"""src/api/mobile_api_routes.py — Phase 95: 모바일 API Blueprint."""
from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

mobile_api_bp = Blueprint(
    'mobile_api',
    __name__,
    url_prefix='/api/mobile/v1',
)

# Lazy singletons
_auth_mgr = None
_product_svc = None
_order_svc = None
_user_svc = None
_push_svc = None
_admin_svc = None


def _auth():
    global _auth_mgr
    if _auth_mgr is None:
        from ..mobile_api.mobile_auth import MobileAuthManager
        _auth_mgr = MobileAuthManager()
    return _auth_mgr


def _products():
    global _product_svc
    if _product_svc is None:
        from ..mobile_api.mobile_product import MobileProductService
        _product_svc = MobileProductService()
    return _product_svc


def _orders():
    global _order_svc
    if _order_svc is None:
        from ..mobile_api.mobile_order import MobileOrderService
        _order_svc = MobileOrderService()
    return _order_svc


def _users():
    global _user_svc
    if _user_svc is None:
        from ..mobile_api.mobile_user import MobileUserService
        _user_svc = MobileUserService()
    return _user_svc


def _push():
    global _push_svc
    if _push_svc is None:
        from ..mobile_api.mobile_notification import MobilePushService
        _push_svc = MobilePushService()
    return _push_svc


def _admin():
    global _admin_svc
    if _admin_svc is None:
        from ..mobile_api.mobile_admin import MobileAdminService
        _admin_svc = MobileAdminService()
    return _admin_svc


def _fmt():
    from ..mobile_api.mobile_response import MobileResponseFormatter
    return MobileResponseFormatter


def _get_user_id() -> str | None:
    return request.headers.get('X-User-Id')


# ─── Auth ────────────────────────────────────────────────────────────────────

@mobile_api_bp.post('/auth/login')
def mobile_login():
    data = request.get_json(force=True) or {}
    email = data.get('email', '')
    password = data.get('password', '')
    device_data = data.get('device', {})
    if not email or not password:
        return jsonify(_fmt().error('MISSING_FIELDS', 'email and password required')), 400
    try:
        from ..mobile_api.mobile_auth import DeviceInfo
        device_info = DeviceInfo(
            device_id=device_data.get('device_id', 'unknown'),
            platform=device_data.get('platform', 'web'),
            push_token=device_data.get('push_token', ''),
            app_version=device_data.get('app_version', '1.0.0'),
        )
        result = _auth().login(email, password, device_info)
        return jsonify(_fmt().success(result, 'Login successful'))
    except ValueError as exc:
        return jsonify(_fmt().error('AUTH_FAILED', str(exc))), 401
    except Exception as exc:
        logger.error("mobile_login error: %s", exc)
        return jsonify(_fmt().error('SERVER_ERROR', str(exc), status_code=500)), 500


@mobile_api_bp.post('/auth/refresh')
def mobile_refresh():
    data = request.get_json(force=True) or {}
    refresh_token = data.get('refresh_token', '')
    device_id = data.get('device_id', 'unknown')
    if not refresh_token:
        return jsonify(_fmt().error('MISSING_FIELDS', 'refresh_token required')), 400
    try:
        result = _auth().refresh_token(refresh_token, device_id)
        return jsonify(_fmt().success(result))
    except ValueError as exc:
        return jsonify(_fmt().error('TOKEN_INVALID', str(exc))), 401


@mobile_api_bp.post('/auth/device')
def mobile_register_device():
    user_id = _get_user_id()
    if not user_id:
        return jsonify(_fmt().error('MISSING_USER', 'X-User-Id header required')), 400
    data = request.get_json(force=True) or {}
    from ..mobile_api.mobile_auth import DeviceInfo
    device_info = DeviceInfo(
        device_id=data.get('device_id', 'unknown'),
        platform=data.get('platform', 'web'),
        push_token=data.get('push_token', ''),
        app_version=data.get('app_version', '1.0.0'),
        os_version=data.get('os_version', ''),
        model=data.get('model', ''),
    )
    _auth().register_device(user_id, device_info)
    return jsonify(_fmt().success({'registered': True}))


@mobile_api_bp.post('/auth/logout')
def mobile_logout():
    data = request.get_json(force=True) or {}
    session_id = data.get('session_id', '')
    if not session_id:
        return jsonify(_fmt().error('MISSING_FIELDS', 'session_id required')), 400
    result = _auth().logout(session_id)
    return jsonify(_fmt().success({'logged_out': result}))


# ─── Products ────────────────────────────────────────────────────────────────

@mobile_api_bp.get('/products')
def mobile_list_products():
    cursor = request.args.get('cursor')
    limit = min(int(request.args.get('limit', 20)), 100)
    category = request.args.get('category')
    search = request.args.get('search')
    result = _products().list_products(cursor=cursor, limit=limit, category=category, search=search)
    formatted = [_fmt().format_product(p) for p in result['items']]
    return jsonify(_fmt().paginated(formatted, result['next_cursor'], result['has_more'], result.get('total')))


