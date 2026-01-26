# Запуск через Docker

Рекомендуемый способ запуска. Работает на Windows, Linux, macOS.

## Требования

- Docker Desktop (Windows/Mac) или Docker Engine (Linux)
- Docker Compose v2
- 2 GB RAM минимум
- 10 GB свободного места

---

## Установка Docker

### Windows

1. Скачайте [Docker Desktop](https://www.docker.com/products/docker-desktop/)
2. Установите и перезагрузите компьютер
3. Запустите Docker Desktop
4. Дождитесь пока иконка Docker станет зелёной

**Проверка:**
```powershell
docker --version
docker compose version
```

### macOS

1. Скачайте [Docker Desktop](https://www.docker.com/products/docker-desktop/)
2. Перетащите в Applications
3. Запустите Docker Desktop

**Проверка:**
```bash
docker --version
docker compose version
```

### Linux (Ubuntu/Debian)

```bash
# Установка Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# Перелогиньтесь или выполните
newgrp docker

# Проверка
docker --version
docker compose version
```

### Linux (CentOS/RHEL/Fedora)

```bash
sudo dnf install -y dnf-plugins-core
sudo dnf config-manager --add-repo https://download.docker.com/linux/fedora/docker-ce.repo
sudo dnf install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo systemctl start docker
sudo systemctl enable docker
sudo usermod -aG docker $USER
```

---

## Быстрый старт

### 1. Клонировать репозиторий

```bash
git clone https://github.com/vitalivo/Parser.git
cd Parser
```

### 2. Создать .env файл

```bash
# Linux/Mac
cp .env.example .env

# Windows (PowerShell)
Copy-Item .env.example .env
```

### 3. Настроить .env

Откройте `.env` в текстовом редакторе и укажите:

```env
# ОБЯЗАТЕЛЬНО - токен Telegram бота
BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz

# РЕКОМЕНДУЕТСЯ - прокси для Avito (без него будет 429 ошибка)
WORKER_SOURCE_PROXY=http://user:pass@proxy.example.com:8080
```

**Как получить BOT_TOKEN:**
1. Откройте [@BotFather](https://t.me/BotFather) в Telegram
2. Отправьте `/newbot`
3. Придумайте имя и username для бота
4. Скопируйте токен

### 4. Запустить

```bash
docker compose up -d
```

Первый запуск займёт несколько минут (скачивание образов).

### 5. Проверить статус

```bash
docker compose ps
```

Все сервисы должны быть `Up`:
```
NAME                 STATUS
parser-backend-1     Up
parser-bot-1         Up
parser-postgres-1    Up (healthy)
parser-redis-1       Up (healthy)
parser-scheduler-1   Up
parser-worker-1      Up
```

### 6. Использовать

1. Найдите вашего бота в Telegram по username
2. Отправьте `/start`
3. Нажмите кнопку "📱 iPhone Москва"
4. Готово! Уведомления придут при появлении новых объявлений

---

## Команды управления

### Запуск и остановка

```bash
# Запустить
docker compose up -d

# Остановить
docker compose down

# Перезапустить всё
docker compose restart

# Перезапустить один сервис
docker compose restart bot
docker compose restart worker
```

### Просмотр логов

```bash
# Все логи в реальном времени
docker compose logs -f

# Логи конкретного сервиса
docker compose logs -f bot
docker compose logs -f worker
docker compose logs -f scheduler

# Последние 50 строк
docker compose logs --tail=50 worker
```

### Масштабирование воркеров

```bash
# Запустить 3 воркера (больше параллельных проверок)
docker compose up -d --scale worker=3

# Вернуть к 1 воркеру
docker compose up -d --scale worker=1
```

### Обновление

```bash
git pull
docker compose down
docker compose build
docker compose up -d
```

---

## Django Admin

Админ-панель: http://localhost:8000/admin/

**Логин по умолчанию:**
- Username: `admin`
- Password: `admin`

Здесь можно:
- Смотреть/редактировать подписки
- Управлять пользователями
- Смотреть найденные объявления

---

## Проверка работоспособности

### API Health Check
```bash
curl http://localhost:8000/api/v1/health/
```

### Статистика системы
```bash
curl -H "X-Internal-Token: dev-internal-token" http://localhost:8000/api/v1/internal/stats/
```

### Проверка очередей Redis
```bash
# Количество задач в очереди
docker compose exec redis redis-cli XLEN stream:checks

# Количество уведомлений в очереди
docker compose exec redis redis-cli XLEN stream:notify
```

---

## Решение проблем

### Docker не запускается (Windows)

1. Убедитесь что Docker Desktop запущен (зелёная иконка)
2. Проверьте WSL2: `wsl --status`
3. Если проблема с WSL2:
   ```powershell
   wsl --install
   # Перезагрузите компьютер
   ```

### "Port already in use"

```bash
# Найти процесс на порту 8000
# Windows:
netstat -ano | findstr :8000

# Linux/Mac:
lsof -i :8000
```

Решение: остановите конфликтующий процесс или измените порт в `docker-compose.yml`.

### Бот не отвечает

```bash
# Проверить логи
docker compose logs bot

# Проверить токен
cat .env | grep BOT_TOKEN

# Перезапустить
docker compose restart bot
```

### Avito возвращает 429 (блокировка)

Avito блокирует запросы без прокси. Решение:

1. Получите прокси (например, на pepeproxy.com)
2. Добавьте в `.env`:
   ```env
   WORKER_SOURCE_PROXY=http://user:pass@proxy:port
   ```
3. Перезапустите:
   ```bash
   docker compose down
   docker compose up -d
   ```

См. подробнее: [PROXY.md](PROXY.md)

### Сброс базы данных

```bash
# Полный сброс (удаляет все данные!)
docker compose down -v
docker compose up -d
```

---

## Структура сервисов

| Сервис | Порт | Описание |
|--------|------|----------|
| backend | 8000 | Django API + Admin |
| bot | - | Telegram бот |
| scheduler | - | Планировщик задач |
| worker | - | Парсер объявлений |
| postgres | 5432 | База данных |
| redis | 6379 | Очереди |

---

## Продакшен рекомендации

1. **Измените пароли** в `.env`:
   ```env
   POSTGRES_PASSWORD=сложный_пароль
   DJANGO_SECRET_KEY=случайная_строка_50_символов
   DJANGO_SUPERUSER_PASSWORD=сложный_пароль
   ```

2. **Настройте прокси** — без него Avito блокирует

3. **Бэкапы базы данных**:
   ```bash
   # Создать бэкап
   docker compose exec postgres pg_dump -U parser parser > backup_$(date +%Y%m%d).sql

   # Восстановить
   docker compose exec -T postgres psql -U parser parser < backup.sql
   ```

4. **Автозапуск** при перезагрузке сервера:
   ```bash
   # Linux: добавить в crontab
   @reboot cd /path/to/Parser && docker compose up -d
   ```

---

## Команды бота

| Команда | Описание |
|---------|----------|
| `/start` | Начать + показать кнопки |
| `/add <url>` | Добавить свою ссылку |
| `/list` | Список подписок |
| `/status <id>` | Статус подписки |
| `/del <id>` | Удалить подписку |
| `/on <id>` | Включить |
| `/off <id>` | Выключить |
| `/pause <id> [мин]` | Пауза |
| `/unpause <id>` | Снять паузу |

---

## Следующие шаги

- [PROXY.md](PROXY.md) — настройка прокси
- [CUSTOMIZATION.md](CUSTOMIZATION.md) — добавление городов
- [INSTALL.md](INSTALL.md) — установка без Docker
