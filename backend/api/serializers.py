from __future__ import annotations

from rest_framework import serializers

from .validators import validate_http_url_allow_internal

from .models import Item, Subscription


class SubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subscription
        fields = (
            "id",
            "url",
            "enabled",
            "rps_limit",
            "check_interval_seconds",
            "last_check_at",
            "last_success_at",
            "last_item_at",
            "last_error",
            "consecutive_errors",
            "paused_until",
            "pause_reason",
            "last_job_id",
            "last_job_enqueued_at",
            "last_job_latency_ms",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "last_check_at",
            "last_success_at",
            "last_item_at",
            "last_error",
            "consecutive_errors",
            "paused_until",
            "pause_reason",
            "last_job_id",
            "last_job_enqueued_at",
            "last_job_latency_ms",
            "created_at",
            "updated_at",
        )


class WorkerItemIn(serializers.Serializer):
    source = serializers.CharField(required=False, default="generic")
    external_id = serializers.CharField()
    url = serializers.URLField()
    title = serializers.CharField(required=False, allow_blank=True, default="")
    price = serializers.IntegerField(required=False, allow_null=True)
    published_at = serializers.DateTimeField(required=False, allow_null=True)
    raw = serializers.JSONField(required=False, allow_null=True)


class WorkerReportIn(serializers.Serializer):
    job_id = serializers.CharField(required=False, allow_blank=False)
    enqueued_at = serializers.FloatField(required=False)
    subscription_id = serializers.IntegerField()
    items = WorkerItemIn(many=True)


class WorkerCheckFailedIn(serializers.Serializer):
    job_id = serializers.CharField(required=False, allow_blank=False)
    enqueued_at = serializers.FloatField(required=False)
    subscription_id = serializers.IntegerField()
    error = serializers.CharField()


class WorkerNewItemOut(serializers.ModelSerializer):
    class Meta:
        model = Item
        fields = ("id", "source", "external_id", "url", "title", "price", "published_at")


class BotRegisterIn(serializers.Serializer):
    chat_id = serializers.IntegerField()
    username = serializers.CharField(required=False, allow_blank=True)


class BotSubscriptionCreateIn(serializers.Serializer):
    chat_id = serializers.IntegerField()
    url = serializers.CharField(validators=[validate_http_url_allow_internal])
    rps_limit = serializers.IntegerField(required=False, default=1, min_value=1, max_value=10)
    check_interval_seconds = serializers.IntegerField(required=False, default=0, min_value=0)
    enabled = serializers.BooleanField(required=False, default=True)


class BotChatIn(serializers.Serializer):
    chat_id = serializers.IntegerField()


class BotSubscriptionUpdateIn(serializers.Serializer):
    chat_id = serializers.IntegerField()
    enabled = serializers.BooleanField(required=False)
    rps_limit = serializers.IntegerField(required=False, min_value=1, max_value=10)
    check_interval_seconds = serializers.IntegerField(required=False, min_value=0)


class BotPauseIn(serializers.Serializer):
    chat_id = serializers.IntegerField()
    minutes = serializers.IntegerField(required=False, min_value=1, max_value=24 * 60)


class BotNotificationOut(serializers.Serializer):
    chat_id = serializers.IntegerField()
    text = serializers.CharField()
