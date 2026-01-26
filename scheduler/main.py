import os
import time
import json

import uuid

import psycopg
import redis

from limiter import clamp_rps, next_due_ts, refill_tokens


def _pg_dsn() -> str:
    return (
        f"dbname={os.environ.get('POSTGRES_DB','parser')} "
        f"user={os.environ.get('POSTGRES_USER','parser')} "
        f"password={os.environ.get('POSTGRES_PASSWORD','parser')} "
        f"host={os.environ.get('POSTGRES_HOST','postgres')} "
        f"port={os.environ.get('POSTGRES_PORT','5432')}"
    )


def _redis() -> redis.Redis:
    return redis.Redis(
        host=os.environ.get("REDIS_HOST", "redis"),
        port=int(os.environ.get("REDIS_PORT", "6379")),
        db=int(os.environ.get("REDIS_DB", "0")),
        decode_responses=True,
    )


def main() -> None:
    r = _redis()
    checks_stream = os.environ.get("REDIS_STREAM_CHECKS", "stream:checks")
    checks_stream_maxlen_raw = os.environ.get("REDIS_STREAM_MAXLEN_CHECKS", "").strip()
    checks_stream_maxlen = int(checks_stream_maxlen_raw) if checks_stream_maxlen_raw else None

    # v2 scheduler: честный лимит RPS на пользователя.
    # Для каждого user_id поддерживаем token bucket (tokens + ts) и выдаём задачи по round-robin
    # между его подписками.
    users_zset = "sched:users"  # score = next_due_ts для пользователя

    # Базовая проверка доступности БД.
    with psycopg.connect(_pg_dsn()) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")

    refresh_every_s = 5.0
    last_refresh = 0.0

    while True:
        now = time.time()
        r.set("scheduler:heartbeat", str(now), ex=10)

        # 1) Периодически обновляем список активных подписок из БД.
        if now - last_refresh >= refresh_every_s:
            last_refresh = now
            with psycopg.connect(_pg_dsn()) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT s.id, s.url, s.user_id, GREATEST(s.rps_limit, 1) AS sub_rps, COALESCE(p.rps_limit, 1) AS user_rps, "
                        "COALESCE(s.check_interval_seconds, 0) AS check_interval, "
                        "EXTRACT(EPOCH FROM s.last_check_at) AS last_check_ts "
                        "FROM api_subscription s "
                        "LEFT JOIN api_telegramprofile p ON p.user_id = s.user_id "
                        "WHERE s.enabled = true AND (s.paused_until IS NULL OR s.paused_until <= NOW())"
                    )
                    subs = cur.fetchall()

            # Пересобираем списки подписок по пользователям в Redis.
            # Формат:
            #   sched:user:{uid}:subs -> list of sub_id (strings)
            #   sched:sub:url -> hash sub_id -> url
            #   sched:sub:interval -> hash sub_id -> interval_seconds (0 = use RPS)
            #   sched:sub:last_check -> hash sub_id -> last_check_ts
            #   sched:user:rps -> hash uid -> rps
            user_to_subs: dict[str, list[tuple[str, str, int]]] = {}
            user_to_rps: dict[str, int] = {}
            sub_intervals: dict[str, int] = {}
            sub_last_checks: dict[str, float] = {}
            for sub_id, url, user_id, sub_rps, user_rps, check_interval, last_check_ts in subs:
                uid = str(int(user_id))
                sid = str(int(sub_id))
                try:
                    sub_weight = clamp_rps(int(sub_rps or 1))
                except Exception:
                    sub_weight = 1
                user_to_subs.setdefault(uid, []).append((sid, url, sub_weight))
                try:
                    user_to_rps[uid] = max(1, min(int(user_rps or 1), 10))
                except Exception:
                    user_to_rps[uid] = 1
                # Сохраняем интервал и время последней проверки
                try:
                    sub_intervals[sid] = int(check_interval or 0)
                except Exception:
                    sub_intervals[sid] = 0
                try:
                    sub_last_checks[sid] = float(last_check_ts or 0)
                except Exception:
                    sub_last_checks[sid] = 0

            pipe = r.pipeline()

            # Сохраняем rps по пользователям
            if user_to_rps:
                pipe.hset("sched:user:rps", mapping={uid: str(rps) for uid, rps in user_to_rps.items()})

            # Сохраняем интервалы и last_check для подписок
            if sub_intervals:
                pipe.hset("sched:sub:interval", mapping={sid: str(iv) for sid, iv in sub_intervals.items()})
            if sub_last_checks:
                pipe.hset("sched:sub:last_check", mapping={sid: str(ts) for sid, ts in sub_last_checks.items()})

            # Обновляем списки подписок и урлы
            for uid, pairs in user_to_subs.items():
                list_key = f"sched:user:{uid}:subs"
                pipe.delete(list_key)
                if pairs:
                    # В list кладём sub_id с весом = sub_rps, чтобы /rps влияло на долю запросов
                    weighted: list[str] = []
                    for sid, _url, w in pairs:
                        weighted.extend([sid] * max(1, w))
                    pipe.rpush(list_key, *weighted)
                    for sid, url, _w in pairs:
                        pipe.hset("sched:sub:url", sid, url)
                # Если пользователя ещё нет в users_zset — ставим его готовым прямо сейчас.
                pipe.zadd(users_zset, {uid: now}, nx=True)

            pipe.execute()

        # 2) Выбираем due-пользователей (score <= now) и выдаём задачи по токенам.
        max_users_batch = 200
        due_users = r.zrangebyscore(users_zset, "-inf", now, start=0, num=max_users_batch)
        if not due_users:
            time.sleep(0.05)
            continue

        # Для каждого пользователя:
        # - пополняем токены согласно RPS
        # - выдаём максимум N задач за тик
        # - планируем следующий due по времени, когда накопится хотя бы 1 токен
        for uid in due_users:
            try:
                uid_int = int(uid)
            except Exception:
                r.zrem(users_zset, uid)
                continue

            subs_key = f"sched:user:{uid_int}:subs"
            sub_ids = r.lrange(subs_key, 0, -1)
            if not sub_ids:
                # Нет подписок — убираем пользователя из расписания.
                r.zrem(users_zset, uid_int)
                continue

            try:
                user_rps = int(r.hget("sched:user:rps", str(uid_int)) or "1")
            except Exception:
                user_rps = 1
            user_rps = clamp_rps(user_rps)

            state_key = f"sched:user:{uid_int}:state"
            state = r.hgetall(state_key) or {}
            try:
                tokens = float(state.get("tokens") or "0")
            except Exception:
                tokens = 0.0
            try:
                last_ts = float(state.get("ts") or "0")
            except Exception:
                last_ts = 0.0
            try:
                idx = int(state.get("idx") or "0")
            except Exception:
                idx = 0

            if last_ts <= 0:
                last_ts = now

            tokens, last_ts = refill_tokens(tokens, last_ts, now, user_rps, burst_seconds=1.0)

            issued = 0
            skipped = 0
            max_jobs_per_tick = min(200, len(sub_ids))
            pipe = r.pipeline()
            while tokens >= 1.0 and issued < max_jobs_per_tick and skipped < len(sub_ids):
                sub_id = sub_ids[idx % len(sub_ids)]
                idx += 1

                # Проверяем интервал для подписки
                try:
                    interval = int(r.hget("sched:sub:interval", sub_id) or "0")
                except Exception:
                    interval = 0

                if interval > 0:
                    # Интервальная подписка — проверяем, прошло ли достаточно времени
                    try:
                        last_check = float(r.hget("sched:sub:last_check", sub_id) or "0")
                    except Exception:
                        last_check = 0
                    if last_check > 0 and (now - last_check) < interval:
                        # Интервал не прошёл, пропускаем
                        skipped += 1
                        continue

                skipped = 0  # Сбрасываем счётчик пропусков
                url = r.hget("sched:sub:url", sub_id) or ""
                job = {
                    "job_id": uuid.uuid4().hex,
                    "enqueued_at": str(now),
                    "subscription_id": str(int(sub_id)),
                    "url": url,
                }
                if checks_stream_maxlen is not None and checks_stream_maxlen > 0:
                    pipe.xadd(checks_stream, job, maxlen=checks_stream_maxlen, approximate=True)
                else:
                    pipe.xadd(checks_stream, job)
                tokens -= 1.0
                issued += 1

            # Сохраняем состояние.
            pipe.hset(state_key, mapping={"tokens": str(tokens), "ts": str(now), "idx": str(idx)})

            # Планируем следующий запуск пользователя.
            # Если токенов хватает — можно запускать сразу, иначе ждём до накопления 1 токена.
            next_due = next_due_ts(tokens, user_rps, now)
            pipe.zadd(users_zset, {str(uid_int): float(next_due)})
            pipe.execute()


if __name__ == "__main__":
    main()
