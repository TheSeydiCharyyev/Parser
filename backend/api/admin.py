from django.contrib import admin

from .models import Item, Subscription, SubscriptionItem, TariffPlan, TelegramProfile


admin.site.site_header = "Панель управления"
admin.site.site_title = "Админка"
admin.site.index_title = "Управление сервисом"


@admin.register(TariffPlan)
class TariffPlanAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "rps_limit", "is_active", "created_at")
    search_fields = ("name",)


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "enabled",
        "rps_limit",
        "paused_until",
        "last_job_id",
        "last_job_latency_ms",
        "last_check_at",
        "last_success_at",
        "last_item_at",
        "consecutive_errors",
        "url",
        "created_at",
    )
    list_filter = ("enabled", "rps_limit")
    search_fields = ("url",)


@admin.register(TelegramProfile)
class TelegramProfileAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "chat_id", "rps_limit", "created_at")
    list_filter = ("rps_limit",)
    search_fields = ("chat_id", "user__username")


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ("id", "source", "external_id", "price", "published_at", "created_at")
    list_filter = ("source",)
    search_fields = ("external_id", "url", "title")


@admin.register(SubscriptionItem)
class SubscriptionItemAdmin(admin.ModelAdmin):
    list_display = ("id", "subscription", "item", "first_seen_at", "notified_at")
    list_filter = ("notified_at",)
