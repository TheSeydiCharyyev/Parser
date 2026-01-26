import os
import time
import json
import socket
import random

import httpx
import redis

from parsing import parse_items


def _redis() -> redis.Redis:
    return redis.Redis(
        host=os.environ.get("REDIS_HOST", "redis"),
        port=int(os.environ.get("REDIS_PORT", "6379")),
        db=int(os.environ.get("REDIS_DB", "0")),
        decode_responses=True,
    )


def _sleep_backoff(attempt: int, base: float, cap: float) -> None:
    delay = min(cap, base * (2 ** max(0, attempt - 1)))
    delay = delay + random.uniform(0.0, min(0.25, delay * 0.1))
    time.sleep(delay)


def _request_with_retries(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    max_attempts: int,
    backoff_base: float,
    backoff_cap: float,
    retry_on_status: set[int],
    **kwargs,
) -> httpx.Response:
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            resp = client.request(method, url, **kwargs)
            if resp.status_code in retry_on_status and attempt < max_attempts:
                _sleep_backoff(attempt, backoff_base, backoff_cap)
                continue
            return resp
        except httpx.RequestError as exc:
            last_exc = exc
            if attempt >= max_attempts:
                raise
            _sleep_backoff(attempt, backoff_base, backoff_cap)
    if last_exc:
        raise last_exc
    raise RuntimeError("unreachable")


def _try_report_failed(
    client: httpx.Client,
    backend_base_url: str,
    internal_token: str,
    subscription_id: int,
    error: str,
    job_id: str = "",
    enqueued_at: float | None = None,
) -> bool:
    headers = {}
    if internal_token:
        headers["X-Internal-Token"] = internal_token
    try:
        payload = {"subscription_id": subscription_id, "error": error}
        if job_id:
            payload["job_id"] = job_id
        if enqueued_at is not None:
            payload["enqueued_at"] = enqueued_at
        resp = _request_with_retries(
            client,
            "POST",
            f"{backend_base_url}/api/v1/worker/check_failed/",
            json=payload,
            headers=headers,
            max_attempts=int(os.environ.get("WORKER_API_RETRIES", "3")),
            backoff_base=float(os.environ.get("WORKER_API_BACKOFF_BASE", "0.5")),
            backoff_cap=float(os.environ.get("WORKER_API_BACKOFF_CAP", "5")),
            retry_on_status={500, 502, 503, 504},
        )
        return resp.status_code < 500
    except Exception:
        return False


