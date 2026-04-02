"""src/api/analytics_api.py — Phase 29: Analytics REST API Blueprint."""

import logging

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

analytics_api = Blueprint('analytics_api', __name__, url_prefix='/api/v1/analytics')


# ──────────────────────────────────────────────────────────
# Status
# ──────────────────────────────────────────────────────────

@analytics_api.get('/status')
def analytics_status():
    """GET /api/v1/analytics/status — 모듈 상태."""
    return jsonify({
        'status': 'ok',
        'modules': ['sales', 'customers', 'products', 'export'],
    })


# ──────────────────────────────────────────────────────────
# Sales
# ──────────────────────────────────────────────────────────

@analytics_api.get('/sales/daily')
def sales_daily():
    """GET /api/v1/analytics/sales/daily?date=YYYY-MM-DD."""
    from ..analytics.sales_analytics import SalesAnalytics
    date_param = request.args.get('date')
    try:
        result = SalesAnalytics().daily_summary(date=date_param)
        return jsonify(result)
    except Exception as exc:
        logger.error("sales_daily 오류: %s", exc)
        return jsonify({'error': str(exc)}), 500


@analytics_api.get('/sales/weekly')
def sales_weekly():
    """GET /api/v1/analytics/sales/weekly?year=YYYY&week=WW."""
    from ..analytics.sales_analytics import SalesAnalytics
    year = request.args.get('year', type=int)
    week = request.args.get('week', type=int)
    try:
        result = SalesAnalytics().weekly_summary(year=year, week=week)
        return jsonify(result)
    except Exception as exc:
        logger.error("sales_weekly 오류: %s", exc)
        return jsonify({'error': str(exc)}), 500


@analytics_api.get('/sales/monthly')
def sales_monthly():
    """GET /api/v1/analytics/sales/monthly?year=YYYY&month=MM."""
    from ..analytics.sales_analytics import SalesAnalytics
    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)
    try:
        result = SalesAnalytics().monthly_summary(year=year, month=month)
        return jsonify(result)
    except Exception as exc:
        logger.error("sales_monthly 오류: %s", exc)
        return jsonify({'error': str(exc)}), 500


# ──────────────────────────────────────────────────────────
# Customers
# ──────────────────────────────────────────────────────────

@analytics_api.post('/customers/rfm')
def customers_rfm():
    """POST /api/v1/analytics/customers/rfm  body: {orders: [...]}."""
    from ..analytics.customer_analytics import CustomerAnalytics
    body = request.get_json(silent=True) or {}
    orders = body.get('orders', [])
    if not isinstance(orders, list):
        return jsonify({'error': 'orders must be a list'}), 400
    try:
        result = CustomerAnalytics().rfm_analysis(orders)
        return jsonify(result)
    except Exception as exc:
        logger.error("customers_rfm 오류: %s", exc)
        return jsonify({'error': str(exc)}), 500


# ──────────────────────────────────────────────────────────
# Products
# ──────────────────────────────────────────────────────────

@analytics_api.post('/products/abc')
def products_abc():
    """POST /api/v1/analytics/products/abc  body: {products: [...]}."""
    from ..analytics.product_analytics import ProductAnalytics
    body = request.get_json(silent=True) or {}
    products = body.get('products', [])
    if not isinstance(products, list):
        return jsonify({'error': 'products must be a list'}), 400
    try:
        result = ProductAnalytics().abc_classification(products)
        return jsonify(result)
    except Exception as exc:
        logger.error("products_abc 오류: %s", exc)
        return jsonify({'error': str(exc)}), 500


@analytics_api.post('/products/margin')
def products_margin():
    """POST /api/v1/analytics/products/margin  body: {products: [...]}."""
    from ..analytics.product_analytics import ProductAnalytics
    body = request.get_json(silent=True) or {}
    products = body.get('products', [])
    if not isinstance(products, list):
        return jsonify({'error': 'products must be a list'}), 400
    try:
        result = ProductAnalytics().margin_analysis(products)
        return jsonify(result)
    except Exception as exc:
        logger.error("products_margin 오류: %s", exc)
        return jsonify({'error': str(exc)}), 500
