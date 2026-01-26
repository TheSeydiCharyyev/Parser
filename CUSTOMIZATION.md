# Кастомизация бота

Как добавить новые города, категории и изменить интерфейс бота.

---

## Добавление новых городов/кнопок

### Где находится код

Файл: `bot/main.py`

Найдите секцию `QUICK_SUBSCRIPTIONS`:

```python
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
```

### Как добавить новый город

1. **Найдите URL на Avito:**
   - Откройте avito.ru
   - Выберите город и категорию
   - Введите поисковый запрос
   - Скопируйте URL из браузера

2. **Добавьте в `QUICK_SUBSCRIPTIONS`:**

```python
QUICK_SUBSCRIPTIONS = {
    # Существующие...
    "iphone_msk": {
        "name": "📱 iPhone Москва",
        "url": "https://www.avito.ru/moskva/telefony?q=iphone",
        "enabled": True,
    },
    "iphone_spb": {
        "name": "📱 iPhone СПб",
        "url": "https://www.avito.ru/sankt-peterburg/telefony?q=iphone",
        "enabled": True,  # Включили!
    },

    # Новые города:
    "iphone_ekb": {
        "name": "📱 iPhone Екатеринбург",
        "url": "https://www.avito.ru/ekaterinburg/telefony?q=iphone",
        "enabled": True,
    },
    "iphone_nsk": {
        "name": "📱 iPhone Новосибирск",
        "url": "https://www.avito.ru/novosibirsk/telefony?q=iphone",
        "enabled": True,
    },
    "iphone_kzn": {
        "name": "📱 iPhone Казань",
        "url": "https://www.avito.ru/kazan/telefony?q=iphone",
        "enabled": True,
    },
}
```

3. **Пересоберите и перезапустите бота:**

```bash
# Docker
docker compose build bot
docker compose up -d bot

# Без Docker
sudo systemctl restart parser-bot
```

---

## Добавление других категорий

### Примеры категорий

```python
QUICK_SUBSCRIPTIONS = {
    # Телефоны
    "iphone_msk": {
        "name": "📱 iPhone Москва",
        "url": "https://www.avito.ru/moskva/telefony?q=iphone",
        "enabled": True,
    },
    "samsung_msk": {
        "name": "📱 Samsung Москва",
        "url": "https://www.avito.ru/moskva/telefony?q=samsung",
        "enabled": True,
    },

    # Ноутбуки
    "macbook_msk": {
        "name": "💻 MacBook Москва",
        "url": "https://www.avito.ru/moskva/noutbuki?q=macbook",
        "enabled": True,
    },

    # Авто
    "bmw_msk": {
        "name": "🚗 BMW Москва",
        "url": "https://www.avito.ru/moskva/avtomobili/bmw",
        "enabled": True,
    },

    # Недвижимость
    "kvartira_msk": {
        "name": "🏠 Квартиры Москва",
        "url": "https://www.avito.ru/moskva/kvartiry/sdam",
        "enabled": True,
    },
}
```

---

## Изменение интервала проверки

По умолчанию: **5 минут** (300 секунд)

### Глобально (для всех новых подписок)

В `bot/main.py` найдите строку:
```python
"check_interval_seconds": 300,  # 5 минут
```

Измените на нужное значение:
- 60 = 1 минута
- 300 = 5 минут
- 600 = 10 минут
- 1800 = 30 минут

### Для конкретной подписки (через БД)

```bash
# Docker
docker compose exec postgres psql -U parser -d parser -c "
UPDATE api_subscription SET check_interval_seconds = 600 WHERE id = 1;
"

# Без Docker
psql -U parser -d parser -c "
UPDATE api_subscription SET check_interval_seconds = 600 WHERE id = 1;
"
```

---

## Изменение текста приветствия

В `bot/main.py` найдите функцию `start`:

```python
@dp.message(CommandStart())
async def start(message: Message) -> None:
    # ...
    await message.answer(
        "👋 Привет! Я бот для отслеживания объявлений на Avito.\n\n"
        "🚀 Быстрый старт — выберите подписку:",
        reply_markup=get_quick_keyboard()
    )
```

Измените текст на свой:

