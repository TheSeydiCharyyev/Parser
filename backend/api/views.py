from __future__ import annotations

import json
import time
import urllib.parse
import re

from datetime import datetime, timezone as dt_timezone

from django.db import models
from django.db import transaction
from django.http import JsonResponse
from django.conf import settings
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse
from rest_framework import status, viewsets
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Item, Subscription, SubscriptionItem, TelegramProfile
from .serializers import (
    BotNotificationOut,
    BotRegisterIn,
    BotChatIn,
    BotSubscriptionCreateIn,
    BotPauseIn,
    BotSubscriptionUpdateIn,
    SubscriptionSerializer,
    WorkerCheckFailedIn,
    WorkerNewItemOut,
    WorkerReportIn,
)


def _redis():
    import redis

    return redis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB,
        decode_responses=True,
    )


def _metrics_keys():
    return {
        "counters": "metrics:counters",
        "obs_sum": "metrics:obs_sum",
        "obs_count": "metrics:obs_count",
        "obs_max": "metrics:obs_max",
    }


def _metrics_incr(r, name: str, amount: int = 1) -> None:
    keys = _metrics_keys()
    try:
        r.hincrby(keys["counters"], name, int(amount))
    except Exception:
        return


def _metrics_observe(r, name: str, value: float) -> None:
    keys = _metrics_keys()
    try:
        r.hincrbyfloat(keys["obs_sum"], name, float(value))
        r.hincrby(keys["obs_count"], name, 1)
        prev = r.hget(keys["obs_max"], name)
        try:
            prev_f = float(prev) if prev is not None else None
        except Exception:
            prev_f = None
        if prev_f is None or float(value) > prev_f:
            r.hset(keys["obs_max"], name, str(float(value)))
    except Exception:
        return


def _metrics_snapshot(r) -> dict:
    keys = _metrics_keys()
    def _hgetall(name: str) -> dict:
        try:
            return r.hgetall(name) or {}
        except Exception:
            return {}
    return {
        "counters": _hgetall(keys["counters"]),
        "observations": {
            "sum": _hgetall(keys["obs_sum"]),
            "count": _hgetall(keys["obs_count"]),
            "max": _hgetall(keys["obs_max"]),
        },
    }


def _require_internal_token(request) -> bool:
    token = getattr(settings, "INTERNAL_API_TOKEN", "")
    if not token:
        return True
    provided = request.headers.get("X-Internal-Token", "")
    return provided == token


@api_view(["GET"])
def internal_stats(request):
    if not _require_internal_token(request):
        return Response({"detail": "forbidden"}, status=status.HTTP_403_FORBIDDEN)

    r = _redis()
    _metrics_incr(r, "internal_stats_total", 1)

    checks_stream = getattr(settings, "REDIS_STREAM_CHECKS", "stream:checks")
    notify_stream = getattr(settings, "REDIS_STREAM_NOTIFY", "stream:notify")
    checks_group = getattr(settings, "REDIS_GROUP_CHECKS", "workers")
    notify_group = getattr(settings, "REDIS_GROUP_NOTIFY", "bot")

    def xinfo_groups(stream: str):
        try:
            # redis-py вернёт list[dict]
            return r.xinfo_groups(stream)
        except Exception:
            return []

    def xlen(stream: str) -> int:
        try:
            return int(r.xlen(stream))
        except Exception:
            return 0

    def xinfo_consumers(stream: str, group: str):
        try:
            # redis-py вернёт list[dict]
            return r.xinfo_consumers(stream, group)
        except Exception:
            return []

    def active_consumers(consumers: list[dict], max_idle_ms: int = 15_000) -> int:
        # Считаем consumer "живым", если он не простаивал слишком долго.
        # Это эвристика: stale consumers остаются в группе даже после остановки контейнера.
        n = 0
        for c in consumers:
            try:
                if int(c.get("idle", 10**12)) <= max_idle_ms:
                    n += 1
            except Exception:
                continue
        return n

    # Heartbeats
    scheduler_hb = r.get("scheduler:heartbeat")
    worker_keys = list(r.scan_iter(match="worker:*:heartbeat", count=100))
    worker_count = len(worker_keys)

    checks_consumers = xinfo_consumers(checks_stream, checks_group)
    notify_consumers = xinfo_consumers(notify_stream, notify_group)

    return Response(
        {
            "streams": {
                "checks": {
                    "name": checks_stream,
                    "len": xlen(checks_stream),
                    "groups": xinfo_groups(checks_stream),
                    "consumers": checks_consumers,
                    "active_consumers": active_consumers(checks_consumers),
                },
                "notify": {
                    "name": notify_stream,
                    "len": xlen(notify_stream),
                    "groups": xinfo_groups(notify_stream),
                    "consumers": notify_consumers,
                    "active_consumers": active_consumers(notify_consumers),
                },
            },
            "groups": {"checks": checks_group, "notify": notify_group},
            "heartbeats": {"scheduler": scheduler_hb, "workers": worker_count},
            "metrics": _metrics_snapshot(r),
        },
        status=status.HTTP_200_OK,
    )


