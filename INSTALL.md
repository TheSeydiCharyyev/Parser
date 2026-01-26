# Установка без Docker

Ручная установка на сервер без использования Docker.
Подходит для VPS, выделенных серверов и локальной разработки.

---

## Требования

- Python 3.12+
- PostgreSQL 14+
- Redis 6+
- Git

---

## Linux (Ubuntu/Debian)

### 1. Установка зависимостей

```bash
# Обновление системы
sudo apt update && sudo apt upgrade -y

# Python 3.12
sudo apt install -y software-properties-common
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt install -y python3.12 python3.12-venv python3.12-dev

# PostgreSQL
sudo apt install -y postgresql postgresql-contrib

# Redis
sudo apt install -y redis-server

# Утилиты
sudo apt install -y git curl
```

### 2. Настройка PostgreSQL

```bash
# Создать пользователя и базу данных
sudo -u postgres psql << EOF
CREATE USER parser WITH PASSWORD 'parser';
CREATE DATABASE parser OWNER parser;
GRANT ALL PRIVILEGES ON DATABASE parser TO parser;
EOF

# Проверка подключения
psql -U parser -d parser -h localhost -c "SELECT 1;"
```

### 3. Настройка Redis

```bash
# Redis уже работает после установки
# Проверка
redis-cli ping
# Должен ответить: PONG
```

### 4. Клонирование проекта

```bash
cd /opt
sudo git clone https://github.com/vitalivo/Parser.git
sudo chown -R $USER:$USER Parser
cd Parser
```

### 5. Создание виртуального окружения

```bash
python3.12 -m venv venv
source venv/bin/activate

# Установка зависимостей для каждого сервиса
pip install -r backend/requirements.txt
pip install -r bot/requirements.txt
pip install -r scheduler/requirements.txt
pip install -r worker/requirements.txt
```

### 6. Настройка окружения

```bash
cp .env.example .env
nano .env
```

Измените:
```env
# Подключение к локальным сервисам
POSTGRES_HOST=localhost
REDIS_HOST=localhost

# Telegram бот
BOT_TOKEN=ваш_токен

# Прокси (рекомендуется)
WORKER_SOURCE_PROXY=http://user:pass@proxy:port
```

### 7. Миграции базы данных

```bash
source venv/bin/activate
cd backend
python manage.py migrate
python manage.py createsuperuser
```

### 8. Запуск сервисов

Откройте 4 терминала (или используйте tmux/screen):

**Терминал 1 — Backend:**
```bash
cd /opt/Parser
source venv/bin/activate
cd backend
python manage.py runserver 0.0.0.0:8000
```

**Терминал 2 — Bot:**
```bash
cd /opt/Parser
source venv/bin/activate
cd bot
python main.py
```

**Терминал 3 — Scheduler:**
```bash
cd /opt/Parser
source venv/bin/activate
cd scheduler
python main.py
```

**Терминал 4 — Worker:**
```bash
cd /opt/Parser
source venv/bin/activate
cd worker
python main.py
```

### 9. Настройка systemd (автозапуск)

Создайте файлы сервисов:

**Backend** (`/etc/systemd/system/parser-backend.service`):
```ini
[Unit]
Description=Parser Backend
After=network.target postgresql.service redis.service

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/Parser/backend
Environment="PATH=/opt/Parser/venv/bin"
EnvironmentFile=/opt/Parser/.env
ExecStart=/opt/Parser/venv/bin/python manage.py runserver 0.0.0.0:8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

**Bot** (`/etc/systemd/system/parser-bot.service`):
```ini
[Unit]
Description=Parser Telegram Bot
After=network.target parser-backend.service

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/Parser/bot
Environment="PATH=/opt/Parser/venv/bin"
EnvironmentFile=/opt/Parser/.env
ExecStart=/opt/Parser/venv/bin/python main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

**Scheduler** (`/etc/systemd/system/parser-scheduler.service`):
```ini
[Unit]
Description=Parser Scheduler
After=network.target parser-backend.service

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/Parser/scheduler
Environment="PATH=/opt/Parser/venv/bin"
EnvironmentFile=/opt/Parser/.env
ExecStart=/opt/Parser/venv/bin/python main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

**Worker** (`/etc/systemd/system/parser-worker.service`):
```ini
[Unit]
Description=Parser Worker
After=network.target parser-backend.service

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/Parser/worker
Environment="PATH=/opt/Parser/venv/bin"
EnvironmentFile=/opt/Parser/.env
ExecStart=/opt/Parser/venv/bin/python main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Активация:
```bash
sudo systemctl daemon-reload
sudo systemctl enable parser-backend parser-bot parser-scheduler parser-worker
sudo systemctl start parser-backend parser-bot parser-scheduler parser-worker

# Проверка статуса
sudo systemctl status parser-backend
sudo systemctl status parser-bot
```

