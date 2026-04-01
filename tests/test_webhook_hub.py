"""tests/test_webhook_hub.py — WebhookHub, WebhookValidator, RetryQueue 테스트."""
import hashlib
import hmac
import base64
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


@pytest.fixture(autouse=True)
def reset_hub():
    """각 테스트 전에 모듈 레벨 싱글턴 허브 핸들러를 초기화한다."""
    import src.webhooks.hub as hub_module
    hub_module.hub._handlers.clear()
    yield hub_module.hub


class TestWebhookHub:
    def test_register_and_dispatch(self):
        """핸들러 등록 후 dispatch하면 핸들러가 호출되어야 한다."""
        from src.webhooks.hub import WebhookHub
        hub = WebhookHub()
        results = []
        hub.register_handler("shopify", "order/created", lambda p: results.append(p))
        hub.dispatch("shopify", "order/created", {"order_id": "123"})
        assert len(results) == 1
        assert results[0]["order_id"] == "123"

    def test_dispatch_unknown_platform(self):
        """등록되지 않은 플랫폼은 빈 리스트를 반환해야 한다."""
        from src.webhooks.hub import WebhookHub
        hub = WebhookHub()
        result = hub.dispatch("unknown_platform", "event", {})
        assert result == []

    def test_multiple_handlers(self):
        """여러 핸들러가 모두 호출되어야 한다."""
        from src.webhooks.hub import WebhookHub
        hub = WebhookHub()
        calls = []
        hub.register_handler("test", "evt", lambda p: calls.append("h1"))
        hub.register_handler("test", "evt", lambda p: calls.append("h2"))
        hub.dispatch("test", "evt", {})
        assert "h1" in calls
        assert "h2" in calls

    def test_handler_exception_does_not_stop_others(self):
        """한 핸들러가 예외를 발생시켜도 다른 핸들러는 실행되어야 한다."""
        from src.webhooks.hub import WebhookHub
        hub = WebhookHub()
        calls = []

        def bad_handler(p):
            raise ValueError("테스트 오류")

        hub.register_handler("test", "evt", bad_handler)
        hub.register_handler("test", "evt", lambda p: calls.append("ok"))
        hub.dispatch("test", "evt", {})
        assert "ok" in calls

    def test_get_handlers(self):
        """get_handlers는 등록된 핸들러 리스트를 반환해야 한다."""
        from src.webhooks.hub import WebhookHub
        hub = WebhookHub()

        def fn(p):
            return None
        hub.register_handler("p", "e", fn)
        handlers = hub.get_handlers("p", "e")
        assert fn in handlers


class TestWebhookValidator:
    def test_validator_shopify_valid(self):
        """유효한 Shopify HMAC 서명은 통과해야 한다."""
        from src.webhooks.validators import WebhookValidator
        validator = WebhookValidator()
        secret = "test_secret"
        body = b'{"order": "test"}'
        sig = base64.b64encode(
            hmac.new(secret.encode(), body, hashlib.sha256).digest()
        ).decode()
        ok, msg = validator.validate("shopify", {
            "headers": {"X-Shopify-Hmac-Sha256": sig},
            "body": body,
            "secret": secret,
        })
        assert ok is True

    def test_validator_shopify_invalid(self):
        """잘못된 Shopify HMAC 서명은 실패해야 한다."""
        from src.webhooks.validators import WebhookValidator
        validator = WebhookValidator()
        ok, msg = validator.validate("shopify", {
            "headers": {"X-Shopify-Hmac-Sha256": "invalid_sig"},
            "body": b'{"order": "test"}',
            "secret": "test_secret",
        })
        assert ok is False

    def test_validator_unknown_platform(self):
        """알 수 없는 플랫폼은 False를 반환해야 한다."""
        from src.webhooks.validators import WebhookValidator
        validator = WebhookValidator()
        ok, msg = validator.validate("unknown", {})
        assert ok is False
        assert "지원하지 않는 플랫폼" in msg

    def test_validator_telegram_valid(self, monkeypatch):
        """유효한 Telegram 토큰은 통과해야 한다."""
        from src.webhooks.validators import WebhookValidator
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "valid_token_123")
        validator = WebhookValidator()
        ok, msg = validator.validate("telegram", {"token": "valid_token_123"})
        assert ok is True

    def test_validator_telegram_invalid(self, monkeypatch):
        """잘못된 Telegram 토큰은 실패해야 한다."""
        from src.webhooks.validators import WebhookValidator
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "real_token")
        validator = WebhookValidator()
        ok, msg = validator.validate("telegram", {"token": "wrong_token"})
        assert ok is False


class TestRetryQueue:
    def test_retry_queue_enqueue(self):
        """enqueue는 항목 ID를 반환하고 큐에 추가해야 한다."""
        from src.webhooks.retry_queue import RetryQueue
        q = RetryQueue()
        item_id = q.enqueue("shopify", "order/created", {"data": 1})
        assert isinstance(item_id, str)
        assert q.get_stats()["pending"] == 1

    def test_retry_queue_process(self):
        """process는 처리 가능한 항목을 디스패치해야 한다."""
        from src.webhooks.hub import WebhookHub
        from src.webhooks.retry_queue import RetryQueue
        hub = WebhookHub()
        results = []
        hub.register_handler("shopify", "order/created", lambda p: results.append(p))
        q = RetryQueue()
        q.enqueue("shopify", "order/created", {"data": 1})
        count = q.process(hub)
        assert count == 1
        assert len(results) == 1

    def test_retry_queue_get_pending(self):
        """get_pending은 대기 중인 항목 리스트를 반환해야 한다."""
        from src.webhooks.retry_queue import RetryQueue
        q = RetryQueue()
        q.enqueue("p", "e", {})
        q.enqueue("p", "e", {})
        pending = q.get_pending()
        assert len(pending) == 2

    def test_retry_queue_get_stats(self):
        """get_stats는 pending 수와 max_retries를 반환해야 한다."""
        from src.webhooks.retry_queue import RetryQueue
        q = RetryQueue()
        stats = q.get_stats()
        assert "pending" in stats
        assert "max_retries" in stats
