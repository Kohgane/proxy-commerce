"""tests/test_mobile_api.py — Phase 95: 모바일 API 테스트."""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest


# ─── MobileAuthManager ──────────────────────────────────────────────────────

class TestMobileAuthManager:
    def _make_device(self, device_id='dev_001', platform='android'):
        from src.mobile_api.mobile_auth import DeviceInfo
        return DeviceInfo(device_id=device_id, platform=platform, push_token='tok123')

    def test_login_success(self):
        from src.mobile_api.mobile_auth import MobileAuthManager
        mgr = MobileAuthManager()
        mgr._users['u1'] = {'email': 'a@b.com', 'password': 'pw', 'name': 'A'}
        result = mgr.login('a@b.com', 'pw', self._make_device())
        assert 'access_token' in result
        assert 'refresh_token' in result
        assert result['user_id'] == 'u1'

    def test_login_fail_bad_credentials(self):
        from src.mobile_api.mobile_auth import MobileAuthManager
        mgr = MobileAuthManager()
        with pytest.raises(ValueError):
            mgr.login('bad@bad.com', 'wrong', self._make_device())

    def test_token_verify(self):
        from src.mobile_api.mobile_auth import MobileAuthManager
        mgr = MobileAuthManager()
        mgr._users['u2'] = {'email': 'c@d.com', 'password': 'pw2', 'name': 'C'}
        result = mgr.login('c@d.com', 'pw2', self._make_device('dev_002'))
        payload = mgr.validate_token(result['access_token'])
        assert payload['sub'] == 'u2'

    def test_refresh_token(self):
        from src.mobile_api.mobile_auth import MobileAuthManager
        mgr = MobileAuthManager()
        mgr._users['u3'] = {'email': 'e@f.com', 'password': 'pw3', 'name': 'E'}
        result = mgr.login('e@f.com', 'pw3', self._make_device('dev_003'))
        new_tokens = mgr.refresh_token(result['refresh_token'], 'dev_003')
        assert 'access_token' in new_tokens

    def test_register_device(self):
        from src.mobile_api.mobile_auth import MobileAuthManager
        mgr = MobileAuthManager()
        device = self._make_device('dev_reg', 'ios')
        mgr.register_device('user_x', device)
        assert 'dev_reg' in mgr._devices

    def test_logout(self):
        from src.mobile_api.mobile_auth import MobileAuthManager
        mgr = MobileAuthManager()
        mgr._users['u4'] = {'email': 'g@h.com', 'password': 'pw4', 'name': 'G'}
        result = mgr.login('g@h.com', 'pw4', self._make_device('dev_004'))
        sid = result['session_id']
        assert mgr.logout(sid) is True
        assert mgr.logout(sid) is False  # already removed

    def test_session_limit_max5(self):
        from src.mobile_api.mobile_auth import MobileAuthManager, DeviceInfo
        mgr = MobileAuthManager()
        mgr._users['u5'] = {'email': 'x@y.com', 'password': 'pw5', 'name': 'X'}
        for i in range(7):
            device = DeviceInfo(device_id=f'dev_{i}', platform='android')
            mgr.login('x@y.com', 'pw5', device)
        sessions = mgr.get_active_sessions('u5')
        assert len(sessions) <= 5

    def test_get_active_sessions(self):
        from src.mobile_api.mobile_auth import MobileAuthManager, DeviceInfo
        mgr = MobileAuthManager()
        mgr._users['u6'] = {'email': 'z@w.com', 'password': 'pw6', 'name': 'Z'}
        mgr.login('z@w.com', 'pw6', DeviceInfo(device_id='d1', platform='ios'))
        mgr.login('z@w.com', 'pw6', DeviceInfo(device_id='d2', platform='android'))
        sessions = mgr.get_active_sessions('u6')
        assert len(sessions) == 2


# ─── MobileProductService ────────────────────────────────────────────────────

