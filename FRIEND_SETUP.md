# Запуск у друга (тест в РФ) — быстрый гайд

Цель: друг поднимает проект у себя локально, чтобы проверить реальную ссылку (например, Avito) с «местного» IP и показать результат.

## 0) Важно (про Telegram-бота)
- **Если бот запущен одновременно в двух местах с одним `BOT_TOKEN` — будут конфликты.**
- На время теста бот должен быть запущен **только у друга** (у вас локально контейнер `bot` можно не запускать).

## 1) Что нужно на машине друга
- Docker + Docker Compose.
- Доступ в интернет.

## 2) Как подготовить проект
1) Получить папку с кодом.
2) В корне проекта:
   - `cp .env.example .env`
3) В `.env`:
   - `BOT_TOKEN=...` (ваш токен от BotFather)
   - `INTERNAL_API_TOKEN=dev-internal-token` (оставить как есть)
   - `WORKER_DEMO_MODE=0` (важно для реальных ссылок)

Рекомендация: токен бота лучше передавать отдельным сообщением, а не хранить в архиве.

## 3) Запуск
- `docker compose up -d --build`
- Проверки:
  - `docker compose ps`
  - `curl -sS http://localhost:8000/api/v1/health/ | cat`

## 4) Тест через Telegram (самый простой)
1) Вы (владелец бота) пишете своему боту в Telegram:
   - `/start`
   - `/add <реальная_ссылка> 1`

Подсказки:
- В группах Telegram команды могут выглядеть как `/list@Parser_Bot` — бот это поддерживает.
- ID можно писать как `15` или `<15>`.

Полезные команды:
- `/list` — список подписок
- `/status <id>` — подробный статус (включая `job_id`, задержку задачи и ошибки)
- `/pause <id> [minutes]` и `/unpause <id>` — ручная пауза

2) Если Avito отвечает 429/капча — уведомлений может не быть.

## 5) Быстрая диагностика «интернет есть / Avito блокирует»
На машине друга:
- Проверить статус ответа Avito из контейнера воркера:

`docker compose exec -T worker python -c "import httpx; url='<URL>'; r=httpx.get(url, timeout=10, follow_redirects=True, headers={'User-Agent':'Mozilla/5.0'}); print(r.status_code, len(r.text)); print(r.text[:200].replace('\\n',' '))"`

Интерпретация:
- `200` — доступ есть, дальше уже вопрос парсинга.
- `429/403` — Avito ограничил IP (это не «нет интернета»).
- `RequestError/timeout/DNS` — проблема с сетью/доступом.

- Сводка очередей/воркеров:
  - `curl -sS -H 'X-Internal-Token: dev-internal-token' http://localhost:8000/api/v1/internal/stats/ | cat`

- Метрики:
   - `curl -sS -H 'X-Internal-Token: dev-internal-token' http://localhost:8000/api/v1/internal/metrics/ | cat`
   - Prometheus-формат:
     - `curl -sS -H 'X-Internal-Token: dev-internal-token' http://localhost:8000/api/v1/internal/metrics.prom | cat`

## 5.1) Важно про лимиты (RPS)
Scheduler лимитирует скорость **на пользователя**, а не “на подписку”.

Где менять тариф/лимит пользователя:
- Django Admin → **Telegram профили** → `rps_limit` (1–10).

`rps_limit` у подписки — это вес/приоритет внутри лимита пользователя.

## 6) После теста (безопасность)
Если вы давали токен другу:
- В BotFather сделайте `/revoke` и обновите `BOT_TOKEN` у себя.

## 7) Прогон тестов и покрытие (на машине друга)
В корне репозитория:
- Прогнать все тесты:
   - `bash tests/run_all.sh`

- Сгенерировать HTML-отчёт покрытия:
   - `bash tests/coverage_html.sh`

Артефакты появятся в:
- `artifacts/coverage/backend/htmlcov/index.html`
- `artifacts/coverage/scheduler/htmlcov/index.html`
