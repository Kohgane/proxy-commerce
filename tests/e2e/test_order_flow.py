"""tests/e2e/test_order_flow.py — 주문 플로우 E2E 통합 테스트.

Shopify / WooCommerce 웹훅 엔드포인트의 전체 흐름을 검증한다.
"""

import json
from unittest.mock import patch

from tests.e2e.conftest import shopify_hmac_header

# ── 샘플 페이로드 ─────────────────────────────────────────────

SHOPIFY_ORDER = {
    'id': 99001,
    'order_number': 2001,
    'name': '#2001',
    'email': 'e2e@example.com',
    'customer': {'first_name': '테스트', 'last_name': '사용자', 'email': 'e2e@example.com'},
    'line_items': [
        {
            'id': 1,
            'sku': 'PTR-TNK-001',
            'title': 'Porter Tanker Briefcase',
            'quantity': 1,
            'price': '370000.00',
        }
    ],
    'shipping_address': {'country_code': 'KR', 'country': 'South Korea'},
    'financial_status': 'paid',
    'total_price': '370000.00',
    'currency': 'KRW',
}

WOO_ORDER = {
    'id': 88001,
    'number': '88001',
    'status': 'processing',
    'billing': {'email': 'woo@example.com', 'first_name': '우커', 'last_name': '고객'},
    'line_items': [
        {
            'id': 1,
            'sku': 'PTR-TNK-001',
            'name': 'Porter Tanker Briefcase',
            'quantity': 1,
            'price': '370000',
        }
    ],
    'total': '370000',
    'currency': 'KRW',
}


class TestShopifyOrderFlow:
    """Shopify 주문 플로우 E2E 테스트."""

    def test_shopify_order_full_flow(self, e2e_client, monkeypatch):
        """유효한 HMAC → 200 OK, 주문 라우팅 완료."""
        secret = 'e2e_test_secret'
        monkeypatch.setenv('SHOPIFY_CLIENT_SECRET', secret)

        payload = json.dumps(SHOPIFY_ORDER).encode()
        sig = shopify_hmac_header(payload, secret)

        with patch('src.order_webhook.router') as mock_router, \
             patch('src.order_webhook.notifier'), \
             patch('src.order_webhook.status_tracker'), \
             patch('src.order_webhook.audit_logger'):

            mock_router.route_order.return_value = {
                'order_id': 99001,
                'tasks': [],
                'summary': {'total_tasks': 1, 'by_vendor': {}, 'by_forwarder': {}},
            }

            resp = e2e_client.post(
                '/webhook/shopify/order',
                data=payload,
                content_type='application/json',
                headers={'X-Shopify-Hmac-Sha256': sig},
            )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get('ok') is True

    def test_shopify_order_invalid_hmac(self, e2e_client, monkeypatch):
        """잘못된 HMAC → 401 반환."""
        payload = json.dumps(SHOPIFY_ORDER).encode()

        with patch('src.order_webhook.verify_webhook', return_value=False), \
             patch('src.order_webhook.audit_logger'):
            resp = e2e_client.post(
                '/webhook/shopify/order',
                data=payload,
                content_type='application/json',
                headers={'X-Shopify-Hmac-Sha256': 'invalidsignature=='},
            )

        assert resp.status_code == 401

    def test_shopify_order_duplicate_rejected(self, e2e_client, monkeypatch):
        """같은 주문 두 번 전송 시 두 번째는 skipped:duplicate 반환."""
        secret = 'dup_test_secret'
        monkeypatch.setenv('SHOPIFY_CLIENT_SECRET', secret)
        payload = json.dumps(SHOPIFY_ORDER).encode()
        sig = shopify_hmac_header(payload, secret)

        with patch('src.order_webhook.router') as mock_router, \
             patch('src.order_webhook.notifier'), \
             patch('src.order_webhook.status_tracker'), \
             patch('src.order_webhook.audit_logger'):

            mock_router.route_order.return_value = {
                'order_id': 99001,
                'tasks': [],
                'summary': {'total_tasks': 1, 'by_vendor': {}, 'by_forwarder': {}},
            }

            headers = {'X-Shopify-Hmac-Sha256': sig}
            # 첫 번째 요청 — 정상 처리
            resp1 = e2e_client.post(
                '/webhook/shopify/order',
                data=payload,
                content_type='application/json',
                headers=headers,
            )
            assert resp1.status_code == 200

            # 두 번째 요청 — 중복 감지
            resp2 = e2e_client.post(
                '/webhook/shopify/order',
                data=payload,
                content_type='application/json',
                headers=headers,
            )

        assert resp2.status_code == 200
        data2 = resp2.get_json()
        assert data2.get('skipped') == 'duplicate'

    def test_shopify_order_validation_failure(self, e2e_client, monkeypatch):
        """필수 필드 누락 시 400 반환."""
        monkeypatch.setenv('SHOPIFY_CLIENT_SECRET', '')  # HMAC 검증 비활성화

        bad_payload = {'id': 99999}  # line_items 등 필수 필드 누락
        payload = json.dumps(bad_payload).encode()

        with patch('src.order_webhook.audit_logger'):
            resp = e2e_client.post(
                '/webhook/shopify/order',
                data=payload,
                content_type='application/json',
                headers={'X-Shopify-Hmac-Sha256': ''},
            )

        assert resp.status_code == 400


class TestWooCommerceOrderFlow:
    """WooCommerce 주문 플로우 E2E 테스트."""

    def test_woocommerce_order_flow(self, e2e_client, monkeypatch):
        """유효한 webhook_secret → 200 OK."""
        secret = 'woo_e2e_secret'
        monkeypatch.setenv('WOO_WEBHOOK_SECRET', secret)

        import base64
        import hashlib
        import hmac as _hmac

        payload = json.dumps(WOO_ORDER).encode()
        digest = _hmac.new(secret.encode(), payload, hashlib.sha256).digest()
        sig = base64.b64encode(digest).decode()

        with patch('src.order_webhook.router') as mock_router, \
             patch('src.order_webhook.notifier'), \
             patch('src.order_webhook.status_tracker'), \
             patch('src.order_webhook.audit_logger'):

            mock_router.route_order.return_value = {
                'order_id': 88001,
                'tasks': [],
                'summary': {'total_tasks': 0, 'by_vendor': {}, 'by_forwarder': {}},
            }

            resp = e2e_client.post(
                '/webhook/woo',
                data=payload,
                content_type='application/json',
                headers={'X-WC-Webhook-Signature': sig},
            )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get('ok') is True

    def test_woocommerce_invalid_secret(self, e2e_client, monkeypatch):
        """잘못된 WooCommerce secret → 401 반환."""
        payload = json.dumps(WOO_ORDER).encode()

        with patch('src.order_webhook.verify_woo_webhook', return_value=False), \
             patch('src.order_webhook.audit_logger'):
            resp = e2e_client.post(
                '/webhook/woo',
                data=payload,
                content_type='application/json',
                headers={'X-WC-Webhook-Signature': 'wrong_signature'},
            )

        assert resp.status_code == 401