class TestMobileProductService:
    def test_list_products_returns_items(self):
        from src.mobile_api.mobile_product import MobileProductService
        svc = MobileProductService()
        result = svc.list_products()
        assert 'items' in result
        assert len(result['items']) > 0

    def test_list_products_pagination(self):
        from src.mobile_api.mobile_product import MobileProductService
        svc = MobileProductService()
        result = svc.list_products(limit=2)
        assert len(result['items']) <= 2

    def test_list_products_cursor(self):
        from src.mobile_api.mobile_product import MobileProductService
        svc = MobileProductService()
        page1 = svc.list_products(limit=2)
        if page1['has_more']:
            page2 = svc.list_products(cursor=page1['next_cursor'], limit=2)
            assert page2['items'] != page1['items']

    def test_list_products_category_filter(self):
        from src.mobile_api.mobile_product import MobileProductService
        svc = MobileProductService()
        result = svc.list_products(category='electronics')
        for p in result['items']:
            assert p['category'] == 'electronics'

    def test_list_products_search(self):
        from src.mobile_api.mobile_product import MobileProductService
        svc = MobileProductService()
        result = svc.list_products(search='headphones')
        assert any('headphones' in p['name'].lower() or 'headphones' in p.get('description', '').lower()
                   for p in result['items'])

    def test_get_product_found(self):
        from src.mobile_api.mobile_product import MobileProductService
        svc = MobileProductService()
        p = svc.get_product('P001')
        assert p is not None
        assert p['sku'] == 'P001'

    def test_get_product_not_found(self):
        from src.mobile_api.mobile_product import MobileProductService
        svc = MobileProductService()
        p = svc.get_product('XXXX')
        assert p is None

    def test_get_recommended(self):
        from src.mobile_api.mobile_product import MobileProductService
        svc = MobileProductService()
        recs = svc.get_recommended('user_001', top_n=3)
        assert isinstance(recs, list)
        assert len(recs) <= 3

    def test_get_trending(self):
        from src.mobile_api.mobile_product import MobileProductService
        svc = MobileProductService()
        trending = svc.get_trending(top_n=5)
        assert len(trending) <= 5

    def test_get_categories(self):
        from src.mobile_api.mobile_product import MobileProductService
        svc = MobileProductService()
        cats = svc.get_categories()
        assert isinstance(cats, list)
        assert len(cats) > 0
        assert 'name' in cats[0]


# ─── MobileOrderService ──────────────────────────────────────────────────────

class TestMobileOrderService:
    def test_add_to_cart(self):
        from src.mobile_api.mobile_order import MobileOrderService
        svc = MobileOrderService()
        item = svc.add_to_cart('u1', 'P001', 2, 99.99)
        assert item.sku == 'P001'
        assert item.quantity == 2

    def test_get_cart(self):
        from src.mobile_api.mobile_order import MobileOrderService
        svc = MobileOrderService()
        svc.add_to_cart('u1', 'P001', 1, 99.99)
        cart = svc.get_cart('u1')
        assert len(cart) == 1
        assert cart[0]['sku'] == 'P001'

    def test_update_cart_item(self):
        from src.mobile_api.mobile_order import MobileOrderService
        svc = MobileOrderService()
        item = svc.add_to_cart('u2', 'P002', 1, 49.0)
        updated = svc.update_cart_item('u2', item.item_id, 5)
        assert updated['quantity'] == 5

    def test_remove_from_cart(self):
        from src.mobile_api.mobile_order import MobileOrderService
        svc = MobileOrderService()
        item = svc.add_to_cart('u3', 'P003', 1, 129.0)
        result = svc.remove_from_cart('u3', item.item_id)
        assert result is True
        assert svc.get_cart('u3') == []

    def test_remove_nonexistent_item(self):
        from src.mobile_api.mobile_order import MobileOrderService
        svc = MobileOrderService()
        result = svc.remove_from_cart('u3', 'nonexistent-id')
        assert result is False

    def test_create_order(self):
        from src.mobile_api.mobile_order import MobileOrderService
        svc = MobileOrderService()
        svc.add_to_cart('u4', 'P001', 2, 99.99)
        order = svc.create_order('u4', {'street': '123 Main St'}, 'card')
        assert order['status'] == 'pending'
        assert order['user_id'] == 'u4'
        assert svc.get_cart('u4') == []  # cart cleared

    def test_list_orders(self):
        from src.mobile_api.mobile_order import MobileOrderService
        svc = MobileOrderService()
        svc.add_to_cart('u5', 'P001', 1, 99.99)
        svc.create_order('u5', {}, 'card')
        result = svc.list_orders('u5')
        assert result['items']

    def test_get_order(self):
        from src.mobile_api.mobile_order import MobileOrderService
        svc = MobileOrderService()
        svc.add_to_cart('u6', 'P002', 1, 49.0)
        order = svc.create_order('u6', {}, 'paypal')
        retrieved = svc.get_order(order['order_id'])
        assert retrieved['order_id'] == order['order_id']

    def test_get_order_tracking(self):
        from src.mobile_api.mobile_order import MobileOrderService
        svc = MobileOrderService()
        svc.add_to_cart('u7', 'P003', 1, 129.0)
        order = svc.create_order('u7', {}, 'card')
        tracking = svc.get_order_tracking(order['order_id'])
        assert 'tracking_number' in tracking
        assert 'status' in tracking

    def test_create_import_order(self):
        from src.mobile_api.mobile_order import MobileOrderService
        svc = MobileOrderService()
        order = svc.create_import_order('u8', 'US', 'https://amazon.com/p/123', 2, 59.99)
        assert order['type'] == 'import'
        assert order['source_country'] == 'US'

    def test_calculate_customs(self):
        from src.mobile_api.mobile_order import MobileOrderService
        svc = MobileOrderService()
        result = svc.calculate_customs(100.0, 'USD', 'KR', '8518.30')
        assert 'duty_amount' in result
        assert 'vat_amount' in result
        assert result['total_landed_cost'] > 100.0