@api_view(["GET"])
def internal_metrics(request):
    if not _require_internal_token(request):
        return Response({"detail": "forbidden"}, status=status.HTTP_403_FORBIDDEN)
    r = _redis()
    _metrics_incr(r, "internal_metrics_total", 1)
    return Response(_metrics_snapshot(r), status=status.HTTP_200_OK)


def _prom_sanitize(name: str) -> str:
    n = re.sub(r"[^a-zA-Z0-9_]", "_", name)
    if not n:
        return "_"
    if not re.match(r"[a-zA-Z_]", n[0]):
        n = f"_{n}"
    return n


@api_view(["GET"])
def internal_metrics_prom(request):
    if not _require_internal_token(request):
        return Response({"detail": "forbidden"}, status=status.HTTP_403_FORBIDDEN)

    r = _redis()
    _metrics_incr(r, "internal_metrics_prom_total", 1)

    snapshot = _metrics_snapshot(r)
    counters = snapshot.get("counters") or {}
    obs = snapshot.get("observations") or {}
    obs_sum = (obs.get("sum") or {})
    obs_count = (obs.get("count") or {})
    obs_max = (obs.get("max") or {})

    # Streams gauges
    checks_stream = getattr(settings, "REDIS_STREAM_CHECKS", "stream:checks")
    notify_stream = getattr(settings, "REDIS_STREAM_NOTIFY", "stream:notify")
    checks_group = getattr(settings, "REDIS_GROUP_CHECKS", "workers")
    notify_group = getattr(settings, "REDIS_GROUP_NOTIFY", "bot")

    def _xlen(stream: str) -> int:
        try:
            return int(r.xlen(stream))
        except Exception:
            return 0

    def _xp_count(stream: str, group: str) -> int:
        try:
            # XPENDING summary: (count, start, end, consumers)
            summary = r.xpending(stream, group)
            return int(summary[0]) if summary else 0
        except Exception:
            return 0

    lines: list[str] = []
    lines.append("# parser internal metrics (generated)")

    # Counters
    for raw_name, raw_value in sorted(counters.items()):
        metric = f"parser_{_prom_sanitize(raw_name)}"
        try:
            value = int(float(raw_value))
        except Exception:
            continue
        mtype = "counter" if metric.endswith("_total") else "gauge"
        lines.append(f"# TYPE {metric} {mtype}")
        lines.append(f"{metric} {value}")

    # Observations (sum/count/max)
    for raw_name in sorted(set(obs_sum.keys()) | set(obs_count.keys()) | set(obs_max.keys())):
        base = f"parser_{_prom_sanitize(raw_name)}"
        for suffix, src, mtype in (
            ("_sum", obs_sum, "gauge"),
            ("_count", obs_count, "gauge"),
            ("_max", obs_max, "gauge"),
        ):
            if raw_name not in src:
                continue
            metric = f"{base}{suffix}"
            try:
                value = float(src.get(raw_name))
            except Exception:
                continue
            lines.append(f"# TYPE {metric} {mtype}")
            lines.append(f"{metric} {value}")

    # Queue depth / lag approximations
    lines.append("# TYPE parser_stream_checks_len gauge")
    lines.append(f"parser_stream_checks_len {_xlen(checks_stream)}")
    lines.append("# TYPE parser_stream_notify_len gauge")
    lines.append(f"parser_stream_notify_len {_xlen(notify_stream)}")

    lines.append("# TYPE parser_stream_checks_pending gauge")
    lines.append(f"parser_stream_checks_pending {_xp_count(checks_stream, checks_group)}")
    lines.append("# TYPE parser_stream_notify_pending gauge")
    lines.append(f"parser_stream_notify_pending {_xp_count(notify_stream, notify_group)}")

    body = "\n".join(lines) + "\n"
    return HttpResponse(body, content_type="text/plain; version=0.0.4; charset=utf-8")


