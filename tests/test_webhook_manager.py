"""tests/test_webhook_manager.py — Phase 51: 웹훅 관리 테스트."""
import json
import pytest
from unittest.mock import patch, MagicMock
from src.webhook_manager.webhook_registry import WebhookRegistry
from src.webhook_manager.webhook_signer import WebhookSigner
from src.webhook_manager.delivery_log import DeliveryLog
from src.webhook_manager.retry_scheduler import RetryScheduler
from src.webhook_manager.webhook_dispatcher import WebhookDispatcher


class TestWebhookRegistry:
    def setup_method(self):
        self.registry = WebhookRegistry()

    def test_register(self):
        wh = self.registry.register('http://example.com', ['order.created'])
        assert wh['url'] == 'http://example.com'
        assert wh['active'] is True
        assert 'id' in wh

    def test_get_webhook(self):
        wh = self.registry.register('http://example.com', ['order.created'])
        found = self.registry.get_webhook(wh['id'])
        assert found is not None

    def test_get_missing(self):
        assert self.registry.get_webhook('no-such') is None

    def test_update_webhook(self):
        wh = self.registry.register('http://example.com', ['order.created'])
        updated = self.registry.update_webhook(wh['id'], active=False)
        assert updated['active'] is False

    def test_delete_webhook(self):
        wh = self.registry.register('http://example.com', ['order.created'])
        assert self.registry.delete_webhook(wh['id']) is True
        assert self.registry.get_webhook(wh['id']) is None

    def test_delete_missing(self):
        assert self.registry.delete_webhook('no-such') is False

    def test_list_webhooks(self):
        self.registry.register('http://a.com', ['e1'])
        self.registry.register('http://b.com', ['e2'])
        assert len(self.registry.list_webhooks()) == 2


class TestWebhookSigner:
    def setup_method(self):
        self.signer = WebhookSigner()

    def test_sign_produces_hex(self):
        sig = self.signer.sign(b'payload', 'secret')
        assert isinstance(sig, str)
        assert len(sig) == 64

    def test_verify_valid(self):
        payload = b'test payload'
        sig = self.signer.sign(payload, 'mysecret')
        assert self.signer.verify(payload, sig, 'mysecret') is True

    def test_verify_invalid(self):
        assert self.signer.verify(b'payload', 'badsig', 'secret') is False

    def test_same_inputs_same_signature(self):
        s1 = self.signer.sign(b'data', 'secret')
        s2 = self.signer.sign(b'data', 'secret')
        assert s1 == s2


class TestDeliveryLog:
    def setup_method(self):
        self.log = DeliveryLog()

    def test_log_success(self):
        record = self.log.log_delivery('wh1', 'order.created', 200, 'ok')
        assert record['success'] is True
        assert record['webhook_id'] == 'wh1'

    def test_log_failure(self):
        record = self.log.log_delivery('wh1', 'order.created', 500, 'error')
        assert record['success'] is False

    def test_get_deliveries(self):
        self.log.log_delivery('wh1', 'e1', 200, 'ok')
        self.log.log_delivery('wh1', 'e2', 201, 'ok')
        self.log.log_delivery('wh2', 'e3', 200, 'ok')
        deliveries = self.log.get_deliveries('wh1')
        assert len(deliveries) == 2

    def test_get_delivery(self):
        record = self.log.log_delivery('wh1', 'e1', 200, 'ok')
        found = self.log.get_delivery(record['id'])
        assert found is not None


class TestRetryScheduler:
    def setup_method(self):
        self.scheduler = RetryScheduler()

    def test_schedule_retry(self):
        entry = self.scheduler.schedule_retry('wh1', 'e1', {}, 1)
        assert entry is not None
        assert entry['delay_seconds'] == 60

    def test_exponential_backoff(self):
        e1 = self.scheduler.schedule_retry('wh1', 'e1', {}, 1)
        e2 = self.scheduler.schedule_retry('wh1', 'e1', {}, 2)
        e3 = self.scheduler.schedule_retry('wh1', 'e1', {}, 3)
        assert e1['delay_seconds'] == 60
        assert e2['delay_seconds'] == 240
        assert e3['delay_seconds'] == 540

    def test_max_retries_exceeded(self):
        entry = self.scheduler.schedule_retry('wh1', 'e1', {}, 6)
        assert entry is None

    def test_get_queue(self):
        self.scheduler.schedule_retry('wh1', 'e1', {}, 1)
        assert len(self.scheduler.get_queue()) == 1


class TestWebhookDispatcher:
    def setup_method(self):
        self.mock_request = MagicMock(return_value=(200, 'ok'))
        self.dispatcher = WebhookDispatcher(request_func=self.mock_request)

    def test_dispatch_success(self):
        wh = self.dispatcher._registry.register('http://example.com', ['order.created'], secret='secret')
        record = self.dispatcher.dispatch(wh['id'], 'order.created', {'order_id': '123'})
        assert record['success'] is True
        assert self.mock_request.called

    def test_dispatch_missing_webhook(self):
        with pytest.raises(KeyError):
            self.dispatcher.dispatch('no-such', 'e1', {})

    def test_dispatch_inactive_webhook(self):
        wh = self.dispatcher._registry.register('http://example.com', ['e1'])
        self.dispatcher._registry.update_webhook(wh['id'], active=False)
        result = self.dispatcher.dispatch(wh['id'], 'e1', {})
        assert result['status'] == 'skipped'

    def test_dispatch_failure_schedules_retry(self):
        self.mock_request.return_value = (500, 'error')
        wh = self.dispatcher._registry.register('http://example.com', ['e1'])
        self.dispatcher.dispatch(wh['id'], 'e1', {})
        assert len(self.dispatcher._retry.get_queue()) > 0