# ─── MobileUserService ───────────────────────────────────────────────────────

class TestMobileUserService:
    def test_get_profile_creates_default(self):
        from src.mobile_api.mobile_user import MobileUserService
        svc = MobileUserService()
        profile = svc.get_profile('u1')
        assert profile['user_id'] == 'u1'

    def test_update_profile(self):
        from src.mobile_api.mobile_user import MobileUserService
        svc = MobileUserService()
        svc.get_profile('u1')
        updated = svc.update_profile('u1', name='Alice', email='alice@example.com')
        assert updated['name'] == 'Alice'
        assert updated['email'] == 'alice@example.com'

    def test_add_address(self):
        from src.mobile_api.mobile_user import MobileUserService
        svc = MobileUserService()
        addr = svc.add_address('u1', {'street': '123 Main St', 'city': 'Seoul'})
        assert 'address_id' in addr

    def test_list_addresses(self):
        from src.mobile_api.mobile_user import MobileUserService
        svc = MobileUserService()
        svc.add_address('u2', {'street': 'A'})
        svc.add_address('u2', {'street': 'B'})
        addrs = svc.list_addresses('u2')
        assert len(addrs) == 2

    def test_set_default_address(self):
        from src.mobile_api.mobile_user import MobileUserService
        svc = MobileUserService()
        a1 = svc.add_address('u3', {'street': 'A'})
        a2 = svc.add_address('u3', {'street': 'B'})
        result = svc.set_default_address('u3', a2['address_id'])
        assert result is True
        addrs = svc.list_addresses('u3')
        for addr in addrs:
            if addr['address_id'] == a2['address_id']:
                assert addr['is_default'] is True
            else:
                assert addr['is_default'] is False

    def test_delete_address(self):
        from src.mobile_api.mobile_user import MobileUserService
        svc = MobileUserService()
        addr = svc.add_address('u4', {'street': 'C'})
        result = svc.delete_address('u4', addr['address_id'])
        assert result is True
        assert svc.list_addresses('u4') == []

    def test_wishlist_add_remove(self):
        from src.mobile_api.mobile_user import MobileUserService
        svc = MobileUserService()
        svc.add_to_wishlist('u5', 'P001')
        svc.add_to_wishlist('u5', 'P002')
        wl = svc.get_wishlist('u5')
        assert len(wl) == 2
        svc.remove_from_wishlist('u5', 'P001')
        wl2 = svc.get_wishlist('u5')
        assert len(wl2) == 1

    def test_notification_settings_default(self):
        from src.mobile_api.mobile_user import MobileUserService
        svc = MobileUserService()
        settings = svc.get_notification_settings('u6')
        assert 'push' in settings
        assert 'email' in settings

    def test_update_notification_settings(self):
        from src.mobile_api.mobile_user import MobileUserService
        svc = MobileUserService()
        svc.get_notification_settings('u7')
        updated = svc.update_notification_settings('u7', push=False, telegram=True)
        assert updated['push'] is False
        assert updated['telegram'] is True

    def test_get_points(self):
        from src.mobile_api.mobile_user import MobileUserService
        svc = MobileUserService()
        points = svc.get_points('u8')
        assert 'balance' in points
        assert 'grade' in points


