"""src/api/auto_purchase_api.py — 자동 구매 API Blueprint (Phase 96).

Blueprint: /api/v1/auto-purchase

엔드포인트:
  POST /order                         — 자동 구매 주문 생성
  GET  /order/<order_id>              — 구매 상태 조회
  POST /order/<order_id>/cancel       — 구매 취소
  GET  /sources/<product_id>          — 소스 옵션 조회
  POST /sources/select                — 최적 소스 선택
  GET  /metrics                       — 구매 메트릭
  GET  /rules                         — 구매 규칙 목록
  POST /rules                         — 구매 규칙 추가
  POST /simulate                      — 구매 시뮬레이션
  GET  /queue                         — 구매 큐 현황
"""
from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

auto_purchase_bp = Blueprint('auto_purchase', __name__, url_prefix='/api/v1/auto-purchase')

# 지연 초기화 서비스
_engine = None
_selector = None
_rules = None


def _get_engine():
    global _engine
    if _engine is None:
        from ..auto_purchase.purchase_engine import AutoPurchaseEngine
        _engine = AutoPurchaseEngine()
    return _engine


def _get_selector():
    global _selector
    if _selector is None:
        from ..auto_purchase.source_selector import SourceSelector
        _selector = SourceSelector()
    return _selector


def _get_rules():
    global _rules
    if _rules is None:
        from ..auto_purchase.purchase_rules import PurchaseRuleEngine
        _rules = PurchaseRuleEngine()
    return _rules


# ---------------------------------------------------------------------------
# POST /order
# ---------------------------------------------------------------------------

@auto_purchase_bp.post('/order')
def create_order():
    """자동 구매 주문을 생성한다.

    Body:
        source_product_id   — 소스 상품 ID (ASIN 등)
        marketplace         — 마켓플레이스 (amazon_us / amazon_jp / taobao / alibaba_1688)
        quantity            — 수량 (기본 1)
        unit_price          — 단가
        currency            — 통화 (기본 USD)
        selling_price       — 고객 판매가 (마진 계산용)
        customer_order_id   — 원본 고객 주문 ID
        shipping_address    — 배송지 (생략 시 배송대행지 기본 주소)
        priority            — 우선순위 (urgent/normal/low)
    """
    data = request.get_json(force=True, silent=True) or {}
    product_id = data.get('source_product_id', '')
    marketplace = data.get('marketplace', '')
    if not product_id or not marketplace:
        return jsonify({'error': 'source_product_id and marketplace are required'}), 400

    try:
        engine = _get_engine()
        order = engine.submit_order(
            source_product_id=product_id,
            marketplace=marketplace,
            quantity=int(data.get('quantity', 1)),
            unit_price=float(data.get('unit_price', 0)),
            currency=data.get('currency', 'USD'),
            selling_price=float(data.get('selling_price', 0)),
            customer_order_id=data.get('customer_order_id', ''),
            shipping_address=data.get('shipping_address'),
            priority=data.get('priority', 'normal'),
        )
        return jsonify({
            'order_id': order.order_id,
            'status': order.status.value,
            'marketplace': order.source_marketplace,
            'product_id': order.source_product_id,
            'quantity': order.quantity,
            'rule_decision': order.metadata.get('rule_decision', ''),
            'error_message': order.error_message,
        }), 201
    except Exception as exc:
        logger.error('create_order error: %s', exc)
        return jsonify({'error': str(exc)}), 500


# ---------------------------------------------------------------------------
# GET /order/<order_id>
# ---------------------------------------------------------------------------

@auto_purchase_bp.get('/order/<order_id>')
def get_order(order_id: str):
    """구매 상태를 조회한다."""
    try:
        engine = _get_engine()
        status = engine.get_order_status(order_id)
        if not status:
            return jsonify({'error': 'Order not found'}), 404
        return jsonify(status)
    except Exception as exc:
        logger.error('get_order error: %s', exc)
        return jsonify({'error': str(exc)}), 500