def health(_request):
    return JsonResponse({"ok": True})


class SubscriptionViewSet(viewsets.ModelViewSet):
    serializer_class = SubscriptionSerializer

    def get_queryset(self):
        # v1: без полноценной авторизации. Для демо: работаем от суперпользователя/первого юзера.
        # На следующем шаге подключим токены для bot/worker и привязку к пользователю.
        return Subscription.objects.all().order_by("-id")

    def perform_create(self, serializer):
        # v1: если нет auth — привяжем к первому пользователю, иначе создадим.
        from django.contrib.auth import get_user_model

        user_model = get_user_model()
        user = user_model.objects.order_by("id").first()
        if user is None:
            user = user_model.objects.create_user(username="admin")
        serializer.save(user=user)


@api_view(["POST"])
def worker_report(request):
    if not _require_internal_token(request):
        return Response({"detail": "forbidden"}, status=status.HTTP_403_FORBIDDEN)

    payload = WorkerReportIn(data=request.data)
    payload.is_valid(raise_exception=True)

    r = _redis()
    _metrics_incr(r, "worker_report_total", 1)

    subscription_id = payload.validated_data["subscription_id"]
    items_in = payload.validated_data["items"]
    job_id = (payload.validated_data.get("job_id") or "").strip()
    enqueued_at = payload.validated_data.get("enqueued_at")

    try:
        subscription = Subscription.objects.get(id=subscription_id)
    except Subscription.DoesNotExist:
        return Response({"detail": "subscription not found"}, status=status.HTTP_404_NOT_FOUND)

    now = timezone.now()

    # Job tracing / latency
    last_job_enqueued_at = None
    last_job_latency_ms = None
    if enqueued_at is not None:
        try:
            enq = float(enqueued_at)
            if enq > 0:
                last_job_enqueued_at = datetime.fromtimestamp(enq, tz=dt_timezone.utc)
                latency_ms = int(max(0.0, (time.time() - enq) * 1000.0))
                last_job_latency_ms = latency_ms
                _metrics_observe(r, "job_latency_ms", float(latency_ms))
        except Exception:
            pass

    # Отмечаем факт успешного чека (даже если items пустой).
    Subscription.objects.filter(id=subscription.id).update(
        last_check_at=now,
        last_success_at=now,
        last_error="",
        consecutive_errors=0,
        paused_until=None,
        pause_reason="",
        last_job_id=job_id or models.F("last_job_id"),
        last_job_enqueued_at=last_job_enqueued_at or models.F("last_job_enqueued_at"),
        last_job_latency_ms=last_job_latency_ms if last_job_latency_ms is not None else models.F("last_job_latency_ms"),
    )

    new_items: list[Item] = []
    notify_events: list[dict] = []
    for it in items_in:
        item, _created = Item.objects.update_or_create(
            source=it.get("source", "generic"),
            external_id=it["external_id"],
            defaults={
                "url": it["url"],
                "title": it.get("title", ""),
                "price": it.get("price"),
                "published_at": it.get("published_at"),
                "raw": it.get("raw"),
            },
        )

        # Дедуп на уровне БД: уникальный ключ (subscription,item)
        sub_item, created = SubscriptionItem.objects.get_or_create(subscription=subscription, item=item)
        if created:
            new_items.append(item)
            notify_events.append({"subscription_id": subscription.id, "item_id": item.id})

    if notify_events:
        Subscription.objects.filter(id=subscription.id).update(last_item_at=now)

    # Push notifications to Redis stream for bot/notifier (at-least-once).
    if notify_events:
        r = _redis()
        stream = getattr(settings, "REDIS_STREAM_NOTIFY", "stream:notify")
        maxlen = int(getattr(settings, "REDIS_STREAM_MAXLEN_NOTIFY", 0) or 0)
        for ev in notify_events:
            fields = {"subscription_id": str(ev["subscription_id"]), "item_id": str(ev["item_id"])}
            if maxlen > 0:
                r.xadd(stream, fields, maxlen=maxlen, approximate=True)
            else:
                r.xadd(stream, fields)

        _metrics_incr(r, "notify_enqueued_total", len(notify_events))

    Subscription.objects.filter(id=subscription.id).update(updated_at=now)
    out = WorkerNewItemOut(new_items, many=True)
    _metrics_incr(r, "new_items_total", len(new_items))
    return Response({"new_items": out.data}, status=status.HTTP_200_OK)


