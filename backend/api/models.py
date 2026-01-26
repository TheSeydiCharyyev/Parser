from __future__ import annotations

from django.conf import settings
from django.db import models

from .validators import validate_http_url_allow_internal


class TariffPlan(models.Model):
    name = models.CharField("Название", max_length=64, unique=True)
    rps_limit = models.PositiveSmallIntegerField("Лимит запросов в секунду", help_text="RPS")
    is_active = models.BooleanField("Активен", default=True)

    created_at = models.DateTimeField("Создано", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        verbose_name = "Тариф"
        verbose_name_plural = "Тарифы"

    def __str__(self) -> str:
        return f"{self.name} ({self.rps_limit} rps)"


class Subscription(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="Пользователь", on_delete=models.CASCADE)

    url = models.CharField(
        "Ссылка",
        max_length=2048,
        validators=[validate_http_url_allow_internal],
    )
    enabled = models.BooleanField("Включена", default=True)

    # v1: храним rps_limit напрямую, чтобы не блокировать ядро на биллинге.
    # Планы (TariffPlan) подключим на этапе кассы/подписок.
    rps_limit = models.PositiveSmallIntegerField(
        "Лимит запросов в секунду",
        default=1,
        help_text="RPS (1–10 в зависимости от тарифа)",
    )

    # Интервал проверки в секундах. Если > 0, используется вместо RPS.
    check_interval_seconds = models.PositiveIntegerField(
        "Интервал проверки (сек)",
        default=0,
        help_text="Если > 0, проверка раз в N секунд вместо RPS. 0 = использовать RPS.",
    )

    # Статусы для демо/админки: чтобы видно было, что мониторинг реально идёт.
    last_check_at = models.DateTimeField("Последняя проверка", null=True, blank=True)
    last_success_at = models.DateTimeField("Последний успешный чек", null=True, blank=True)
    last_item_at = models.DateTimeField("Последняя находка", null=True, blank=True)
    last_error = models.TextField("Последняя ошибка", blank=True, default="")
    consecutive_errors = models.PositiveIntegerField("Ошибок подряд", default=0)

    paused_until = models.DateTimeField("Пауза до", null=True, blank=True)
    pause_reason = models.TextField("Причина паузы", blank=True, default="")

    last_job_id = models.CharField("Последний job_id", max_length=64, blank=True, default="")
    last_job_enqueued_at = models.DateTimeField("Последний job enqueued_at", null=True, blank=True)
    last_job_latency_ms = models.PositiveIntegerField("Последняя задержка job (мс)", null=True, blank=True)

    created_at = models.DateTimeField("Создано", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        verbose_name = "Подписка"
        verbose_name_plural = "Подписки"

    def __str__(self) -> str:
        return f"Подписка #{self.id} (user={self.user_id}, rps={self.rps_limit})"


class Item(models.Model):
    # На будущее: если источников несколько, будет удобно.
    source = models.CharField("Источник", max_length=32, default="generic")
    external_id = models.CharField("Внешний ID", max_length=128)

    url = models.URLField("Ссылка", max_length=2048)
    title = models.CharField("Название", max_length=512, blank=True, default="")
    price = models.BigIntegerField("Цена", null=True, blank=True)
    published_at = models.DateTimeField("Опубликовано", null=True, blank=True)

    raw = models.JSONField("Сырые данные", null=True, blank=True)

    created_at = models.DateTimeField("Создано", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        verbose_name = "Объявление"
        verbose_name_plural = "Объявления"
        constraints = [
            models.UniqueConstraint(fields=["source", "external_id"], name="uniq_item_source_external"),
        ]

    def __str__(self) -> str:
        return f"{self.source}:{self.external_id}"


class SubscriptionItem(models.Model):
    subscription = models.ForeignKey(Subscription, verbose_name="Подписка", on_delete=models.CASCADE)
    item = models.ForeignKey(Item, verbose_name="Объявление", on_delete=models.CASCADE)

    first_seen_at = models.DateTimeField("Впервые увидели", auto_now_add=True)
    notified_at = models.DateTimeField("Уведомлено", null=True, blank=True)

    class Meta:
        verbose_name = "Подписка → объявление"
        verbose_name_plural = "Подписки → объявления"
        constraints = [
            models.UniqueConstraint(fields=["subscription", "item"], name="uniq_subscription_item"),
        ]

    def __str__(self) -> str:
        return f"Подписка #{self.subscription_id} → объявление {self.item_id}"


class TelegramProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, verbose_name="Пользователь", on_delete=models.CASCADE)
    chat_id = models.BigIntegerField("ID чата", unique=True)

    rps_limit = models.PositiveSmallIntegerField(
        "Лимит запросов в секунду (пользователь)",
        default=1,
        help_text="Тариф/лимит клиента (1–10). Используется scheduler'ом как общий RPS на пользователя.",
    )

    created_at = models.DateTimeField("Создано", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        verbose_name = "Telegram профиль"
        verbose_name_plural = "Telegram профили"

    def __str__(self) -> str:
        return f"Telegram {self.chat_id} (user={self.user_id})"
