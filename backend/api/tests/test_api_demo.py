import time

import redis
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from api.models import Subscription


@override_settings(REDIS_DB=15, INTERNAL_API_TOKEN="")
class ApiDemoTests(TestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.chat_id = 111111

        self.redis = redis.Redis(host="redis", port=6379, db=15, decode_responses=True)
        self.redis.flushdb()

    def _register_chat(self) -> None:
        resp = self.client.post(
            "/api/v1/bot/register/",
            {"chat_id": self.chat_id, "username": f"tg_{self.chat_id}"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)

    def _create_subscription(self) -> dict:
        self._register_chat()
        resp = self.client.post(
            "/api/v1/bot/subscriptions/",
            {
                "chat_id": self.chat_id,
                "url": "http://backend:8000/api/v1/demo/source/dynamic/?q=test",
                "rps_limit": 1,
                "enabled": True,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        return resp.json()

    def test_pause_unpause_and_status(self):
        sub = self._create_subscription()
        sub_id = sub["id"]

        pause = self.client.post(
            f"/api/v1/bot/subscriptions/{sub_id}/pause/",
            {"chat_id": self.chat_id, "minutes": 5},
            format="json",
        )
        self.assertEqual(pause.status_code, 200, pause.content)
        paused = pause.json()
        self.assertTrue(paused.get("paused_until"))
        self.assertIn("manual_pause", (paused.get("pause_reason") or ""))

        status = self.client.get(
            f"/api/v1/bot/subscriptions/{sub_id}/",
            {"chat_id": self.chat_id},
        )
        self.assertEqual(status.status_code, 200, status.content)
        self.assertTrue(status.json().get("paused_until"))

        unpause = self.client.post(
            f"/api/v1/bot/subscriptions/{sub_id}/unpause/",
            {"chat_id": self.chat_id},
            format="json",
        )
        self.assertEqual(unpause.status_code, 200, unpause.content)
        self.assertIsNone(unpause.json().get("paused_until"))

    def test_worker_job_tracing_and_metrics(self):
        sub = self._create_subscription()
        sub_id = sub["id"]

        job_id = "demo_job_123"
        enqueued_at = time.time() - 0.2

        report = self.client.post(
            "/api/v1/worker/report/",
            {"subscription_id": sub_id, "items": [], "job_id": job_id, "enqueued_at": enqueued_at},
            format="json",
        )
        self.assertEqual(report.status_code, 200, report.content)

        s = Subscription.objects.get(id=sub_id)
        self.assertEqual(s.last_job_id, job_id)
        self.assertIsNotNone(s.last_job_latency_ms)
        self.assertGreaterEqual(int(s.last_job_latency_ms or 0), 0)

        metrics = self.client.get("/api/v1/internal/metrics/")
        self.assertEqual(metrics.status_code, 200, metrics.content)
        data = metrics.json()
        counters = data.get("counters") or {}
        self.assertGreaterEqual(int(counters.get("worker_report_total") or 0), 1)

        prom = self.client.get("/api/v1/internal/metrics.prom")
        self.assertEqual(prom.status_code, 200, prom.content)
        text = prom.content.decode("utf-8", errors="replace")
        self.assertIn("parser_worker_report_total", text)

    def test_auto_pause_on_429_failed_check(self):
        sub = self._create_subscription()
        sub_id = sub["id"]

        failed = self.client.post(
            "/api/v1/worker/check_failed/",
            {"subscription_id": sub_id, "error": "HTTP 429 от источника", "job_id": "x", "enqueued_at": time.time()},
            format="json",
        )
        self.assertEqual(failed.status_code, 200, failed.content)

        s = Subscription.objects.get(id=sub_id)
        self.assertIsNotNone(s.paused_until)
        self.assertIn("auto_pause", (s.pause_reason or ""))
        self.assertGreaterEqual(int(s.consecutive_errors or 0), 1)

        metrics = self.client.get("/api/v1/internal/metrics/")
        data = metrics.json()
        counters = data.get("counters") or {}
        self.assertGreaterEqual(int(counters.get("worker_check_failed_total") or 0), 1)
        self.assertGreaterEqual(int(counters.get("errors_total") or 0), 1)