@api_view(["POST"])
def worker_check_failed(request):
    if not _require_internal_token(request):
        return Response({"detail": "forbidden"}, status=status.HTTP_403_FORBIDDEN)

    payload = WorkerCheckFailedIn(data=request.data)
    payload.is_valid(raise_exception=True)

    r = _redis()
    _metrics_incr(r, "worker_check_failed_total", 1)

    subscription_id = payload.validated_data["subscription_id"]
    error = payload.validated_data["error"]
    job_id = (payload.validated_data.get("job_id") or "").strip()
    enqueued_at = payload.validated_data.get("enqueued_at")
    now = timezone.now()

    last_job_enqueued_at = None
    last_job_latency_ms = None
    if enqueued_at is not None:
        try:
            enq = float(enqueued_at)
            if enq > 0:
                last_job_enqueued_at = datetime.fromtimestamp(enq, tz=dt_timezone.utc)
                last_job_latency_ms = int(max(0.0, (time.time() - enq) * 1000.0))
                _metrics_observe(r, "job_latency_ms", float(last_job_latency_ms))
        except Exception:
            pass

    with transaction.atomic():
        try:
            sub = Subscription.objects.select_for_update().get(id=subscription_id)
        except Subscription.DoesNotExist:
            return Response({"detail": "subscription not found"}, status=status.HTTP_404_NOT_FOUND)

        new_consecutive = int(sub.consecutive_errors or 0) + 1

        updates = {
            "last_check_at": now,
            "last_error": error[:2000],
            "consecutive_errors": new_consecutive,
            "updated_at": now,
        }

        if job_id:
            updates["last_job_id"] = job_id
        if last_job_enqueued_at is not None:
            updates["last_job_enqueued_at"] = last_job_enqueued_at
        if last_job_latency_ms is not None:
            updates["last_job_latency_ms"] = last_job_latency_ms

        # Авто-пауза при блокировках источника (например, Avito 429/403).
        # Это НЕ обход капчи, а защита от "добивания" IP повторными запросами.
        if "HTTP 429" in error or "HTTP 403" in error:
            attempt = max(1, min(new_consecutive, 6))
            pause_seconds = min(3600, 60 * (2 ** (attempt - 1)))
            updates["paused_until"] = now + timezone.timedelta(seconds=pause_seconds)
            updates["pause_reason"] = f"auto_pause: {error[:200]}"

        # Ошибки считаем для метрик
        _metrics_incr(r, "errors_total", 1)

        Subscription.objects.filter(id=sub.id).update(**updates)

    return Response({"ok": True}, status=status.HTTP_200_OK)