# ─── MobilePushService ───────────────────────────────────────────────────────

class TestMobilePushService:
    def test_register_push_token(self):
        from src.mobile_api.mobile_notification import MobilePushService
        svc = MobilePushService()
        result = svc.register_push_token('u1', 'dev1', 'android', 'fcm_token_abc')
        assert result is True

    def test_revoke_push_token(self):
        from src.mobile_api.mobile_notification import MobilePushService
        svc = MobilePushService()
        svc.register_push_token('u1', 'dev1', 'android', 'token')
        result = svc.revoke_push_token('u1', 'dev1')
        assert result is True
        result2 = svc.revoke_push_token('u1', 'dev1')
        assert result2 is False

    def test_send_notification(self):
        from src.mobile_api.mobile_notification import MobilePushService, PushNotification
        svc = MobilePushService()
        notif = svc.send_notification('u1', 'Hello', 'World', 'promotion')
        assert isinstance(notif, PushNotification)
        assert notif.user_id == 'u1'
        assert not notif.is_read

    def test_send_order_status_notification(self):
        from src.mobile_api.mobile_notification import MobilePushService
        svc = MobilePushService()
        notif = svc.send_order_status_notification('u2', 'order-abc-123', 'shipped')
        assert notif.notification_type == 'order_status'
        assert 'order-abc' in notif.data.get('order_id', '')

    def test_send_price_drop_notification(self):
        from src.mobile_api.mobile_notification import MobilePushService
        svc = MobilePushService()
        notif = svc.send_price_drop_notification('u3', 'P001', 100.0, 80.0)
        assert notif.notification_type == 'price_drop'

    def test_send_restock_notification(self):
        from src.mobile_api.mobile_notification import MobilePushService
        svc = MobilePushService()
        notif = svc.send_restock_notification('u4', 'P002')
        assert notif.notification_type == 'restock'

    def test_send_delivery_notification(self):
        from src.mobile_api.mobile_notification import MobilePushService
        svc = MobilePushService()
        notif = svc.send_delivery_notification('u5', 'order-xyz-456')
        assert notif.notification_type == 'delivery'

    def test_send_promotion_notification(self):
        from src.mobile_api.mobile_notification import MobilePushService
        svc = MobilePushService()
        notif = svc.send_promotion_notification('u6', 'Sale!', '50% off today')
        assert notif.notification_type == 'promotion'

    def test_get_notification_history(self):
        from src.mobile_api.mobile_notification import MobilePushService
        svc = MobilePushService()
        svc.send_notification('u7', 'T1', 'B1', 'promotion')
        svc.send_notification('u7', 'T2', 'B2', 'order_status')
        history = svc.get_notification_history('u7')
        assert len(history) == 2

    def test_mark_as_read(self):
        from src.mobile_api.mobile_notification import MobilePushService
        svc = MobilePushService()
        notif = svc.send_notification('u8', 'Test', 'Body', 'promotion')
        result = svc.mark_as_read('u8', notif.notification_id)
        assert result is True
        history = svc.get_notification_history('u8', unread_only=True)
        assert len(history) == 0

    def test_unread_filter(self):
        from src.mobile_api.mobile_notification import MobilePushService
        svc = MobilePushService()
        n1 = svc.send_notification('u9', 'A', 'B', 'promotion')
        svc.send_notification('u9', 'C', 'D', 'promotion')
        svc.mark_as_read('u9', n1.notification_id)
        unread = svc.get_notification_history('u9', unread_only=True)
        assert len(unread) == 1


# ─── MobileAdminService ──────────────────────────────────────────────────────

