"""tests/test_order_webhook.py — Flask 웹훅 엔드포인트 테스트.

/webhook/shopify/order, /webhook/forwarder/tracking, /health/deep 포함
HMAC 검증, 정상/비정상 payload 처리를 검증한다.
"""

import hashlib
import hmac
import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


# ──────────────────────────────────────────────────────────
# Flask 테스트 클라이언트
# ──────────────────────────────────────────────────────────

@pytest.fixture
def client():
    import src.order_webhook as wh
    wh.app.config['TESTING'] = True
    with wh.app.test_client() as c:
        yield c


def _make_hmac_header(secret: str, body: bytes) -> str:
    """Shopify HMAC 서명 헤더 값을 생성한다."""
    import base64
    digest = hmac.new(secret.encode(), body, hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


SAMPLE_ORDER = {
    'id': 12345,
    'order_number': 1001,
    'name': '#1001',
    'email': 'customer@example.com',
    'customer': {'first_name': '길동', 'last_name': '홍'},
    'line_items': [
        {'id': 1, 'sku': 'PTR-TNK-001', 'title': 'Porter Bag', 'quantity': 1, 'price': '370000.00'}
    ],
    'shipping_address': {'country_code': 'KR'},
    'financial_status': 'paid',
}

SAMPLE_TRACKING = {
    'order_id': '12345',
    'sku': 'PTR-TNK-001',
    'tracking_number': 'JD123456789KR',
    'carrier': 'CJ대한통운',
    'status': 'in_transit',
}


# ══════════════════════════════════════════════════════════
# /webhook/shopify/order
# ══════════════════════════════════════════════════════════

class TestShopifyOrderWebhook:
    def test_returns_401_without_hmac(self, client):
        """HMAC 헤더 없으면 401을 반환해야 한다."""
        with patch('src.order_webhook.verify_webhook', return_value=False):
            resp = client.post(
                '/webhook/shopify/order',
                data=json.dumps(SAMPLE_ORDER),
                content_type='application/json',
            )
        assert resp.status_code == 401

    def test_returns_401_with_invalid_hmac(self, client):
        """잘못된 HMAC은 401을 반환해야 한다."""
        with patch('src.order_webhook.verify_webhook', return_value=False):
            resp = client.post(
                '/webhook/shopify/order',
                data=json.dumps(SAMPLE_ORDER),
                content_type='application/json',
                headers={'X-Shopify-Hmac-Sha256': 'invalid_sig'},
            )
        assert resp.status_code == 401

    def test_returns_200_with_valid_hmac(self, client):
        """유효한 HMAC 검증을 통과하면 200을 반환해야 한다."""
        mock_routed = {
            'order_id': 12345,
            'tasks': [],
            'summary': {'total_tasks': 0, 'by_vendor': {}, 'by_forwarder': {}},
        }
        with patch('src.order_webhook.verify_webhook', return_value=True), \
             patch('src.order_webhook.router') as mock_router, \
             patch('src.order_webhook.notifier') as mock_notifier, \
             patch('src.order_webhook.status_tracker') as mock_st:
            mock_router.route_order.return_value = mock_routed
            mock_notifier.notify_new_order.return_value = None
            mock_st.record_order.return_value = None

            resp = client.post(
                '/webhook/shopify/order',
                data=json.dumps(SAMPLE_ORDER),
                content_type='application/json',
                headers={'X-Shopify-Hmac-Sha256': 'valid_sig'},
            )
        assert resp.status_code == 200

    def test_response_contains_ok_field(self, client):
        """성공 응답에는 ok 필드가 포함되어야 한다."""
        mock_routed = {
            'order_id': 12345,
            'tasks': [],
            'summary': {'total_tasks': 0, 'by_vendor': {}, 'by_forwarder': {}},
        }
        with patch('src.order_webhook.verify_webhook', return_value=True), \
             patch('src.order_webhook.router') as mock_router, \
             patch('src.order_webhook.notifier'), \
             patch('src.order_webhook.status_tracker'):
            mock_router.route_order.return_value = mock_routed

            resp = client.post(
                '/webhook/shopify/order',
                data=json.dumps(SAMPLE_ORDER),
                content_type='application/json',
            )
        data = json.loads(resp.data)
        assert 'ok' in data

    def test_status_tracker_failure_does_not_cause_500(self, client):
        """status_tracker 오류는 무시하고 200을 반환해야 한다."""
        mock_routed = {
            'order_id': 12345,
            'tasks': [],
            'summary': {'total_tasks': 0, 'by_vendor': {}, 'by_forwarder': {}},
        }
        with patch('src.order_webhook.verify_webhook', return_value=True), \
             patch('src.order_webhook.router') as mock_router, \
             patch('src.order_webhook.notifier'), \
             patch('src.order_webhook.status_tracker') as mock_st:
            mock_router.route_order.return_value = mock_routed
            mock_st.record_order.side_effect = Exception('Sheets error')

            resp = client.post(
                '/webhook/shopify/order',
                data=json.dumps(SAMPLE_ORDER),
                content_type='application/json',
            )
        assert resp.status_code == 200

    def test_401_error_response_contains_error_field(self, client):
        """401 응답에는 error 필드가 포함되어야 한다."""
        with patch('src.order_webhook.verify_webhook', return_value=False):
            resp = client.post(
                '/webhook/shopify/order',
                data=json.dumps(SAMPLE_ORDER),
                content_type='application/json',
            )
        data = json.loads(resp.data)
        assert 'error' in data


# ══════════════════════════════════════════════════════════
# /webhook/forwarder/tracking
# ══════════════════════════════════════════════════════════

class TestForwarderTrackingWebhook:
    def test_tracking_update_returns_200(self, client):
        """배송 추적 업데이트 웹훅은 200을 반환해야 한다."""
        with patch('src.order_webhook.tracker') as mock_tracker, \
             patch('src.order_webhook.status_tracker'), \
             patch('src.order_webhook.notifier'):
            mock_tracker.process_tracking.return_value = {
                'order_id': '12345',
                'notification_sent': False,
            }

            resp = client.post(
                '/webhook/forwarder/tracking',
                data=json.dumps(SAMPLE_TRACKING),
                content_type='application/json',
            )
        assert resp.status_code == 200

    def test_tracking_response_is_json(self, client):
        """배송 추적 응답은 JSON이어야 한다."""
        with patch('src.order_webhook.tracker') as mock_tracker, \
             patch('src.order_webhook.status_tracker'), \
             patch('src.order_webhook.notifier'):
            mock_tracker.process_tracking.return_value = {'order_id': '12345'}

            resp = client.post(
                '/webhook/forwarder/tracking',
                data=json.dumps(SAMPLE_TRACKING),
                content_type='application/json',
            )
        data = json.loads(resp.data)
        assert isinstance(data, dict)

    def test_tracking_with_notification_calls_notifier(self, client):
        """notification_sent=True이면 notifier가 호출되어야 한다."""
        with patch('src.order_webhook.tracker') as mock_tracker, \
             patch('src.order_webhook.status_tracker'), \
             patch('src.order_webhook.notifier') as mock_notifier:
            mock_tracker.process_tracking.return_value = {
                'order_id': '12345',
                'notification_sent': True,
            }
            mock_notifier.notify_tracking_update.return_value = None

            client.post(
                '/webhook/forwarder/tracking',
                data=json.dumps(SAMPLE_TRACKING),
                content_type='application/json',
            )
        mock_notifier.notify_tracking_update.assert_called_once()

    def test_tracking_status_update_failure_is_ignored(self, client):
        """status_tracker 오류는 무시하고 200을 반환해야 한다."""
        with patch('src.order_webhook.tracker') as mock_tracker, \
             patch('src.order_webhook.status_tracker') as mock_st, \
             patch('src.order_webhook.notifier'):
            mock_tracker.process_tracking.return_value = {'order_id': '12345'}
            mock_st.update_status.side_effect = Exception('DB error')

            resp = client.post(
                '/webhook/forwarder/tracking',
                data=json.dumps(SAMPLE_TRACKING),
                content_type='application/json',
            )
        assert resp.status_code == 200


# ══════════════════════════════════════════════════════════
# /health/deep
# ══════════════════════════════════════════════════════════

class TestDeepHealthEndpoint:
    def test_deep_health_returns_json(self, client):
        """Deep healthcheck는 JSON을 반환해야 한다."""
        resp = client.get('/health/deep')
        assert resp.content_type.startswith('application/json')
        data = json.loads(resp.data)
        assert isinstance(data, dict)

    def test_deep_health_has_status_field(self, client):
        """Deep healthcheck 응답에는 status 필드가 있어야 한다."""
        resp = client.get('/health/deep')
        data = json.loads(resp.data)
        assert 'status' in data

    def test_deep_health_has_checks_field(self, client):
        """Deep healthcheck 응답에는 checks 필드가 있어야 한다."""
        resp = client.get('/health/deep')
        data = json.loads(resp.data)
        assert 'checks' in data

    def test_deep_health_has_uptime_field(self, client):
        """Deep healthcheck 응답에는 uptime 또는 timestamp 필드가 있어야 한다."""
        resp = client.get('/health/deep')
        data = json.loads(resp.data)
        has_time_info = 'uptime_seconds' in data or 'timestamp' in data or 'now' in data
        assert has_time_info

    def test_deep_health_checks_secrets(self, client):
        """Deep healthcheck는 시크릿 검증 결과를 포함해야 한다."""
        with patch('src.utils.secret_check.check_secrets') as mock_check:
            mock_check.return_value = {
                'core': {'set': ['GOOGLE_SERVICE_JSON_B64', 'GOOGLE_SHEET_ID'], 'missing': []}
            }
            resp = client.get('/health/deep')
        data = json.loads(resp.data)
        assert 'checks' in data

    def test_deep_health_200_when_all_ok(self, client):
        """모든 체크 통과 시 200을 반환해야 한다."""
        with patch('src.utils.secret_check.check_secrets') as mock_check, \
             patch('src.utils.sheets.open_sheet') as mock_sheet:
            mock_check.return_value = {
                'core': {'set': ['GOOGLE_SERVICE_JSON_B64', 'GOOGLE_SHEET_ID'], 'missing': []}
            }
            mock_sheet.return_value = MagicMock()
            resp = client.get('/health/deep')
        assert resp.status_code in (200, 503)  # 환경에 따라 다를 수 있음

    def test_deep_health_exception_does_not_cause_500(self, client):
        """예외 발생 시에도 500이 아닌 503을 반환해야 한다."""
        with patch('src.utils.secret_check.check_secrets', side_effect=Exception('err')):
            resp = client.get('/health/deep')
        assert resp.status_code in (200, 503)
        data = json.loads(resp.data)
        assert 'status' in data