@csrf_exempt
@api_view(["POST"])
def bot_register(request):
    if not _require_internal_token(request):
        return Response({"detail": "forbidden"}, status=status.HTTP_403_FORBIDDEN)

    payload = BotRegisterIn(data=request.data)
    payload.is_valid(raise_exception=True)
    chat_id = payload.validated_data["chat_id"]
    username = payload.validated_data.get("username") or f"tg_{chat_id}"

    from django.contrib.auth import get_user_model

    user_model = get_user_model()
    user, _ = user_model.objects.get_or_create(username=username)
    TelegramProfile.objects.update_or_create(user=user, defaults={"chat_id": chat_id})
    return Response({"ok": True, "user_id": user.id}, status=status.HTTP_200_OK)


@csrf_exempt
@api_view(["GET", "POST"])
def bot_create_subscription(request):
    if not _require_internal_token(request):
        return Response({"detail": "forbidden"}, status=status.HTTP_403_FORBIDDEN)

    if request.method == "GET":
        payload = BotChatIn(data=request.query_params)
        payload.is_valid(raise_exception=True)
        chat_id = payload.validated_data["chat_id"]

        try:
            profile = TelegramProfile.objects.get(chat_id=chat_id)
        except TelegramProfile.DoesNotExist:
            return Response({"detail": "chat not registered"}, status=status.HTTP_400_BAD_REQUEST)

        subs = Subscription.objects.filter(user=profile.user).order_by("-id")
        return Response(SubscriptionSerializer(subs, many=True).data, status=status.HTTP_200_OK)

    payload = BotSubscriptionCreateIn(data=request.data)
    payload.is_valid(raise_exception=True)
    chat_id = payload.validated_data["chat_id"]
    url = payload.validated_data["url"]
    rps_limit = payload.validated_data.get("rps_limit", 1)
    check_interval_seconds = payload.validated_data.get("check_interval_seconds", 0)
    enabled = payload.validated_data.get("enabled", True)

    try:
        profile = TelegramProfile.objects.get(chat_id=chat_id)
    except TelegramProfile.DoesNotExist:
        return Response({"detail": "chat not registered"}, status=status.HTTP_400_BAD_REQUEST)

    sub = Subscription.objects.create(
        user=profile.user,
        url=url,
        rps_limit=rps_limit,
        check_interval_seconds=check_interval_seconds,
        enabled=enabled,
    )
    return Response(SubscriptionSerializer(sub).data, status=status.HTTP_201_CREATED)