---

## Windows

### 1. Установка Python

1. Скачайте [Python 3.12](https://www.python.org/downloads/)
2. При установке отметьте "Add Python to PATH"
3. Проверьте: `python --version`

### 2. Установка PostgreSQL

1. Скачайте [PostgreSQL](https://www.postgresql.org/download/windows/)
2. Установите с pgAdmin
3. Создайте базу данных `parser` и пользователя `parser`

### 3. Установка Redis

**Вариант 1 — Memurai (рекомендуется):**
1. Скачайте [Memurai](https://www.memurai.com/)
2. Установите как сервис

**Вариант 2 — WSL:**
```powershell
wsl --install
# После перезагрузки в WSL:
sudo apt install redis-server
sudo service redis-server start
```

### 4. Клонирование и настройка

```powershell
cd C:\Projects
git clone https://github.com/vitalivo/Parser.git
cd Parser

# Виртуальное окружение
python -m venv venv
.\venv\Scripts\activate

# Установка зависимостей
pip install -r backend\requirements.txt
pip install -r bot\requirements.txt
pip install -r scheduler\requirements.txt
pip install -r worker\requirements.txt
```

### 5. Настройка .env

```powershell
Copy-Item .env.example .env
notepad .env
```

Измените:
```env
POSTGRES_HOST=localhost
REDIS_HOST=localhost
BOT_TOKEN=ваш_токен
```

### 6. Миграции

```powershell
cd backend
python manage.py migrate
python manage.py createsuperuser
```

### 7. Запуск (4 окна PowerShell)

**Окно 1:**
```powershell
cd C:\Projects\Parser
.\venv\Scripts\activate
cd backend
python manage.py runserver 0.0.0.0:8000
```

**Окно 2:**
```powershell
cd C:\Projects\Parser
.\venv\Scripts\activate
cd bot
python main.py
```

**Окно 3:**
```powershell
cd C:\Projects\Parser
.\venv\Scripts\activate
cd scheduler
python main.py
```

**Окно 4:**
```powershell
cd C:\Projects\Parser
.\venv\Scripts\activate
cd worker
python main.py
```

### 8. Автозапуск (Task Scheduler)

1. Откройте Task Scheduler
2. Create Basic Task для каждого сервиса
3. Trigger: At startup
4. Action: Start a program
   - Program: `C:\Projects\Parser\venv\Scripts\python.exe`
   - Arguments: `main.py`
   - Start in: `C:\Projects\Parser\bot` (или другой сервис)

---

## macOS

### 1. Установка через Homebrew

```bash
# Homebrew
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Python, PostgreSQL, Redis
brew install python@3.12 postgresql@16 redis

# Запуск сервисов
brew services start postgresql@16
brew services start redis
```

### 2. Настройка PostgreSQL

```bash
createuser -s parser
createdb -O parser parser
```

### 3. Клонирование и настройка

```bash
cd ~/Projects
git clone https://github.com/vitalivo/Parser.git
cd Parser

# Виртуальное окружение
python3.12 -m venv venv
source venv/bin/activate

# Зависимости
pip install -r backend/requirements.txt
pip install -r bot/requirements.txt
pip install -r scheduler/requirements.txt
pip install -r worker/requirements.txt
```

### 4. Настройка .env

```bash
cp .env.example .env
nano .env
```

```env
POSTGRES_HOST=localhost
REDIS_HOST=localhost
BOT_TOKEN=ваш_токен
```

### 5. Запуск

Используйте 4 терминала или tmux:

```bash
# Терминал 1
cd ~/Projects/Parser && source venv/bin/activate && cd backend && python manage.py runserver

# Терминал 2
cd ~/Projects/Parser && source venv/bin/activate && cd bot && python main.py

# Терминал 3
cd ~/Projects/Parser && source venv/bin/activate && cd scheduler && python main.py

# Терминал 4
cd ~/Projects/Parser && source venv/bin/activate && cd worker && python main.py
```

### 6. Автозапуск (launchd)

Создайте plist файлы в `~/Library/LaunchAgents/`:

**com.parser.backend.plist:**
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.parser.backend</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/YOU/Projects/Parser/venv/bin/python</string>
        <string>manage.py</string>
        <string>runserver</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/YOU/Projects/Parser/backend</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
```

Загрузка:
```bash
launchctl load ~/Library/LaunchAgents/com.parser.backend.plist
```

---

## Проверка работы

После запуска всех сервисов:

1. Откройте http://localhost:8000/admin/
2. Найдите бота в Telegram
3. Отправьте `/start`

---

## Следующие шаги

- [PROXY.md](PROXY.md) — настройка прокси
- [CUSTOMIZATION.md](CUSTOMIZATION.md) — добавление городов
