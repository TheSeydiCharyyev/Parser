# Настройка прокси

Avito блокирует частые запросы с одного IP (ошибка 429).
Прокси позволяет обойти это ограничение.

---

## Зачем нужен прокси

| Без прокси | С прокси |
|------------|----------|
| HTTP 429 через 5-10 запросов | Стабильная работа |
| Подписки на паузе | Проверка каждые 5 минут |
| Не работает | Работает ✓ |

---

## Где получить прокси

### Рекомендуемые провайдеры

| Провайдер | Тип | Цена | Примечание |
|-----------|-----|------|------------|
| [Pepeproxy](https://pepeproxy.com/) | Резидентные | ~$3/GB | Хорошо работает с Avito |
| [Bright Data](https://brightdata.com/) | Резидентные | ~$10/GB | Премиум качество |
| [Smartproxy](https://smartproxy.com/) | Резидентные | ~$7/GB | Большой пул IP |
| [ProxyLine](https://proxyline.net/) | Datacenter | ~$1/IP | Дешевле, но менее надёжно |

### Требования к прокси

- **Тип:** HTTP/HTTPS (не SOCKS)
- **Локация:** Россия (желательно Москва)
- **Ротация:** Желательно с ротацией IP

---

## Настройка

### 1. Формат прокси

```
http://username:password@host:port
```

Примеры:
```
http://user123:pass456@proxy.example.com:8080
http://abc123:xyz789@ru.smartproxy.com:10000
```

### 2. Добавление в .env

Откройте файл `.env` и добавьте/измените строку:

```env
WORKER_SOURCE_PROXY=http://user:pass@proxy.example.com:8080
```

### 3. Применение изменений

**Docker:**
```bash
docker compose down
docker compose up -d
```

**Без Docker:**
```bash
# Перезапустите worker
sudo systemctl restart parser-worker
```

### 4. Проверка

```bash
# Docker
docker compose logs worker | grep -i proxy

# Или проверьте статус подписки в боте
/status 1
```

Если прокси работает — ошибка `HTTP 429` исчезнет.

---

## Тестирование прокси

### Проверка доступности прокси

```bash
# Linux/Mac
curl -x http://user:pass@proxy:port https://httpbin.org/ip

# Windows PowerShell
Invoke-WebRequest -Proxy "http://user:pass@proxy:port" -Uri "https://httpbin.org/ip"
```

### Проверка работы с Avito

```bash
# Через Docker
docker compose exec worker python -c "
import httpx
import os
proxy = os.environ.get('WORKER_SOURCE_PROXY')
print(f'Proxy: {proxy}')
client = httpx.Client(timeout=30, proxy=proxy)
resp = client.get('https://www.avito.ru/', headers={'User-Agent': 'Mozilla/5.0'})
print(f'Status: {resp.status_code}')
print('OK!' if resp.status_code == 200 else 'FAIL')
"
```

---

## Ротация прокси

### Вариант 1: Провайдер с встроенной ротацией

Большинство резидентных провайдеров автоматически меняют IP при каждом запросе.
Просто используйте их endpoint:

```env
WORKER_SOURCE_PROXY=http://user:pass@rotating.proxy.com:8080
```

### Вариант 2: Несколько воркеров с разными прокси

Создайте несколько `.env` файлов и запустите воркеры с разными прокси:

```bash
# docker-compose.override.yml
services:
  worker-1:
    extends:
      service: worker
    environment:
      WORKER_SOURCE_PROXY: http://user:pass@proxy1:port

  worker-2:
    extends:
      service: worker
    environment:
      WORKER_SOURCE_PROXY: http://user:pass@proxy2:port
```

---

## Решение проблем

### Прокси не работает

1. **Проверьте формат:**
   ```
   http://user:pass@host:port  ✓
   https://user:pass@host:port ✓
   socks5://...               ✗ (не поддерживается)
   ```

2. **Проверьте доступность:**
   ```bash
   curl -x http://user:pass@proxy:port https://google.com
   ```

3. **Проверьте логин/пароль** — спецсимволы нужно URL-encode:
   ```
   pass@word  →  pass%40word
   pass:word  →  pass%3Aword
   ```

### Avito всё ещё блокирует (403/429)

1. **Смените провайдера** — возможно, их IP забанены
2. **Используйте резидентные прокси** вместо datacenter
3. **Выберите российскую локацию** — Avito лучше работает с RU IP
4. **Увеличьте интервал проверки:**
   ```sql
   -- В БД
   UPDATE api_subscription SET check_interval_seconds = 600 WHERE id = 1;
   ```

### Connection timeout

1. **Увеличьте таймаут** в `.env`:
   ```env
   WORKER_SOURCE_TIMEOUT=30
   ```

2. **Проверьте, не блокирует ли файрвол** исходящие соединения на порт прокси

---

## Стоимость

### Расчёт трафика

- 1 проверка Avito ≈ 500 KB
- 1 подписка = 12 проверок/час = 6 MB/час
- 10 подписок = 60 MB/час ≈ 1.4 GB/день

### Примерная стоимость

| Подписок | Трафик/месяц | Стоимость* |
|----------|--------------|------------|
| 10 | ~45 GB | ~$15 |
| 50 | ~225 GB | ~$75 |
| 150 | ~675 GB | ~$200 |

*При цене ~$3/GB резидентных прокси

---

## Альтернативы прокси

### 1. VPN на сервере

Настройте VPN на сервере, чтобы весь трафик шёл через VPN:
```bash
# WireGuard, OpenVPN, etc.
```

Минус: один IP, может быть забанен.

### 2. Tor (не рекомендуется)

Avito активно блокирует Tor exit nodes.

### 3. Мобильный интернет

Используйте мобильный модем с динамическим IP.
Минус: нестабильно, требует физический доступ.

---

## Следующие шаги

- [CUSTOMIZATION.md](CUSTOMIZATION.md) — добавление городов
- [DOCKER.md](DOCKER.md) — запуск через Docker