@csrf_exempt
@api_view(["GET", "PATCH", "DELETE"])
def bot_subscription_detail(request, subscription_id: int):
    if not _require_internal_token(request):
        return Response({"detail": "forbidden"}, status=status.HTTP_403_FORBIDDEN)

    if request.method == "GET":
        payload = BotChatIn(data=request.query_params)
        payload.is_valid(raise_exception=True)
        chat_id = payload.validated_data["chat_id"]

        try:
            profile = TelegramProfile.objects.get(chat_id=chat_id)
        except TelegramProfile.DoesNotExist:
            return Response({"detail": "chat not registered"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            sub = Subscription.objects.get(id=subscription_id, user=profile.user)
        except Subscription.DoesNotExist:
            return Response({"detail": "subscription not found"}, status=status.HTTP_404_NOT_FOUND)

        return Response(SubscriptionSerializer(sub).data, status=status.HTTP_200_OK)

    if request.method == "DELETE":
        payload = BotChatIn(data=request.query_params)
        payload.is_valid(raise_exception=True)
        chat_id = payload.validated_data["chat_id"]
    else:
        payload = BotSubscriptionUpdateIn(data=request.data)
        payload.is_valid(raise_exception=True)
        chat_id = payload.validated_data["chat_id"]

    try:
        profile = TelegramProfile.objects.get(chat_id=chat_id)
    except TelegramProfile.DoesNotExist:
        return Response({"detail": "chat not registered"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        sub = Subscription.objects.get(id=subscription_id, user=profile.user)
    except Subscription.DoesNotExist:
        return Response({"detail": "subscription not found"}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "DELETE":
        sub.delete()
        return Response({"ok": True}, status=status.HTTP_200_OK)

    updates: dict = {}
    if "enabled" in payload.validated_data:
        updates["enabled"] = payload.validated_data["enabled"]
        # Если руками включили — снимаем авто-паузу.
        if payload.validated_data["enabled"] is True:
            updates["paused_until"] = None
            updates["pause_reason"] = ""
    if "rps_limit" in payload.validated_data:
        updates["rps_limit"] = payload.validated_data["rps_limit"]
    if "check_interval_seconds" in payload.validated_data:
        updates["check_interval_seconds"] = payload.validated_data["check_interval_seconds"]
    if updates:
        Subscription.objects.filter(id=sub.id).update(**updates)
        sub.refresh_from_db()

    return Response(SubscriptionSerializer(sub).data, status=status.HTTP_200_OK)


@csrf_exempt
@api_view(["POST"])
def bot_subscription_pause(request, subscription_id: int):
    if not _require_internal_token(request):
        return Response({"detail": "forbidden"}, status=status.HTTP_403_FORBIDDEN)

    payload = BotPauseIn(data=request.data)
    payload.is_valid(raise_exception=True)
    chat_id = payload.validated_data["chat_id"]
    minutes = payload.validated_data.get("minutes") or 60

    try:
        profile = TelegramProfile.objects.get(chat_id=chat_id)
    except TelegramProfile.DoesNotExist:
        return Response({"detail": "chat not registered"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        sub = Subscription.objects.get(id=subscription_id, user=profile.user)
    except Subscription.DoesNotExist:
        return Response({"detail": "subscription not found"}, status=status.HTTP_404_NOT_FOUND)

    now = timezone.now()
    paused_until = now + timezone.timedelta(minutes=int(minutes))
    Subscription.objects.filter(id=sub.id).update(
        paused_until=paused_until,
        pause_reason=f"manual_pause: {int(minutes)}m",
        updated_at=now,
    )
    sub.refresh_from_db()

    r = _redis()
    _metrics_incr(r, "manual_pause_total", 1)
    return Response(SubscriptionSerializer(sub).data, status=status.HTTP_200_OK)


@csrf_exempt
@api_view(["POST"])
def bot_subscription_unpause(request, subscription_id: int):
    if not _require_internal_token(request):
        return Response({"detail": "forbidden"}, status=status.HTTP_403_FORBIDDEN)

    payload = BotChatIn(data=request.data)
    payload.is_valid(raise_exception=True)
    chat_id = payload.validated_data["chat_id"]

    try:
        profile = TelegramProfile.objects.get(chat_id=chat_id)
    except TelegramProfile.DoesNotExist:
        return Response({"detail": "chat not registered"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        sub = Subscription.objects.get(id=subscription_id, user=profile.user)
    except Subscription.DoesNotExist:
        return Response({"detail": "subscription not found"}, status=status.HTTP_404_NOT_FOUND)

    now = timezone.now()
    Subscription.objects.filter(id=sub.id).update(paused_until=None, pause_reason="", updated_at=now)
    sub.refresh_from_db()

    r = _redis()
    _metrics_incr(r, "manual_unpause_total", 1)
    return Response(SubscriptionSerializer(sub).data, status=status.HTTP_200_OK)


@api_view(["GET"])
def bot_notification(request):
    if not _require_internal_token(request):
        return Response({"detail": "forbidden"}, status=status.HTTP_403_FORBIDDEN)

    subscription_id = request.query_params.get("subscription_id")
    item_id = request.query_params.get("item_id")
    if not subscription_id or not item_id:
        return Response({"detail": "subscription_id and item_id are required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        sub = Subscription.objects.select_related("user").get(id=int(subscription_id))
        item = Item.objects.get(id=int(item_id))
        profile = TelegramProfile.objects.get(user=sub.user)
    except (Subscription.DoesNotExist, Item.DoesNotExist, TelegramProfile.DoesNotExist, ValueError):
        return Response({"detail": "not found"}, status=status.HTTP_404_NOT_FOUND)

    # Фиксируем факт уведомления (помогает показать в админке прогресс и скорость).
    now = timezone.now()
    SubscriptionItem.objects.filter(subscription=sub, item=item, notified_at__isnull=True).update(
        notified_at=now
    )

    text = f"{item.title or 'Новое объявление'}\nЦена: {item.price or '-'}\n{item.url}"
    out = BotNotificationOut({"chat_id": profile.chat_id, "text": text})
    return Response(out.data, status=status.HTTP_200_OK)


@api_view(["GET"])
def demo_source(request):
    """Локальный "источник" для проверки воркера/парсинга.

    Возвращает HTML с JSON-LD (schema.org ItemList). Это позволяет проверить этап D
    без внешнего интернета и без привязки к конкретному сайту.
    """

    # Важно: item.url в backend валидируется как URLField. Для демо берём домен с TLD,
    # чтобы не ослаблять валидацию в ядре под внутренние hostname'ы.
    item_base = "https://example.com/"
    html_doc = f"""<!doctype html>
<html lang="ru">
    <head>
        <meta charset="utf-8" />
        <title>Демо-источник</title>
        <script type="application/ld+json">
        {{
            "@context": "https://schema.org",
            "@type": "ItemList",
            "itemListElement": [
                {{"@type": "ListItem", "position": 1, "item": {{"@type": "Product", "url": "{item_base}demo/items/1001/", "name": "Демо объявление 1001", "offers": {{"price": 10000}}, "datePublished": "2026-01-22T10:00:00Z" }} }},
                {{"@type": "ListItem", "position": 2, "item": {{"@type": "Product", "url": "{item_base}demo/items/1002/", "name": "Демо объявление 1002", "offers": {{"price": "20 000"}} }} }}
            ]
        }}
        </script>
    </head>
    <body>
        <h1>Демо-источник</h1>
        <p>Этот эндпоинт нужен для проверки воркера/парсинга.</p>
    </body>
</html>
"""

    return HttpResponse(html_doc, content_type="text/html; charset=utf-8")


@api_view(["GET"])
def demo_source_dynamic(request):
    """Демо-источник с "новыми" объявлениями на каждом запросе.

    Нужен, чтобы записывать видео и проверять сквозной поток уведомлений:
    scheduler -> worker(fetch+parse) -> backend(dedup) -> notify stream -> bot.

    query params:
      - q: текст для заголовка (например, "айфон мск")
      - n: сколько items возвращать (по умолчанию 2)
    """

    q = (request.query_params.get("q") or "").strip()
    if not q:
        q = "демо"

    try:
        n = int(request.query_params.get("n") or "2")
    except ValueError:
        n = 2
    n = max(1, min(n, 10))

    # Генерируем уникальную базу по времени (секунды). Это гарантирует "новые" external_id.
    ts = int(time.time())
    q_slug = urllib.parse.quote_plus(q)

    item_base = "https://example.com/"
    items_jsonld = []
    for i in range(n):
        ext_id = f"{ts}-{i+1}"
        items_jsonld.append(
            {
                "@type": "ListItem",
                "position": i + 1,
                "item": {
                    "@type": "Product",
                    "url": f"{item_base}demo/{q_slug}/{ext_id}/",
                    "name": f"{q} — объявление {ext_id}",
                    "offers": {"price": 10000 + 1000 * i},
                    "datePublished": timezone.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
                },
            }
        )

    html_doc = f"""<!doctype html>
<html lang=\"ru\">
  <head>
    <meta charset=\"utf-8\" />
    <title>Демо-источник (dynamic)</title>
    <script type=\"application/ld+json\">
    {json.dumps({"@context": "https://schema.org", "@type": "ItemList", "itemListElement": items_jsonld}, ensure_ascii=False)}
    </script>
  </head>
  <body>
    <h1>Демо-источник (dynamic)</h1>
    <p>q={q}</p>
    <p>ts={ts}</p>
  </body>
</html>
"""

    return HttpResponse(html_doc, content_type="text/html; charset=utf-8")