@mobile_api_bp.get('/products/recommended')
def mobile_recommended():
    user_id = request.args.get('user_id') or _get_user_id() or 'anonymous'
    top_n = int(request.args.get('top_n', 10))
    items = _products().get_recommended(user_id, top_n=top_n)
    return jsonify(_fmt().success([_fmt().format_product(p) for p in items]))


@mobile_api_bp.get('/products/trending')
def mobile_trending():
    category = request.args.get('category')
    top_n = int(request.args.get('top_n', 10))
    items = _products().get_trending(category=category, top_n=top_n)
    return jsonify(_fmt().success([_fmt().format_product(p) for p in items]))


@mobile_api_bp.get('/products/<sku>')
def mobile_product_detail(sku: str):
    product = _products().get_product(sku)
    if not product:
        return jsonify(_fmt().error('NOT_FOUND', f'Product {sku} not found', status_code=404)), 404
    return jsonify(_fmt().success(_fmt().format_product(product, size='large')))


@mobile_api_bp.get('/categories')
def mobile_categories():
    return jsonify(_fmt().success(_products().get_categories()))


# ─── Cart ────────────────────────────────────────────────────────────────────

@mobile_api_bp.get('/cart')
def mobile_get_cart():
    user_id = _get_user_id()
    if not user_id:
        return jsonify(_fmt().error('MISSING_USER', 'X-User-Id header required')), 400
    return jsonify(_fmt().success(_orders().get_cart(user_id)))


@mobile_api_bp.post('/cart')
def mobile_add_to_cart():
    user_id = _get_user_id()
    if not user_id:
        return jsonify(_fmt().error('MISSING_USER', 'X-User-Id header required')), 400
    data = request.get_json(force=True) or {}
    sku = data.get('sku', '')
    quantity = int(data.get('quantity', 1))
    price = float(data.get('price', 0))
    if not sku:
        return jsonify(_fmt().error('MISSING_FIELDS', 'sku required')), 400
    item = _orders().add_to_cart(user_id, sku, quantity, price)
    return jsonify(_fmt().success({
        'item_id': item.item_id, 'sku': item.sku,
        'quantity': item.quantity, 'price': item.price,
    })), 201


@mobile_api_bp.put('/cart/<item_id>')
def mobile_update_cart(item_id: str):
    user_id = _get_user_id()
    if not user_id:
        return jsonify(_fmt().error('MISSING_USER', 'X-User-Id header required')), 400
    data = request.get_json(force=True) or {}
    quantity = int(data.get('quantity', 1))
    result = _orders().update_cart_item(user_id, item_id, quantity)
    return jsonify(_fmt().success(result))


@mobile_api_bp.delete('/cart/<item_id>')
def mobile_remove_from_cart(item_id: str):
    user_id = _get_user_id()
    if not user_id:
        return jsonify(_fmt().error('MISSING_USER', 'X-User-Id header required')), 400
    result = _orders().remove_from_cart(user_id, item_id)
    return jsonify(_fmt().success({'removed': result}))


# ─── Orders ──────────────────────────────────────────────────────────────────

@mobile_api_bp.post('/orders')
def mobile_create_order():
    user_id = _get_user_id()
    if not user_id:
        return jsonify(_fmt().error('MISSING_USER', 'X-User-Id header required')), 400
    data = request.get_json(force=True) or {}
    shipping_address = data.get('shipping_address', {})
    payment_method = data.get('payment_method', 'card')
    coupon_code = data.get('coupon_code')
    order = _orders().create_order(user_id, shipping_address, payment_method, coupon_code)
    return jsonify(_fmt().success(order)), 201


@mobile_api_bp.get('/orders')
def mobile_list_orders():
    user_id = _get_user_id()
    if not user_id:
        return jsonify(_fmt().error('MISSING_USER', 'X-User-Id header required')), 400
    cursor = request.args.get('cursor')
    limit = int(request.args.get('limit', 20))
    result = _orders().list_orders(user_id, cursor=cursor, limit=limit)
    return jsonify(_fmt().paginated(result['items'], result['next_cursor'], result['has_more']))


@mobile_api_bp.get('/orders/<order_id>')
def mobile_get_order(order_id: str):
    order = _orders().get_order(order_id)
    if not order:
        return jsonify(_fmt().error('NOT_FOUND', f'Order {order_id} not found', status_code=404)), 404
    return jsonify(_fmt().success(order))


@mobile_api_bp.get('/orders/<order_id>/tracking')
def mobile_order_tracking(order_id: str):
    tracking = _orders().get_order_tracking(order_id)
    if not tracking:
        return jsonify(_fmt().error('NOT_FOUND', 'Order not found', status_code=404)), 404
    return jsonify(_fmt().success(tracking))


# ─── User/Profile ─────────────────────────────────────────────────────────────

@mobile_api_bp.get('/profile')
def mobile_get_profile():
    user_id = _get_user_id()
    if not user_id:
        return jsonify(_fmt().error('MISSING_USER', 'X-User-Id header required')), 400
    return jsonify(_fmt().success(_users().get_profile(user_id)))