```python
    await message.answer(
        "🔥 Добро пожаловать в ParserBot!\n\n"
        "Я помогу найти лучшие предложения на Avito.\n"
        "Выберите что искать:",
        reply_markup=get_quick_keyboard()
    )
```

---

## Изменение формата уведомлений

Формат уведомлений настраивается в `backend/api/views.py`.

Найдите endpoint `/api/v1/bot/notification/` и измените шаблон текста.

---

## Добавление эмодзи к кнопкам

```python
QUICK_SUBSCRIPTIONS = {
    "iphone_msk": {
        "name": "📱 iPhone Москва",  # Эмодзи в начале
        ...
    },
    "macbook_msk": {
        "name": "💻 MacBook Москва",
        ...
    },
    "auto_msk": {
        "name": "🚗 Авто Москва",
        ...
    },
}
```

Популярные эмодзи:
- 📱 Телефоны
- 💻 Ноутбуки/ПК
- 🚗 Авто
- 🏠 Недвижимость
- 👕 Одежда
- 🎮 Игры/Консоли
- 📺 Электроника
- 🛋️ Мебель

---

## Города Avito (URL slugs)

| Город | URL slug |
|-------|----------|
| Москва | moskva |
| Санкт-Петербург | sankt-peterburg |
| Екатеринбург | ekaterinburg |
| Новосибирск | novosibirsk |
| Казань | kazan |
| Нижний Новгород | nizhniy_novgorod |
| Челябинск | chelyabinsk |
| Самара | samara |
| Ростов-на-Дону | rostov-na-donu |
| Уфа | ufa |
| Красноярск | krasnoyarsk |
| Пермь | perm |
| Воронеж | voronezh |
| Волгоград | volgograd |
| Краснодар | krasnodar |

Полный формат URL:
```
https://www.avito.ru/{город}/{категория}?q={запрос}
```

---

## Категории Avito (URL paths)

| Категория | URL path |
|-----------|----------|
| Телефоны | telefony |
| Ноутбуки | noutbuki |
| Компьютеры | nastolnye_kompyutery |
| Планшеты | planshety |
| Фото/Видео | foto_i_videokamery |
| Игровые приставки | igry_pristavki_i_programmy |
| Авто | avtomobili |
| Квартиры (аренда) | kvartiry/sdam |
| Квартиры (продажа) | kvartiry/prodam |
| Одежда | odezhda_obuv_aksessuary |
| Мебель | mebel_i_interer |
| Бытовая техника | bytovaya_tehnika |

---

## Полный пример кастомизации

```python
# bot/main.py

QUICK_SUBSCRIPTIONS = {
    # === ТЕЛЕФОНЫ ===
    "iphone_msk": {
        "name": "📱 iPhone Москва",
        "url": "https://www.avito.ru/moskva/telefony?q=iphone",
        "enabled": True,
    },
    "iphone_spb": {
        "name": "📱 iPhone СПб",
        "url": "https://www.avito.ru/sankt-peterburg/telefony?q=iphone",
        "enabled": True,
    },
    "samsung_msk": {
        "name": "📱 Samsung Москва",
        "url": "https://www.avito.ru/moskva/telefony?q=samsung+galaxy",
        "enabled": True,
    },

    # === НОУТБУКИ ===
    "macbook_msk": {
        "name": "💻 MacBook Москва",
        "url": "https://www.avito.ru/moskva/noutbuki?q=macbook",
        "enabled": True,
    },

    # === ИГРЫ ===
    "ps5_msk": {
        "name": "🎮 PS5 Москва",
        "url": "https://www.avito.ru/moskva/igry_pristavki_i_programmy?q=playstation+5",
        "enabled": True,
    },

    # === СКОРО ===
    "auto_msk": {
        "name": "🚗 Авто Москва (скоро)",
        "url": "https://www.avito.ru/moskva/avtomobili",
        "enabled": False,
    },
}
```

---

## После изменений

Не забудьте пересобрать и перезапустить:

```bash
# Docker
docker compose build bot
docker compose up -d bot

# Без Docker
sudo systemctl restart parser-bot
```

---

## Следующие шаги

- [PROXY.md](PROXY.md) — настройка прокси
- [DOCKER.md](DOCKER.md) — запуск через Docker
- [INSTALL.md](INSTALL.md) — установка без Docker
