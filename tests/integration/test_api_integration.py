"""tests/integration/test_api_integration.py — 주요 API 엔드포인트 통합 테스트."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))


@pytest.fixture
def app():
    """Flask 테스트 앱 생성."""
    import os
    os.environ.setdefault('SHOPIFY_CLIENT_SECRET', 'test_secret')
    os.environ.setdefault('TELEGRAM_BOT_TOKEN', '123456:test')
    os.environ.setdefault('TELEGRAM_CHAT_ID', '-100123456')
    os.environ.setdefault('DASHBOARD_API_ENABLED', '0')
    os.environ.setdefault('DASHBOARD_WEB_UI_ENABLED', '0')

    from flask import Flask

    flask_app = Flask(__name__)

    from src.api.inventory_sync_api import inventory_sync_bp
    from src.api.translation_api import translation_bp
    from src.api.pricing_api import pricing_bp
    from src.api.suppliers_api import suppliers_bp
    from src.api.notifications_api import notifications_bp

    flask_app.register_blueprint(inventory_sync_bp)
    flask_app.register_blueprint(translation_bp)
    flask_app.register_blueprint(pricing_bp)
    flask_app.register_blueprint(suppliers_bp)
    flask_app.register_blueprint(notifications_bp)

    flask_app.config['TESTING'] = True
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


class TestInventorySyncAPI:
    """재고 동기화 API 테스트."""

    def test_get_sync_status(self, client):
        resp = client.get('/api/inventory/sync')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'channels' in data

    def test_post_sync(self, client):
        resp = client.post('/api/inventory/sync', json={})
        assert resp.status_code == 200

    def test_post_sync_with_sku(self, client):
        resp = client.post('/api/inventory/sync', json={'sku': 'test-sku'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['sku'] == 'test-sku'

    def test_inventory_status(self, client):
        resp = client.get('/api/inventory/status')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['status'] == 'ok'


class TestTranslationAPI:
    """번역 API 테스트."""

    def test_translation_status(self, client):
        resp = client.get('/api/translation/status')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['status'] == 'ok'

    def test_list_requests(self, client):
        resp = client.get('/api/translation/requests')
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    def test_create_request(self, client):
        resp = client.post('/api/translation/requests', json={
            'product_id': 'prod-001',
            'text': 'Hello World',
            'src_lang': 'en',
            'tgt_lang': 'ko',
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert 'request_id' in data

    def test_create_request_no_text(self, client):
        resp = client.post('/api/translation/requests', json={})
        assert resp.status_code == 400


class TestPricingAPI:
    """가격 엔진 API 테스트."""

    def test_pricing_status(self, client):
        resp = client.get('/api/pricing/status')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['status'] == 'ok'

    def test_simulate_price(self, client):
        resp = client.post('/api/pricing/simulate', json={
            'sku': 'test-sku',
            'market_data': {'cost': 10000, 'margin_rate': 0.3},
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'prices' in data

    def test_simulate_no_sku(self, client):
        resp = client.post('/api/pricing/simulate', json={})
        assert resp.status_code == 400

    def test_run_pricer(self, client):
        resp = client.post('/api/pricing/run', json={'dry_run': True})
        assert resp.status_code == 200


class TestSuppliersAPI:
    """공급자 API 테스트."""

    def test_suppliers_status(self, client):
        resp = client.get('/api/suppliers/status')
        assert resp.status_code == 200

    def test_list_suppliers(self, client):
        resp = client.get('/api/suppliers/')
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    def test_add_supplier(self, client):
        resp = client.post('/api/suppliers/', json={'name': 'Test Supplier', 'email': 'test@example.com'})
        assert resp.status_code == 201
        data = resp.get_json()
        assert 'supplier_id' in data

    def test_calculate_score(self, client):
        resp = client.post('/api/suppliers/score', json={'quality': 90, 'delivery': 80, 'price': 70})
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'score' in data
        assert 'grade' in data

    def test_create_order(self, client):
        resp = client.post('/api/suppliers/orders', json={
            'supplier_id': 'sup-001',
            'sku': 'test-sku',
            'qty': 100,
        })
        assert resp.status_code == 201

    def test_create_order_missing_fields(self, client):
        resp = client.post('/api/suppliers/orders', json={})
        assert resp.status_code == 400


class TestNotificationsAPI:
    """알림 API 테스트."""

    def test_notifications_status(self, client):
        resp = client.get('/api/notifications/status')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['status'] == 'ok'

    def test_dispatch_notification(self, client):
        resp = client.post('/api/notifications/dispatch', json={
            'event_type': 'stock_low',
            'recipient': 'admin',
            'message': '재고 부족 경고',
        })
        assert resp.status_code == 200

    def test_dispatch_missing_fields(self, client):
        resp = client.post('/api/notifications/dispatch', json={})
        assert resp.status_code == 400

    def test_get_preferences(self, client):
        resp = client.get('/api/notifications/preferences/user-001')
        assert resp.status_code == 200

    def test_set_preferences(self, client):
        resp = client.post('/api/notifications/preferences/user-001', json={
            'event_type': 'order_placed',
            'channel': 'email',
            'enabled': True,
        })
        assert resp.status_code == 200