@mobile_api_bp.put('/profile')
def mobile_update_profile():
    user_id = _get_user_id()
    if not user_id:
        return jsonify(_fmt().error('MISSING_USER', 'X-User-Id header required')), 400
    data = request.get_json(force=True) or {}
    profile = _users().update_profile(user_id, **data)
    return jsonify(_fmt().success(profile))


@mobile_api_bp.get('/addresses')
def mobile_list_addresses():
    user_id = _get_user_id()
    if not user_id:
        return jsonify(_fmt().error('MISSING_USER', 'X-User-Id header required')), 400
    return jsonify(_fmt().success(_users().list_addresses(user_id)))


@mobile_api_bp.post('/addresses')
def mobile_add_address():
    user_id = _get_user_id()
    if not user_id:
        return jsonify(_fmt().error('MISSING_USER', 'X-User-Id header required')), 400
    data = request.get_json(force=True) or {}
    addr = _users().add_address(user_id, data)
    return jsonify(_fmt().success(addr)), 201


@mobile_api_bp.get('/wishlist')
def mobile_get_wishlist():
    user_id = _get_user_id()
    if not user_id:
        return jsonify(_fmt().error('MISSING_USER', 'X-User-Id header required')), 400
    return jsonify(_fmt().success(_users().get_wishlist(user_id)))


@mobile_api_bp.get('/notifications')
def mobile_get_notifications():
    user_id = _get_user_id()
    if not user_id:
        return jsonify(_fmt().error('MISSING_USER', 'X-User-Id header required')), 400
    limit = int(request.args.get('limit', 50))
    unread_only = request.args.get('unread_only', '').lower() == 'true'
    notifs = _push().get_notification_history(user_id, limit=limit, unread_only=unread_only)
    return jsonify(_fmt().success(notifs))


@mobile_api_bp.put('/notifications/<notification_id>/read')
def mobile_mark_notification_read(notification_id: str):
    user_id = _get_user_id()
    if not user_id:
        return jsonify(_fmt().error('MISSING_USER', 'X-User-Id header required')), 400
    result = _push().mark_as_read(user_id, notification_id)
    return jsonify(_fmt().success({'marked_read': result}))


# ─── Import/Global ────────────────────────────────────────────────────────────

@mobile_api_bp.post('/import/order')
def mobile_import_order():
    user_id = _get_user_id()
    if not user_id:
        return jsonify(_fmt().error('MISSING_USER', 'X-User-Id header required')), 400
    data = request.get_json(force=True) or {}
    order = _orders().create_import_order(
        user_id=user_id,
        source_country=data.get('source_country', 'US'),
        product_url=data.get('product_url', ''),
        quantity=int(data.get('quantity', 1)),
        estimated_price=float(data.get('estimated_price', 0)),
    )
    return jsonify(_fmt().success(order)), 201


@mobile_api_bp.post('/import/customs-calc')
def mobile_customs_calc():
    data = request.get_json(force=True) or {}
    result = _orders().calculate_customs(
        price=float(data.get('price', 0)),
        currency=data.get('currency', 'USD'),
        country=data.get('country', 'KR'),
        hs_code=data.get('hs_code', ''),
    )
    return jsonify(_fmt().success(result))


@mobile_api_bp.get('/import/<order_id>/status')
def mobile_import_status(order_id: str):
    order = _orders().get_order(order_id)
    if not order:
        return jsonify(_fmt().error('NOT_FOUND', f'Import order {order_id} not found', status_code=404)), 404
    return jsonify(_fmt().success({'order_id': order_id, 'status': order.get('status', 'pending'), 'order': order}))


# ─── Admin ────────────────────────────────────────────────────────────────────

@mobile_api_bp.get('/admin/dashboard')
def mobile_admin_dashboard():
    return jsonify(_fmt().success(_admin().get_dashboard_summary()))


@mobile_api_bp.get('/admin/orders/pending')
def mobile_admin_pending_orders():
    limit = int(request.args.get('limit', 20))
    return jsonify(_fmt().success(_admin().get_pending_orders(limit=limit)))


@mobile_api_bp.post('/admin/orders/<order_id>/approve')
def mobile_admin_approve_order(order_id: str):
    data = request.get_json(force=True) or {}
    admin_id = data.get('admin_id', 'admin')
    result = _admin().approve_order(order_id, admin_id)
    return jsonify(_fmt().success(result))


@mobile_api_bp.post('/admin/orders/<order_id>/cancel')
def mobile_admin_cancel_order(order_id: str):
    data = request.get_json(force=True) or {}
    admin_id = data.get('admin_id', 'admin')
    reason = data.get('reason', '')
    result = _admin().cancel_order(order_id, admin_id, reason)
    return jsonify(_fmt().success(result))


@mobile_api_bp.get('/admin/alerts')
def mobile_admin_alerts():
    limit = int(request.args.get('limit', 20))
    return jsonify(_fmt().success(_admin().get_system_alerts(limit=limit)))
