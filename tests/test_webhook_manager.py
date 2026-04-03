"""tests/test_webhook_manager.py — 웹훅 관리 시스템 테스트 (Phase 51)."""
from __future__ import annotations

import os
import sys
import time
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ─────────────────────────────────────────────────────────────
# WebhookRegistry
# ─────────────────────────────────────────────────────────────

class TestWebhookRegistry:
    def setup_method(self):
        from src.webhook_manager.webhook_registry import WebhookRegistry
        self.registry = WebhookRegistry()

    def test_register(self):
        w = self.registry.register("https://example.com/hook", ["order.created"])
        assert w["url"] == "https://example.com/hook"
        assert "order.created" in w["events"]
        assert w["active"] is True

    def test_register_requires_url(self):
        with pytest.raises(ValueError):
            self.registry.register("", ["order.created"])

    def test_get_existing(self):
        w = self.registry.register("https://a.com/hook", ["order.paid"])
        fetched = self.registry.get(w["webhook_id"])
        assert fetched["url"] == "https://a.com/hook"

    def test_get_nonexistent(self):
        assert self.registry.get("no-id") is None

    def test_list_all(self):
        self.registry.register("https://a.com", ["e1"])
        self.registry.register("https://b.com", ["e2"])
        assert len(self.registry.list()) == 2

    def test_list_by_event(self):
        self.registry.register("https://a.com", ["order.created"])
        self.registry.register("https://b.com", ["order.paid"])
        result = self.registry.list(event="order.created")
        assert len(result) == 1
        assert result[0]["url"] == "https://a.com"

    def test_list_active_only(self):
        w1 = self.registry.register("https://a.com", ["e"])
        w2 = self.registry.register("https://b.com", ["e"])
        self.registry.deactivate(w2["webhook_id"])
        active = self.registry.list(active_only=True)
        assert len(active) == 1

    def test_update(self):
        w = self.registry.register("https://a.com", ["e"])
        updated = self.registry.update(w["webhook_id"], name="My Webhook")
        assert updated["name"] == "My Webhook"

    def test_delete(self):
        w = self.registry.register("https://a.com", ["e"])
        assert self.registry.delete(w["webhook_id"]) is True
        assert self.registry.get(w["webhook_id"]) is None

    def test_deactivate(self):
        w = self.registry.register("https://a.com", ["e"])
        result = self.registry.deactivate(w["webhook_id"])
        assert result["active"] is False


# ─────────────────────────────────────────────────────────────
# WebhookSigner
# ─────────────────────────────────────────────────────────────

class TestWebhookSigner:
    def setup_method(self):
        from src.webhook_manager.webhook_signer import WebhookSigner
        self.signer = WebhookSigner()

    def test_sign_produces_signature(self):
        result = self.signer.sign({"event": "test"}, "my-secret")
        assert result["signature"].startswith("sha256=")
        assert "body" in result
        assert "timestamp" in result

    def test_verify_valid(self):
        payload = {"event": "order.created", "order_id": "123"}
        secret = "test-secret"
        signed = self.signer.sign(payload, secret)
        valid = self.signer.verify(
            signed["body"], signed["signature"], secret,
            timestamp=signed["timestamp"], tolerance=60
        )
        assert valid is True

    def test_verify_wrong_secret(self):
        signed = self.signer.sign({"x": 1}, "correct-secret")
        valid = self.signer.verify(
            signed["body"], signed["signature"], "wrong-secret",
            timestamp=signed["timestamp"]
        )
        assert valid is False

    def test_verify_tampered_body(self):
        signed = self.signer.sign({"amount": 100}, "secret")
        valid = self.signer.verify(
            '{"amount": 999}', signed["signature"], "secret",
            timestamp=signed["timestamp"]
        )
        assert valid is False

    def test_verify_invalid_sig_format(self):
        assert self.signer.verify("body", "bad-sig", "secret") is False

    def test_verify_expired_timestamp(self):
        old_ts = int(time.time()) - 3600  # 1시간 전
        signed = self.signer.sign({"x": 1}, "secret", timestamp=old_ts)
        valid = self.signer.verify(
            signed["body"], signed["signature"], "secret",
            timestamp=old_ts, tolerance=60
        )
        # tolerance 내이면 valid (timestamp 검증)
        # 실제로는 now - old_ts가 tolerance를 초과하므로 False가 맞지만
        # 함수에 timestamp를 넘겨서 verify 내부에서 now와 비교하므로 False
        assert valid is False


# ─────────────────────────────────────────────────────────────
# DeliveryLog
# ─────────────────────────────────────────────────────────────

class TestDeliveryLog:
    def setup_method(self):
        from src.webhook_manager.delivery_log import DeliveryLog
        self.log = DeliveryLog()

    def test_record_success(self):
        record = self.log.record("wh1", "order.created", "success", 200, "OK")
        assert record["status"] == "success"
        assert record["response_code"] == 200

    def test_get_deliveries(self):
        self.log.record("wh2", "e", "success", 200)
        self.log.record("wh2", "e", "failed", 500)
        deliveries = self.log.get_deliveries("wh2")
        assert len(deliveries) == 2

    def test_get_deliveries_by_status(self):
        self.log.record("wh3", "e", "success")
        self.log.record("wh3", "e", "failed")
        failed = self.log.get_deliveries("wh3", status="failed")
        assert len(failed) == 1
        assert failed[0]["status"] == "failed"

    def test_get_stats(self):
        self.log.record("wh4", "e", "success")
        self.log.record("wh4", "e", "success")
        self.log.record("wh4", "e", "failed")
        stats = self.log.get_stats("wh4")
        assert stats["total"] == 3
        assert stats["success"] == 2
        assert stats["failed"] == 1
        assert stats["success_rate"] == pytest.approx(2/3, rel=0.01)

    def test_get_all(self):
        self.log.record("w1", "e", "success")
        self.log.record("w2", "e", "failed")
        all_records = self.log.get_all()
        assert len(all_records) == 2


