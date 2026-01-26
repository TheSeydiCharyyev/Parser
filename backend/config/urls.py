from django.contrib import admin
from django.urls import include, path

from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter

from api.views import (
    SubscriptionViewSet,
    bot_create_subscription,
    bot_notification,
    bot_register,
    bot_subscription_detail,
    bot_subscription_pause,
    bot_subscription_unpause,
    demo_source,
    demo_source_dynamic,
    health,
    internal_metrics,
    internal_metrics_prom,
    internal_stats,
    worker_check_failed,
    worker_report,
)

router = DefaultRouter()
router.register(r"subscriptions", SubscriptionViewSet, basename="subscription")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/health/", health, name="health"),
    path("api/v1/internal/stats/", internal_stats, name="internal_stats"),
    path("api/v1/internal/metrics/", internal_metrics, name="internal_metrics"),
    path("api/v1/internal/metrics.prom", internal_metrics_prom, name="internal_metrics_prom"),
    path("api/v1/demo/source/", demo_source, name="demo_source"),
    path("api/v1/demo/source/dynamic/", demo_source_dynamic, name="demo_source_dynamic"),
    path("api/v1/worker/report/", worker_report, name="worker_report"),
    path("api/v1/worker/check_failed/", worker_check_failed, name="worker_check_failed"),
    path("api/v1/bot/register/", bot_register, name="bot_register"),
    path("api/v1/bot/subscriptions/", bot_create_subscription, name="bot_create_subscription"),
    path(
        "api/v1/bot/subscriptions/<int:subscription_id>/",
        bot_subscription_detail,
        name="bot_subscription_detail",
    ),
    path(
        "api/v1/bot/subscriptions/<int:subscription_id>/pause/",
        bot_subscription_pause,
        name="bot_subscription_pause",
    ),
    path(
        "api/v1/bot/subscriptions/<int:subscription_id>/unpause/",
        bot_subscription_unpause,
        name="bot_subscription_unpause",
    ),
    path("api/v1/bot/notification/", bot_notification, name="bot_notification"),
    path("api/v1/", include(router.urls)),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
]