class TestMobileAdminService:
    def test_get_dashboard_summary(self):
        from src.mobile_api.mobile_admin import MobileAdminService
        svc = MobileAdminService()
        summary = svc.get_dashboard_summary()
        assert 'order_count' in summary
        assert 'revenue' in summary
        assert 'active_users' in summary

    def test_get_pending_orders(self):
        from src.mobile_api.mobile_admin import MobileAdminService
        svc = MobileAdminService()
        orders = svc.get_pending_orders(limit=3)
        assert len(orders) <= 3

    def test_approve_order(self):
        from src.mobile_api.mobile_admin import MobileAdminService
        svc = MobileAdminService()
        result = svc.approve_order('ORD0001', 'admin1')
        assert result['success'] is True
        assert result['status'] == 'confirmed'

    def test_cancel_order(self):
        from src.mobile_api.mobile_admin import MobileAdminService
        svc = MobileAdminService()
        result = svc.cancel_order('ORD0002', 'admin1', 'customer request')
        assert result['success'] is True
        assert result['status'] == 'cancelled'

    def test_approve_nonexistent_order(self):
        from src.mobile_api.mobile_admin import MobileAdminService
        svc = MobileAdminService()
        result = svc.approve_order('NONEXISTENT', 'admin1')
        assert result['success'] is False

    def test_get_system_alerts(self):
        from src.mobile_api.mobile_admin import MobileAdminService
        svc = MobileAdminService()
        alerts = svc.get_system_alerts()
        assert isinstance(alerts, list)
        assert len(alerts) > 0
        assert 'severity' in alerts[0]

    def test_get_inventory_status(self):
        from src.mobile_api.mobile_admin import MobileAdminService
        svc = MobileAdminService()
        inv = svc.get_inventory_status(limit=5)
        assert len(inv) <= 5

    def test_get_import_export_status(self):
        from src.mobile_api.mobile_admin import MobileAdminService
        svc = MobileAdminService()
        result = svc.get_import_export_status()
        assert 'import_orders' in result
        assert 'export_orders' in result


# ─── MobileResponseFormatter ─────────────────────────────────────────────────

class TestMobileResponseFormatter:
    def test_success_response(self):
        from src.mobile_api.mobile_response import MobileResponseFormatter
        resp = MobileResponseFormatter.success({'key': 'value'})
        assert resp['success'] is True
        assert resp['data'] == {'key': 'value'}
        assert resp['api_version'] == 'v1'

    def test_success_with_message(self):
        from src.mobile_api.mobile_response import MobileResponseFormatter
        resp = MobileResponseFormatter.success(None, message='OK')
        assert resp['message'] == 'OK'

    def test_error_response(self):
        from src.mobile_api.mobile_response import MobileResponseFormatter
        resp = MobileResponseFormatter.error('NOT_FOUND', 'Resource not found', status_code=404)
        assert resp['success'] is False
        assert resp['error']['code'] == 'NOT_FOUND'
        assert resp['status_code'] == 404

    def test_paginated_response(self):
        from src.mobile_api.mobile_response import MobileResponseFormatter
        resp = MobileResponseFormatter.paginated([1, 2, 3], next_cursor='abc', has_more=True, total=10)
        assert resp['success'] is True
        assert resp['data'] == [1, 2, 3]
        assert resp['meta']['has_more'] is True
        assert resp['meta']['total'] == 10

    def test_format_image_url_medium(self):
        from src.mobile_api.mobile_response import MobileResponseFormatter
        url = MobileResponseFormatter.format_image_url('https://cdn.example.com/img.jpg', 'medium')
        assert 'w=400' in url
        assert 'h=400' in url

    def test_format_image_url_thumbnail(self):
        from src.mobile_api.mobile_response import MobileResponseFormatter
        url = MobileResponseFormatter.format_image_url('https://cdn.example.com/img.jpg', 'thumbnail')
        assert 'w=100' in url

    def test_format_image_url_large(self):
        from src.mobile_api.mobile_response import MobileResponseFormatter
        url = MobileResponseFormatter.format_image_url('https://cdn.example.com/img.jpg', 'large')
        assert 'w=800' in url

    def test_format_product(self):
        from src.mobile_api.mobile_response import MobileResponseFormatter
        product = {'sku': 'P001', 'name': 'Test', 'images': ['https://cdn.example.com/p.jpg']}
        formatted = MobileResponseFormatter.format_product(product)
        assert 'w=400' in formatted['images'][0]

    def test_cursor_encode_decode(self):
        from src.mobile_api.mobile_response import MobileResponseFormatter
        encoded = MobileResponseFormatter.cursor_encode(42)
        decoded = MobileResponseFormatter.cursor_decode(encoded)
        assert decoded == 42

    def test_cursor_decode_invalid(self):
        from src.mobile_api.mobile_response import MobileResponseFormatter
        result = MobileResponseFormatter.cursor_decode('!!!invalid!!!')
        assert result == 0


# ─── Flask Blueprint Integration ─────────────────────────────────────────────