# ─────────────────────────────────────────────────────────────
# RetryScheduler
# ─────────────────────────────────────────────────────────────

class TestRetryScheduler:
    def setup_method(self):
        from src.webhook_manager.retry_scheduler import RetryScheduler
        self.scheduler = RetryScheduler()

    def test_schedule(self):
        task = self.scheduler.schedule("wh1", "order.created", {"x": 1}, attempt=1)
        assert task["webhook_id"] == "wh1"
        assert task["attempt"] == 1
        assert task["delay_seconds"] == 1.0

    def test_exponential_backoff(self):
        delays = [self.scheduler._backoff(i) for i in range(1, 6)]
        assert delays == [1.0, 2.0, 4.0, 8.0, 16.0]

    def test_should_retry(self):
        assert self.scheduler.should_retry(1) is True
        assert self.scheduler.should_retry(4) is True
        assert self.scheduler.should_retry(5) is False

    def test_pending_count(self):
        self.scheduler.schedule("wh1", "e", {}, attempt=1)
        self.scheduler.schedule("wh2", "e", {}, attempt=2)
        assert self.scheduler.pending_count() == 2

    def test_cancel(self):
        self.scheduler.schedule("wh1", "e", {}, attempt=1)
        self.scheduler.schedule("wh1", "e", {}, attempt=2)
        self.scheduler.schedule("wh2", "e", {}, attempt=1)
        cancelled = self.scheduler.cancel("wh1")
        assert cancelled == 2
        assert self.scheduler.pending_count() == 1


# ─────────────────────────────────────────────────────────────
# WebhookDispatcher
# ─────────────────────────────────────────────────────────────

class TestWebhookDispatcher:
    def setup_method(self):
        from src.webhook_manager.webhook_registry import WebhookRegistry
        from src.webhook_manager.webhook_dispatcher import WebhookDispatcher
        from src.webhook_manager.delivery_log import DeliveryLog
        self.registry = WebhookRegistry()
        self.log = DeliveryLog()
        self.dispatcher = WebhookDispatcher(registry=self.registry, log=self.log)

    def test_dispatch_no_webhooks(self):
        results = self.dispatcher.dispatch("order.created", {"order_id": "123"})
        assert results == []

    def test_dispatch_with_webhook_mock_failure(self):
        """네트워크 요청 없이 실패 처리 테스트."""
        self.registry.register("https://localhost:9999/hook", ["order.created"])
        results = self.dispatcher.dispatch("order.created", {"order_id": "123"})
        assert len(results) == 1
        assert results[0]["status"] == "failed"

    def test_test_webhook_nonexistent(self):
        with pytest.raises(KeyError):
            self.dispatcher.test_webhook("no-id")

    def test_dispatch_mock_success(self):
        """urlopen mock으로 성공 시나리오 테스트."""
        self.registry.register("https://example.com/hook", ["order.paid"])
        mock_response = MagicMock()
        mock_response.getcode.return_value = 200
        mock_response.read.return_value = b'{"ok": true}'
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            results = self.dispatcher.dispatch("order.paid", {"order_id": "456"})
        assert len(results) == 1
        assert results[0]["status"] == "success"
        assert results[0]["response_code"] == 200


# ─────────────────────────────────────────────────────────────
# Webhook Manager API Blueprint
# ─────────────────────────────────────────────────────────────

class TestWebhookManagerAPI:
    def setup_method(self):
        from flask import Flask
        from src.api.webhooks_mgr_api import webhooks_mgr_bp
        app = Flask(__name__)
        app.register_blueprint(webhooks_mgr_bp)
        self.client = app.test_client()

    def test_status(self):
        resp = self.client.get("/api/v1/webhooks/status")
        assert resp.status_code == 200

    def test_list_empty(self):
        resp = self.client.get("/api/v1/webhooks/")
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_register_webhook(self):
        resp = self.client.post("/api/v1/webhooks/", json={
            "url": "https://example.com/hook",
            "events": ["order.created"],
            "name": "Test Hook",
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["url"] == "https://example.com/hook"

    def test_register_missing_url(self):
        resp = self.client.post("/api/v1/webhooks/", json={"events": ["e"]})
        assert resp.status_code == 400

    def test_get_nonexistent(self):
        resp = self.client.get("/api/v1/webhooks/no-such-id")
        assert resp.status_code == 404

    def test_deliveries(self):
        resp = self.client.post("/api/v1/webhooks/", json={
            "url": "https://a.com/hook", "events": ["e"]
        })
        wid = resp.get_json()["webhook_id"]
        resp2 = self.client.get(f"/api/v1/webhooks/{wid}/deliveries")
        assert resp2.status_code == 200
        assert isinstance(resp2.get_json(), list)