# ---------------------------------------------------------------------------
# POST /order/<order_id>/cancel
# ---------------------------------------------------------------------------

@auto_purchase_bp.post('/order/<order_id>/cancel')
def cancel_order(order_id: str):
    """구매를 취소한다."""
    try:
        engine = _get_engine()
        success = engine.cancel_order(order_id)
        if not success:
            return jsonify({'error': 'Cannot cancel order (not found or already shipped)'}), 400
        return jsonify({'order_id': order_id, 'cancelled': True})
    except Exception as exc:
        logger.error('cancel_order error: %s', exc)
        return jsonify({'error': str(exc)}), 500


# ---------------------------------------------------------------------------
# GET /sources/<product_id>
# ---------------------------------------------------------------------------

@auto_purchase_bp.get('/sources/<product_id>')
def get_sources(product_id: str):
    """상품의 소스 옵션을 조회한다."""
    try:
        from ..auto_purchase.marketplace_buyer import AmazonBuyer, TaobaoBuyer, AlibabaBuyer
        buyers = [AmazonBuyer(region='US'), AmazonBuyer(region='JP'), TaobaoBuyer(), AlibabaBuyer()]
        options = []
        for buyer in buyers:
            results = buyer.search_product(product_id)
            options.extend(results)

        return jsonify({
            'product_id': product_id,
            'sources': [
                {
                    'marketplace': o.marketplace,
                    'product_id': o.product_id,
                    'title': o.title,
                    'price': o.price,
                    'currency': o.currency,
                    'availability': o.availability,
                    'stock_quantity': o.stock_quantity,
                    'estimated_delivery_days': o.estimated_delivery_days,
                    'seller_rating': o.seller_rating,
                    'shipping_cost': o.shipping_cost,
                    'total_cost': o.total_cost,
                }
                for o in options
            ],
        })
    except Exception as exc:
        logger.error('get_sources error: %s', exc)
        return jsonify({'error': str(exc)}), 500


# ---------------------------------------------------------------------------
# POST /sources/select
# ---------------------------------------------------------------------------

@auto_purchase_bp.post('/sources/select')
def select_source():
    """최적 소스를 선택한다.

    Body:
        options     — 소스 옵션 목록
        strategy    — 선택 전략 (cheapest_first/fastest_delivery/reliability_first/balanced)
    """
    data = request.get_json(force=True, silent=True) or {}
    options_data = data.get('options', [])
    strategy = data.get('strategy', 'balanced')

    try:
        from ..auto_purchase.purchase_models import SourceOption
        selector = _get_selector()
        options = [
            SourceOption(
                marketplace=o.get('marketplace', ''),
                product_id=o.get('product_id', ''),
                title=o.get('title', ''),
                price=float(o.get('price', 0)),
                currency=o.get('currency', 'USD'),
                availability=bool(o.get('availability', True)),
                stock_quantity=int(o.get('stock_quantity', 0)),
                estimated_delivery_days=int(o.get('estimated_delivery_days', 0)),
                seller_rating=float(o.get('seller_rating', 0)),
                shipping_cost=float(o.get('shipping_cost', 0)),
            )
            for o in options_data
        ]
        selected = selector.select(options, strategy=strategy)
        scores = selector.score_all(options)

        return jsonify({
            'strategy': strategy,
            'selected': {
                'marketplace': selected.marketplace,
                'product_id': selected.product_id,
                'total_cost': selected.total_cost,
                'delivery_days': selected.estimated_delivery_days,
                'seller_rating': selected.seller_rating,
            } if selected else None,
            'scores': scores,
        })
    except Exception as exc:
        logger.error('select_source error: %s', exc)
        return jsonify({'error': str(exc)}), 500


# ---------------------------------------------------------------------------
# GET /metrics
# ---------------------------------------------------------------------------

