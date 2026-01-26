import asyncio
import os
import json
import socket
import random
from datetime import datetime, timezone

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

import httpx
import redis


async def main() -> None:
    token = os.environ.get("BOT_TOKEN")
    backend_base_url = os.environ.get("BACKEND_BASE_URL", "http://backend:8000").rstrip("/")
    internal_token = os.environ.get("INTERNAL_API_TOKEN", "")
    notify_stream = os.environ.get("REDIS_STREAM_NOTIFY", "stream:notify")
    notify_group = os.environ.get("REDIS_GROUP_NOTIFY", "bot")
    claim_min_idle_ms = int(os.environ.get("REDIS_CLAIM_MIN_IDLE_MS", "60000"))

    r = redis.Redis(
        host=os.environ.get("REDIS_HOST", "redis"),
        port=int(os.environ.get("REDIS_PORT", "6379")),
        db=int(os.environ.get("REDIS_DB", "0")),
        decode_responses=True,
    )

    api_timeout = float(os.environ.get("BOT_API_TIMEOUT", "10"))
    api_retries = int(os.environ.get("BOT_API_RETRIES", "3"))
    api_backoff_base = float(os.environ.get("BOT_API_BACKOFF_BASE", "0.5"))
    api_backoff_cap = float(os.environ.get("BOT_API_BACKOFF_CAP", "5"))

    bot_proxy = (os.environ.get("BOT_PROXY") or "").strip() or None
    http_kwargs: dict = {"timeout": api_timeout, "trust_env": False}
    if bot_proxy:
        http_kwargs["proxy"] = bot_proxy

    http = httpx.AsyncClient(**http_kwargs)

    bot: Bot | None = None
    if token and token != "replace-me":
        bot = Bot(token=token)
    dp = Dispatcher()

    def _parse_dt(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            return None

    async def _sleep_backoff(attempt: int) -> None:
        delay = min(api_backoff_cap, api_backoff_base * (2 ** max(0, attempt - 1)))
        delay = delay + random.uniform(0.0, min(0.25, delay * 0.1))
        await asyncio.sleep(delay)

    async def call_backend(path: str, payload: dict | None = None, method: str = "POST"):
        headers = {}
        if internal_token:
            headers["X-Internal-Token"] = internal_token
        url = f"{backend_base_url}{path}"
        method = method.upper()

        async def _do_request():
            if method == "POST":
                return await http.post(url, json=payload or {}, headers=headers)
            if method == "PATCH":
                return await http.patch(url, json=payload or {}, headers=headers)
            if method == "DELETE":
                return await http.delete(url, params=payload or {}, headers=headers)
            return await http.get(url, params=payload or {}, headers=headers)

        last_exc: Exception | None = None
        for attempt in range(1, api_retries + 1):
            try:
                resp = await _do_request()
                if resp.status_code in (500, 502, 503, 504) and attempt < api_retries:
                    await _sleep_backoff(attempt)
                    continue
                return resp
            except httpx.RequestError as exc:
                last_exc = exc
                if attempt >= api_retries:
                    raise
                await _sleep_backoff(attempt)
        if last_exc:
            raise last_exc
        raise RuntimeError("unreachable")

    async def notification_loop() -> None:
        try:
            await asyncio.to_thread(r.xgroup_create, notify_stream, notify_group, "$", True)
        except Exception:
            pass

        hostname = os.environ.get("HOSTNAME") or socket.gethostname() or "unknown"
        consumer_name = f"b-{hostname}-{os.getpid()}"

        async def ack(message_id: str) -> None:
            await asyncio.to_thread(r.xack, notify_stream, notify_group, message_id)

        async def process_message(message_id: str, fields: dict) -> None:
            try:
                subscription_id = fields.get("subscription_id")
                item_id = fields.get("item_id")
                if not subscription_id or not item_id:
                    await ack(message_id)
                    return
            except Exception:
                return

            resp = await call_backend(
                "/api/v1/bot/notification/",
                {"subscription_id": subscription_id, "item_id": item_id},
                method="GET",
            )
            if resp.status_code != 200:
                if resp.status_code in (400, 404):
                    await ack(message_id)
                return
            data = resp.json()

            if bot is None:
                print(f"[notify] chat_id={data.get('chat_id')} text={data.get('text')}")
                await ack(message_id)
                return

            try:
                await bot.send_message(chat_id=data["chat_id"], text=data["text"])
            except Exception:
                # Не ack'аем, чтобы сообщение осталось pending.
                return

            await ack(message_id)

        while True:
            # Подбираем pending (например, после падения бота или сетевых ошибок).
            try:
                next_id, claimed, _deleted = await asyncio.to_thread(
                    r.xautoclaim,
                    notify_stream,
                    notify_group,
                    consumer_name,
                    claim_min_idle_ms,
                    "0-0",
                    20,
                )
                if claimed:
                    for message_id, fields in claimed:
                        await process_message(message_id, fields)
            except Exception:
                pass

            res = await asyncio.to_thread(
                r.xreadgroup,
                notify_group,
                consumer_name,
                {notify_stream: ">"},
                20,
                1000,
            )
            if not res:
                continue

            for _stream_name, messages in res:
                for message_id, fields in messages:
                    await process_message(message_id, fields)

    # Готовые подписки для быстрого добавления
    QUICK_SUBSCRIPTIONS = {
        "iphone_msk": {
            "name": "📱 iPhone Москва",
            "url": "https://www.avito.ru/moskva/telefony?q=iphone",
            "enabled": True,
        },
        "iphone_spb": {
            "name": "📱 iPhone СПб",
            "url": "https://www.avito.ru/sankt-peterburg/telefony?q=iphone",
            "enabled": False,  # Пока не работает
        },
    }

    def get_quick_keyboard() -> InlineKeyboardMarkup:
        buttons = []
        for key, data in QUICK_SUBSCRIPTIONS.items():
            status = "" if data["enabled"] else " (скоро)"
            buttons.append([InlineKeyboardButton(
                text=f"{data['name']}{status}",
                callback_data=f"quick:{key}"
            )])
        return InlineKeyboardMarkup(inline_keyboard=buttons)

    @dp.message(CommandStart())
    async def start(message: Message) -> None:
        # register chat
        await call_backend(
            "/api/v1/bot/register/",
            {"chat_id": message.chat.id, "username": f"tg_{message.chat.id}"},
            method="POST",
        )
        await message.answer(
            "👋 Привет! Я бот для отслеживания объявлений на Avito.\n\n"
            "🚀 Быстрый старт — выберите подписку:",
            reply_markup=get_quick_keyboard()
        )
        await message.answer(
            "📝 Или используйте команды:\n"
            "/add <url> — добавить свою ссылку\n"
            "/list — список подписок\n"
            "/status <id> — статус подписки\n"
            "/del <id> — удалить\n"
            "/on <id> | /off <id> — вкл/выкл"
        )

    @dp.callback_query(F.data.startswith("quick:"))
    async def quick_subscription(callback: CallbackQuery) -> None:
        key = callback.data.split(":", 1)[1]
        sub_data = QUICK_SUBSCRIPTIONS.get(key)

        if not sub_data:
            await callback.answer("Неизвестная подписка")
            return

        if not sub_data["enabled"]:
            await callback.answer("⏳ Эта подписка пока недоступна", show_alert=True)
            return

        # Создаём подписку
        resp = await call_backend(
            "/api/v1/bot/subscriptions/",
            {
                "chat_id": callback.message.chat.id,
                "url": sub_data["url"],
                "rps_limit": 1,
                "enabled": True,
                "check_interval_seconds": 300,  # 5 минут
            },
            method="POST",
        )

        if resp.status_code >= 300:
            await callback.answer(f"Ошибка: {resp.text[:100]}", show_alert=True)
            return

        data = resp.json()
        await callback.answer("✅ Подписка создана!")
        await callback.message.answer(
            f"✅ Подписка создана!\n\n"
            f"🆔 ID: {data.get('id')}\n"
            f"🔗 {sub_data['name']}\n"
            f"⏱ Проверка каждые 5 минут\n\n"
            f"Вы будете получать уведомления о новых объявлениях."
        )

    @dp.message(F.text.regexp(r"^/add(@\w+)?(\s|$)"))
    async def add_subscription(message: Message) -> None:
        parts = message.text.split()
        if parts:
            parts[0] = parts[0].split("@", 1)[0]
        if len(parts) < 2:
            await message.answer("Использование: /add <url> [rps]")
            return

        url = parts[1].strip()
        rps = 1
        if len(parts) >= 3:
            try:
                rps = int(parts[2])
            except ValueError:
                await message.answer("RPS должен быть числом 1–10")
                return

        resp = await call_backend(
            "/api/v1/bot/subscriptions/",
            {"chat_id": message.chat.id, "url": url, "rps_limit": rps, "enabled": True},
            method="POST",
        )
        if resp.status_code >= 300:
            await message.answer(f"Не удалось добавить ссылку: {resp.text}")
            return
        data = resp.json()
        await message.answer(f"Добавлено. ID: {data.get('id')}\nRPS: {data.get('rps_limit')}\n{data.get('url')}")

    @dp.message(F.text.regexp(r"^/list(@\w+)?$"))
    async def list_subscriptions(message: Message) -> None:
        resp = await call_backend(
            "/api/v1/bot/subscriptions/",
            {"chat_id": message.chat.id},
            method="GET",
        )
        if resp.status_code >= 300:
            await message.answer(f"Не удалось получить список: {resp.text}")
            return
        subs = resp.json()
        if not subs:
            await message.answer("Подписок пока нет. Добавьте: /add <url> [rps]")
            return

        def _pause_label(s: dict) -> str:
            pu = s.get("paused_until")
            if not pu:
                return ""
            dt = _parse_dt(str(pu))
            if dt and dt > datetime.now(timezone.utc):
                return f" (пауза до {dt.strftime('%H:%M UTC')})"
            if dt is None:
                return " (пауза)"
            return ""

        lines = ["Ваши подписки:"]
        for s in subs:
            status = "вкл" if s.get("enabled") else "выкл"
            lines.append(
                f"#{s.get('id')} [{status}]{_pause_label(s)} rps={s.get('rps_limit')} — {s.get('url')}"
            )
        await message.answer("\n".join(lines))

    @dp.message(F.text.regexp(r"^/status(@\w+)?(\s|$)"))
    async def subscription_status(message: Message) -> None:
        parts = message.text.split()
        # Поддерживаем формат /status@BotName 15
        if parts:
            parts[0] = parts[0].split("@", 1)[0]
        if len(parts) != 2:
            await message.answer("Использование: /status <id>")
            return
        try:
            sub_id = int(parts[1].strip("<>").strip())
        except ValueError:
            await message.answer("ID должен быть числом")
            return

        resp = await call_backend(
            f"/api/v1/bot/subscriptions/{sub_id}/",
            {"chat_id": message.chat.id},
            method="GET",
        )
        if resp.status_code >= 300:
            await message.answer(f"Не удалось получить статус: {resp.text}")
            return

        s = resp.json()
        enabled = "вкл" if s.get("enabled") else "выкл"
        pu = s.get("paused_until")
        pause_txt = ""
        pu_dt = _parse_dt(str(pu)) if pu else None
        if pu_dt and pu_dt > datetime.now(timezone.utc):
            pause_txt = f"\nПауза до: {pu_dt.strftime('%Y-%m-%d %H:%M:%S UTC')}"
        elif pu:
            pause_txt = f"\nПауза до: {pu}"

        last_error = (s.get("last_error") or "").strip()
        if len(last_error) > 500:
            last_error = last_error[:500] + "…"

        text = (
            f"Подписка #{s.get('id')} [{enabled}]\n"
            f"RPS: {s.get('rps_limit')}\n"
            f"URL: {s.get('url')}"
            f"{pause_txt}\n"
            f"job_id: {s.get('last_job_id') or '-'}\n"
            f"Задержка job: {(str(s.get('last_job_latency_ms')) + ' ms') if s.get('last_job_latency_ms') is not None else '-'}\n"
            f"Последняя проверка: {s.get('last_check_at') or '-'}\n"
            f"Последний успех: {s.get('last_success_at') or '-'}\n"
            f"Последняя находка: {s.get('last_item_at') or '-'}\n"
            f"Ошибок подряд: {s.get('consecutive_errors') or 0}\n"
            f"Ошибка: {last_error or '-'}"
        )
        await message.answer(text)

    @dp.message(F.text.regexp(r"^/pause(@\w+)?(\s|$)"))
    async def pause_subscription(message: Message) -> None:
        parts = message.text.split()
        if parts:
            parts[0] = parts[0].split("@", 1)[0]
        if len(parts) not in (2, 3):
            await message.answer("Использование: /pause <id> [minutes]")
            return
        try:
            sub_id = int(parts[1].strip("<>").strip())
        except ValueError:
            await message.answer("ID должен быть числом")
            return

        minutes: int | None = None
        if len(parts) == 3:
            try:
                minutes = int(parts[2])
            except ValueError:
                await message.answer("minutes должен быть числом")
                return

        payload = {"chat_id": message.chat.id}
        if minutes is not None:
            payload["minutes"] = minutes

        resp = await call_backend(
            f"/api/v1/bot/subscriptions/{sub_id}/pause/",
            payload,
            method="POST",
        )
        if resp.status_code >= 300:
            await message.answer(f"Не удалось поставить на паузу: {resp.text}")
            return
        s = resp.json()
        await message.answer(f"Подписка #{s.get('id')} на паузе до: {s.get('paused_until')}")

    @dp.message(F.text.regexp(r"^/unpause(@\w+)?(\s|$)"))
    async def unpause_subscription(message: Message) -> None:
        parts = message.text.split()
        if parts:
            parts[0] = parts[0].split("@", 1)[0]
        if len(parts) != 2:
            await message.answer("Использование: /unpause <id>")
            return
        try:
            sub_id = int(parts[1].strip("<>").strip())
        except ValueError:
            await message.answer("ID должен быть числом")
            return

        resp = await call_backend(
            f"/api/v1/bot/subscriptions/{sub_id}/unpause/",
            {"chat_id": message.chat.id},
            method="POST",
        )
        if resp.status_code >= 300:
            await message.answer(f"Не удалось снять паузу: {resp.text}")
            return
        s = resp.json()
        await message.answer(f"Подписка #{s.get('id')} снята с паузы")

    @dp.message(F.text.regexp(r"^/del(@\w+)?(\s|$)"))
    async def delete_subscription(message: Message) -> None:
        parts = message.text.split()
        if parts:
            parts[0] = parts[0].split("@", 1)[0]
        if len(parts) != 2:
            await message.answer("Использование: /del <id>")
            return
        try:
            sub_id = int(parts[1].strip("<>").strip())
        except ValueError:
            await message.answer("ID должен быть числом")
            return

        resp = await call_backend(
            f"/api/v1/bot/subscriptions/{sub_id}/",
            {"chat_id": message.chat.id},
            method="DELETE",
        )
        if resp.status_code >= 300:
            await message.answer(f"Не удалось удалить: {resp.text}")
            return
        await message.answer(f"Удалено: #{sub_id}")

    @dp.message(F.text.regexp(r"^/on(@\w+)?(\s|$)"))
    async def enable_subscription(message: Message) -> None:
        await _toggle(message, True)

    @dp.message(F.text.regexp(r"^/off(@\w+)?(\s|$)"))
    async def disable_subscription(message: Message) -> None:
        await _toggle(message, False)

    async def _toggle(message: Message, enabled: bool) -> None:
        parts = message.text.split()
        if parts:
            parts[0] = parts[0].split("@", 1)[0]
        if len(parts) != 2:
            await message.answer("Использование: /on <id> или /off <id>")
            return
        try:
            sub_id = int(parts[1].strip("<>").strip())
        except ValueError:
            await message.answer("ID должен быть числом")
            return

        resp = await call_backend(
            f"/api/v1/bot/subscriptions/{sub_id}/",
            {"chat_id": message.chat.id, "enabled": enabled},
            method="PATCH",
        )
        if resp.status_code >= 300:
            await message.answer(f"Не удалось обновить: {resp.text}")
            return
        data = resp.json()
        status_txt = "включена" if data.get("enabled") else "выключена"
        await message.answer(f"Подписка #{data.get('id')} {status_txt}")

    @dp.message(F.text.regexp(r"^/rps(@\w+)?(\s|$)"))
    async def set_rps(message: Message) -> None:
        parts = message.text.split()
        if parts:
            parts[0] = parts[0].split("@", 1)[0]
        if len(parts) != 3:
            await message.answer("Использование: /rps <id> <1-10>")
            return
        try:
            sub_id = int(parts[1].strip("<>").strip())
            rps = int(parts[2])
        except ValueError:
            await message.answer("ID и RPS должны быть числами")
            return

        resp = await call_backend(
            f"/api/v1/bot/subscriptions/{sub_id}/",
            {"chat_id": message.chat.id, "rps_limit": rps},
            method="PATCH",
        )
        if resp.status_code >= 300:
            await message.answer(f"Не удалось обновить RPS: {resp.text}")
            return
        data = resp.json()
        await message.answer(f"Подписка #{data.get('id')}: rps={data.get('rps_limit')}")

    @dp.message(F.text)
    async def echo(message: Message) -> None:
        await message.answer("Не понял команду. Наберите /start для списка команд.")

    asyncio.create_task(notification_loop())
    if bot is None:
        # If telegram token isn't configured, we still want queue consumer running.
        while True:
            await asyncio.sleep(3600)
    else:
        await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