class TestMobileAPIBlueprint:
    @pytest.fixture
    def client(self):
        import sys
        import os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
        from src.api.mobile_api_routes import mobile_api_bp
        from flask import Flask
        app = Flask(__name__)
        app.register_blueprint(mobile_api_bp)
        app.config['TESTING'] = True
        return app.test_client()

    def test_login_success(self, client):
        resp = client.post('/api/mobile/v1/auth/login', json={
            'email': 'user@example.com', 'password': 'pass123',
            'device': {'device_id': 'test_dev', 'platform': 'android'},
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert 'access_token' in data['data']

    def test_login_fail(self, client):
        resp = client.post('/api/mobile/v1/auth/login', json={
            'email': 'wrong@wrong.com', 'password': 'bad',
        })
        assert resp.status_code == 401

    def test_login_missing_fields(self, client):
        resp = client.post('/api/mobile/v1/auth/login', json={})
        assert resp.status_code == 400

    def test_list_products(self, client):
        resp = client.get('/api/mobile/v1/products')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert isinstance(data['data'], list)

    def test_product_detail_found(self, client):
        resp = client.get('/api/mobile/v1/products/P001')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['data']['sku'] == 'P001'

    def test_product_detail_not_found(self, client):
        resp = client.get('/api/mobile/v1/products/XXXX')
        assert resp.status_code == 404

    def test_categories(self, client):
        resp = client.get('/api/mobile/v1/categories')
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data['data'], list)

    def test_get_cart_missing_header(self, client):
        resp = client.get('/api/mobile/v1/cart')
        assert resp.status_code == 400

    def test_add_to_cart(self, client):
        resp = client.post('/api/mobile/v1/cart',
                           json={'sku': 'P001', 'quantity': 1, 'price': 99.99},
                           headers={'X-User-Id': 'u_test'})
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['data']['sku'] == 'P001'

    def test_get_cart(self, client):
        client.post('/api/mobile/v1/cart',
                    json={'sku': 'P002', 'quantity': 2, 'price': 49.0},
                    headers={'X-User-Id': 'u_cart_test'})
        resp = client.get('/api/mobile/v1/cart', headers={'X-User-Id': 'u_cart_test'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert any(item['sku'] == 'P002' for item in data['data'])

    def test_create_order(self, client):
        client.post('/api/mobile/v1/cart',
                    json={'sku': 'P001', 'quantity': 1, 'price': 99.99},
                    headers={'X-User-Id': 'u_order'})
        resp = client.post('/api/mobile/v1/orders',
                           json={'shipping_address': {'street': '123 Main'}, 'payment_method': 'card'},
                           headers={'X-User-Id': 'u_order'})
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['data']['status'] == 'pending'

    def test_list_orders(self, client):
        resp = client.get('/api/mobile/v1/orders', headers={'X-User-Id': 'u_list'})
        assert resp.status_code == 200

    def test_get_profile(self, client):
        resp = client.get('/api/mobile/v1/profile', headers={'X-User-Id': 'u_profile'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['data']['user_id'] == 'u_profile'

    def test_admin_dashboard(self, client):
        resp = client.get('/api/mobile/v1/admin/dashboard')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'order_count' in data['data']

    def test_admin_alerts(self, client):
        resp = client.get('/api/mobile/v1/admin/alerts')
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data['data'], list)

    def test_customs_calc(self, client):
        resp = client.post('/api/mobile/v1/import/customs-calc',
                           json={'price': 200.0, 'currency': 'USD', 'country': 'KR', 'hs_code': '8518.30'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'total_customs' in data['data']

    def test_trending_products(self, client):
        resp = client.get('/api/mobile/v1/products/trending')
        assert resp.status_code == 200

    def test_recommended_products(self, client):
        resp = client.get('/api/mobile/v1/products/recommended?user_id=u_rec')
        assert resp.status_code == 200

    def test_wishlist(self, client):
        resp = client.get('/api/mobile/v1/wishlist', headers={'X-User-Id': 'u_wish'})
        assert resp.status_code == 200

    def test_notifications_list(self, client):
        resp = client.get('/api/mobile/v1/notifications', headers={'X-User-Id': 'u_notif'})
        assert resp.status_code == 200

    def test_import_order(self, client):
        resp = client.post('/api/mobile/v1/import/order',
                           json={'source_country': 'US', 'product_url': 'https://amazon.com/p/123',
                                 'quantity': 1, 'estimated_price': 50.0},
                           headers={'X-User-Id': 'u_import'})
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['data']['type'] == 'import'