@auto_purchase_bp.get('/metrics')
def get_metrics():
    """구매 메트릭을 반환한다."""
    try:
        engine = _get_engine()
        return jsonify(engine.get_metrics())
    except Exception as exc:
        logger.error('get_metrics error: %s', exc)
        return jsonify({'error': str(exc)}), 500


# ---------------------------------------------------------------------------
# GET /rules
# ---------------------------------------------------------------------------

@auto_purchase_bp.get('/rules')
def list_rules():
    """구매 규칙 목록을 반환한다."""
    try:
        rules = _get_rules()
        return jsonify({'rules': rules.list_rules()})
    except Exception as exc:
        logger.error('list_rules error: %s', exc)
        return jsonify({'error': str(exc)}), 500


# ---------------------------------------------------------------------------
# POST /rules
# ---------------------------------------------------------------------------

@auto_purchase_bp.post('/rules')
def add_rule():
    """구매 규칙을 추가한다.

    Body:
        type        — max_price | min_margin | daily_limit | blacklist_seller | blacklist_product
        value       — 규칙 파라미터
    """
    data = request.get_json(force=True, silent=True) or {}
    rule_type = data.get('type', '')
    value = data.get('value')

    try:
        from ..auto_purchase.purchase_rules import (
            MaxPriceRule, MinMarginRule, DailyLimitRule, BlacklistRule,
        )
        rules = _get_rules()

        if rule_type == 'max_price':
            rules.add_rule(MaxPriceRule(max_price=float(value or 1000)))
        elif rule_type == 'min_margin':
            rules.add_rule(MinMarginRule(min_margin_rate=float(value or 0.15)))
        elif rule_type == 'daily_limit':
            rules.add_rule(DailyLimitRule(max_daily_orders=int(value or 50)))
        elif rule_type in ('blacklist_seller', 'blacklist_product'):
            bl_rule = next((r for r in rules._rules if r.name == 'blacklist'), None)
            if bl_rule is None:
                bl_rule = BlacklistRule()
                rules.add_rule(bl_rule)
            if rule_type == 'blacklist_seller':
                bl_rule.add_seller(str(value))
            else:
                bl_rule.add_product(str(value))
        else:
            return jsonify({'error': f'Unknown rule type: {rule_type}'}), 400

        return jsonify({'added': True, 'type': rule_type, 'rules': rules.list_rules()}), 201
    except Exception as exc:
        logger.error('add_rule error: %s', exc)
        return jsonify({'error': str(exc)}), 500


# ---------------------------------------------------------------------------
# POST /simulate
# ---------------------------------------------------------------------------

@auto_purchase_bp.post('/simulate')
def simulate():
    """구매 시뮬레이션 (실제 구매 없음).

    Body:
        source_product_id, marketplace, quantity, unit_price, currency, selling_price, strategy
    """
    data = request.get_json(force=True, silent=True) or {}
    product_id = data.get('source_product_id', '')
    marketplace = data.get('marketplace', '')
    if not product_id or not marketplace:
        return jsonify({'error': 'source_product_id and marketplace are required'}), 400

    try:
        engine = _get_engine()
        result = engine.simulate(
            source_product_id=product_id,
            marketplace=marketplace,
            quantity=int(data.get('quantity', 1)),
            unit_price=float(data.get('unit_price', 0)),
            currency=data.get('currency', 'USD'),
            selling_price=float(data.get('selling_price', 0)),
            strategy=data.get('strategy', 'balanced'),
        )
        return jsonify(result)
    except Exception as exc:
        logger.error('simulate error: %s', exc)
        return jsonify({'error': str(exc)}), 500


# ---------------------------------------------------------------------------
# GET /queue
# ---------------------------------------------------------------------------

@auto_purchase_bp.get('/queue')
def get_queue():
    """구매 큐 현황을 반환한다."""
    try:
        engine = _get_engine()
        return jsonify(engine.get_queue_status())
    except Exception as exc:
        logger.error('get_queue error: %s', exc)
        return jsonify({'error': str(exc)}), 500