def main() -> None:
    r = _redis()
    checks_stream = os.environ.get("REDIS_STREAM_CHECKS", "stream:checks")
    checks_group = os.environ.get("REDIS_GROUP_CHECKS", "workers")
    claim_min_idle_ms = int(os.environ.get("REDIS_CLAIM_MIN_IDLE_MS", "60000"))
    backend_base_url = os.environ.get("BACKEND_BASE_URL", "http://backend:8000").rstrip("/")
    internal_token = os.environ.get("INTERNAL_API_TOKEN", "")

    demo_mode = os.environ.get("WORKER_DEMO_MODE", "1") == "1"
    demo_external_id = os.environ.get("WORKER_DEMO_EXTERNAL_ID", "demo-a1")

    user_agent = os.environ.get("WORKER_USER_AGENT", "parser-monitor/1.0")
    max_items = int(os.environ.get("WORKER_MAX_ITEMS", "50"))

    # HTTP retry/backoff knobs
    source_retries = int(os.environ.get("WORKER_SOURCE_RETRIES", "2"))
    source_backoff_base = float(os.environ.get("WORKER_SOURCE_BACKOFF_BASE", "0.5"))
    source_backoff_cap = float(os.environ.get("WORKER_SOURCE_BACKOFF_CAP", "5"))

    api_retries = int(os.environ.get("WORKER_API_RETRIES", "3"))
    api_backoff_base = float(os.environ.get("WORKER_API_BACKOFF_BASE", "0.5"))
    api_backoff_cap = float(os.environ.get("WORKER_API_BACKOFF_CAP", "5"))

    source_proxy = (os.environ.get("WORKER_SOURCE_PROXY") or "").strip() or None

    source_timeout = float(os.environ.get("WORKER_SOURCE_TIMEOUT", "10"))
    api_timeout = float(os.environ.get("WORKER_API_TIMEOUT", "10"))

    source_client = httpx.Client(timeout=source_timeout, follow_redirects=True, proxy=source_proxy, trust_env=False)
    api_client = httpx.Client(timeout=api_timeout, trust_env=False)

    # Ensure consumer group exists.
    # В dev/prod обычно не хотим разгребать "исторический" backlog после пересоздания группы,
    # поэтому при первом создании стартуем с конца потока ("$").
    try:
        r.xgroup_create(name=checks_stream, groupname=checks_group, id="$", mkstream=True)
    except Exception:
        pass

    hostname = os.environ.get("HOSTNAME") or socket.gethostname() or "unknown"
    consumer_name = f"w-{hostname}-{os.getpid()}"

    def process_message(message_id: str, fields: dict) -> None:
        try:
            job_id = (fields.get("job_id") or "").strip()
            try:
                enqueued_at = float(fields.get("enqueued_at")) if fields.get("enqueued_at") is not None else None
            except Exception:
                enqueued_at = None
            subscription_id = int(fields.get("subscription_id", "0"))
            _url = fields.get("url", "")
        except Exception:
            r.xack(checks_stream, checks_group, message_id)
            return

        api_headers = {}
        if internal_token:
            api_headers["X-Internal-Token"] = internal_token

        if demo_mode:
            items = [
                {
                    "source": "generic",
                    "external_id": demo_external_id,
                    "url": f"https://example.com/item/{demo_external_id}",
                    "title": f"Демо-объявление для подписки {subscription_id}",
                    "price": 100,
                }
            ]
        else:
            try:
                src_resp = _request_with_retries(
                    source_client,
                    "GET",
                    _url,
                    headers={"User-Agent": user_agent},
                    max_attempts=source_retries,
                    backoff_base=source_backoff_base,
                    backoff_cap=source_backoff_cap,
                    # retry only on transient upstream issues
                    retry_on_status={500, 502, 503, 504},
                )
            except httpx.RequestError as exc:
                err = f"Fetch error: {type(exc).__name__}: {exc}"
                if _try_report_failed(
                    api_client,
                    backend_base_url,
                    internal_token,
                    subscription_id,
                    err,
                    job_id=job_id,
                    enqueued_at=enqueued_at,
                ):
                    r.xack(checks_stream, checks_group, message_id)
                return

            # Для простоты: фиксируем ошибку и ack, чтобы не копить pending.
            # Следующий чек придёт новой задачей от scheduler.
            if src_resp.status_code == 429 or src_resp.status_code >= 500:
                err = f"HTTP {src_resp.status_code} от источника"
                if _try_report_failed(
                    api_client,
                    backend_base_url,
                    internal_token,
                    subscription_id,
                    err,
                    job_id=job_id,
                    enqueued_at=enqueued_at,
                ):
                    r.xack(checks_stream, checks_group, message_id)
                return
            if src_resp.status_code >= 400:
                err = f"HTTP {src_resp.status_code} от источника"
                if _try_report_failed(
                    api_client,
                    backend_base_url,
                    internal_token,
                    subscription_id,
                    err,
                    job_id=job_id,
                    enqueued_at=enqueued_at,
                ):
                    r.xack(checks_stream, checks_group, message_id)
                return

            parse_result = parse_items(
                _url,
                content_type=src_resp.headers.get("content-type"),
                text=src_resp.text,
                max_items=max_items,
            )

            # Обработка Avito redirect
            if isinstance(parse_result, tuple):
                items, redirect_url = parse_result
                if redirect_url and not items:
                    # Нужно загрузить redirect URL (Avito JS redirect)
                    try:
                        redirect_resp = _request_with_retries(
                            source_client,
                            "GET",
                            redirect_url,
                            headers={"User-Agent": user_agent},
                            max_attempts=source_retries,
                            backoff_base=source_backoff_base,
                            backoff_cap=source_backoff_cap,
                            retry_on_status={500, 502, 503, 504},
                        )
                        if redirect_resp.status_code == 200:
                            parse_result2 = parse_items(
                                redirect_url,
                                content_type=redirect_resp.headers.get("content-type"),
                                text=redirect_resp.text,
                                max_items=max_items,
                            )
                            if isinstance(parse_result2, tuple):
                                items = parse_result2[0]
                            else:
                                items = parse_result2
                    except httpx.RequestError:
                        pass  # Используем пустой items
            else:
                items = parse_result

        payload = {"subscription_id": subscription_id, "items": items}
        if job_id:
            payload["job_id"] = job_id
        if enqueued_at is not None:
            payload["enqueued_at"] = enqueued_at

        try:
            resp = _request_with_retries(
                api_client,
                "POST",
                f"{backend_base_url}/api/v1/worker/report/",
                json=payload,
                headers=api_headers,
                max_attempts=api_retries,
                backoff_base=api_backoff_base,
                backoff_cap=api_backoff_cap,
                retry_on_status={500, 502, 503, 504},
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code if exc.response is not None else 0
            # Перманентные ошибки (например, неверный токен/подписка удалена) не имеет смысла ретраить бесконечно.
            if status_code in (400, 403, 404):
                try:
                    _request_with_retries(
                        api_client,
                        "POST",
                        f"{backend_base_url}/api/v1/worker/check_failed/",
                        json={
                            "subscription_id": subscription_id,
                            "error": f"HTTP {status_code}: {exc.response.text}",
                            **({"job_id": job_id} if job_id else {}),
                            **({"enqueued_at": enqueued_at} if enqueued_at is not None else {}),
                        },
                        headers=api_headers,
                        max_attempts=api_retries,
                        backoff_base=api_backoff_base,
                        backoff_cap=api_backoff_cap,
                        retry_on_status={500, 502, 503, 504},
                    )
                except Exception:
                    pass
                r.xack(checks_stream, checks_group, message_id)
                return
            # Транзиентные 5xx — оставляем pending для повтора.
            return
        except httpx.RequestError:
            # Сетевые ошибки — оставляем pending для повтора.
            return

        r.xack(checks_stream, checks_group, message_id)

    while True:
        now = time.time()
        r.set(f"worker:{consumer_name}:heartbeat", str(now), ex=10)

        # Периодически подбираем "зависшие" pending-сообщения (например, после падения воркера).
        try:
            next_id, claimed, _deleted = r.xautoclaim(
                name=checks_stream,
                groupname=checks_group,
                consumername=consumer_name,
                min_idle_time=claim_min_idle_ms,
                start_id="0-0",
                count=20,
            )
            if claimed:
                for message_id, fields in claimed:
                    process_message(message_id, fields)
        except Exception:
            pass

        res = r.xreadgroup(
            groupname=checks_group,
            consumername=consumer_name,
            streams={checks_stream: ">"},
            count=20,
            block=1000,
        )
        if not res:
            continue

        for _stream_name, messages in res:
            for message_id, fields in messages:
                process_message(message_id, fields)


if __name__ == "__main__":
    main()
