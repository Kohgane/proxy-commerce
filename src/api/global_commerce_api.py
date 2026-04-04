"""src/api/global_commerce_api.py — 글로벌 커머스 API Blueprint (Phase 93).

Blueprint: /api/v1/global

엔드포인트:
  GET  /products/<sku>              — 로케일별 상품 조회
  POST /payments/route              — 결제 라우팅 조회
  POST /trade/import                — 수입 주문 생성
  POST /trade/export                — 수출 주문 생성
  GET  /trade/<order_id>/status     — 무역 주문 상태 조회
  POST /customs/calculate           — 관세 계산
  POST /shipping/calculate          — 국제 배송비 계산
  GET  /shipping/forwarding/status  — 배송대행지 상태
"""
from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

global_commerce_bp = Blueprint("global_commerce", __name__, url_prefix="/api/v1/global")

# ---------------------------------------------------------------------------
# 지연 초기화 서비스
# ---------------------------------------------------------------------------

_i18n_mgr = None
_product_page = None
_payment_router = None
_settlement = None
_compliance = None
_import_mgr = None
_export_mgr = None
_trade_compliance = None
_shipping_mgr = None
_insurance = None
_moltail = None
_ohmyzip = None


def _get_i18n():
    global _i18n_mgr, _product_page
    if _i18n_mgr is None:
        from ..global_commerce.i18n.i18n_manager import I18nManager
        from ..global_commerce.i18n.localized_product_page import LocalizedProductPage
        _i18n_mgr = I18nManager()
        _product_page = LocalizedProductPage(i18n_manager=_i18n_mgr)
    return _i18n_mgr, _product_page


def _get_payments():
    global _payment_router, _settlement, _compliance
    if _payment_router is None:
        from ..global_commerce.payments.global_payment_router import GlobalPaymentRouter
        from ..global_commerce.payments.cross_border_settlement import CrossBorderSettlement
        from ..global_commerce.payments.payment_compliance_checker import PaymentComplianceChecker
        _payment_router = GlobalPaymentRouter()
        _settlement = CrossBorderSettlement()
        _compliance = PaymentComplianceChecker()
    return _payment_router, _settlement, _compliance


def _get_trade():
    global _import_mgr, _export_mgr, _trade_compliance
    if _import_mgr is None:
        from ..global_commerce.trade.import_manager import ImportManager
        from ..global_commerce.trade.export_manager import ExportManager
        from ..global_commerce.trade.trade_compliance_checker import TradeComplianceChecker
        _import_mgr = ImportManager()
        _export_mgr = ExportManager()
        _trade_compliance = TradeComplianceChecker()
    return _import_mgr, _export_mgr, _trade_compliance


def _get_shipping():
    global _shipping_mgr, _insurance, _moltail, _ohmyzip
    if _shipping_mgr is None:
        from ..global_commerce.shipping.international_shipping_manager import InternationalShippingManager
        from ..global_commerce.shipping.shipping_insurance import ShippingInsurance
        from ..global_commerce.shipping.forwarding_agent import MoltailAgent, OhmyzipAgent
        _shipping_mgr = InternationalShippingManager()
        _insurance = ShippingInsurance()
        _moltail = MoltailAgent()
        _ohmyzip = OhmyzipAgent()
    return _shipping_mgr, _insurance, _moltail, _ohmyzip


# ---------------------------------------------------------------------------
# 다국어 상품
# ---------------------------------------------------------------------------

@global_commerce_bp.get("/products/<sku>")
def get_localized_product(sku: str):
    """로케일별 상품 조회."""
    _, product_page = _get_i18n()
    locale = request.args.get("locale", "ko")
    accept_lang = request.headers.get("Accept-Language", "")
    detected_locale = product_page.detect_locale(
        accept_language=accept_lang,
        user_preference=locale,
    )
    price = float(request.args.get("price", 0))
    image_url = request.args.get("image_url", "")
    result = product_page.build(sku=sku, locale=detected_locale, price=price, image_url=image_url)
    if result.get("error"):
        return jsonify(result), 404
    return jsonify(result)


@global_commerce_bp.post("/products/<sku>/content")
def set_product_content(sku: str):
    """로케일별 상품 콘텐츠 등록."""
    i18n_mgr, _ = _get_i18n()
    data = request.get_json(silent=True) or {}
    locale = data.get("locale", "ko")
    title = data.get("title", "")
    description = data.get("description", "")
    features = data.get("features", [])
    if not title:
        return jsonify({"error": "title 필드가 필요합니다."}), 400
    try:
        content = i18n_mgr.set_content(sku, locale, title, description, features)
        return jsonify(content), 201
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


# ---------------------------------------------------------------------------
# 결제 라우팅
# ---------------------------------------------------------------------------

@global_commerce_bp.post("/payments/route")
def route_payment():
    """결제 라우팅 조회."""
    router, settlement, compliance_checker = _get_payments()
    data = request.get_json(silent=True) or {}
    country = data.get("country", "KR")
    currency = data.get("currency", "KRW")
    amount = float(data.get("amount", 0))

    route = router.route(country=country, currency=currency)
    compliance = compliance_checker.check(amount=amount, currency=currency, country=country)
    settlement_cycle = settlement.get_settlement_cycle(currency)

    return jsonify({
        "route": route.to_dict(),
        "compliance": compliance.to_dict(),
        "settlement_days": settlement_cycle,
    })


# ---------------------------------------------------------------------------
# 무역 주문
# ---------------------------------------------------------------------------

@global_commerce_bp.post("/trade/import")
def create_import_order():
    """수입 주문 생성."""
    import_mgr, _, trade_compliance = _get_trade()
    data = request.get_json(silent=True) or {}
    required = ("product_url", "source_country")
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"error": f"필수 필드 누락: {', '.join(missing)}"}), 400

    # 규정 체크
    comp = trade_compliance.check(
        direction='import',
        source_country=data.get('source_country', ''),
        destination_country=data.get('destination_country', 'KR'),
        product_name=data.get('product_name', ''),
        quantity=int(data.get('quantity', 1)),
    )
    if not comp.passed:
        return jsonify({"error": "수출입 규정 위반", "details": comp.to_dict()}), 400

    order = import_mgr.create(
        product_url=data['product_url'],
        source_country=data['source_country'],
        destination_country=data.get('destination_country', 'KR'),
        product_name=data.get('product_name', ''),
        quantity=int(data.get('quantity', 1)),
        unit_price_usd=float(data.get('unit_price_usd', 0)),
        hs_code=data.get('hs_code', 'DEFAULT'),
        customer_id=data.get('customer_id', ''),
        notes=data.get('notes', ''),
    )
    return jsonify(order.to_dict()), 201


@global_commerce_bp.post("/trade/export")
def create_export_order():
    """수출 주문 생성."""
    _, export_mgr, trade_compliance = _get_trade()
    data = request.get_json(silent=True) or {}
    required = ("product_name", "source_country", "destination_country")
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"error": f"필수 필드 누락: {', '.join(missing)}"}), 400

    comp = trade_compliance.check(
        direction='export',
        source_country=data.get('source_country', ''),
        destination_country=data.get('destination_country', ''),
        product_name=data.get('product_name', ''),
        quantity=int(data.get('quantity', 1)),
    )
    if not comp.passed:
        return jsonify({"error": "수출입 규정 위반", "details": comp.to_dict()}), 400

    order = export_mgr.create(
        product_name=data['product_name'],
        source_country=data['source_country'],
        destination_country=data['destination_country'],
        quantity=int(data.get('quantity', 1)),
        unit_price_usd=float(data.get('unit_price_usd', 0)),
        customer_name=data.get('customer_name', ''),
        customer_address=data.get('customer_address', ''),
        notes=data.get('notes', ''),
    )
    return jsonify(order.to_dict()), 201


@global_commerce_bp.get("/trade/<order_id>/status")
def get_trade_status(order_id: str):
    """무역 주문 상태 조회."""
    import_mgr, export_mgr, _ = _get_trade()
    order = import_mgr.get(order_id)
    if order:
        return jsonify({"type": "import", "order": order.to_dict()})
    order = export_mgr.get(order_id)
    if order:
        return jsonify({"type": "export", "order": order.to_dict()})
    return jsonify({"error": "주문을 찾을 수 없습니다."}), 404


# ---------------------------------------------------------------------------
# 관세 계산
# ---------------------------------------------------------------------------

@global_commerce_bp.post("/customs/calculate")
def calculate_customs():
    """관세 계산."""
    import_mgr, _, _ = _get_trade()
    data = request.get_json(silent=True) or {}
    required = ("price_usd", "source_country")
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"error": f"필수 필드 누락: {', '.join(missing)}"}), 400

    result = import_mgr.duty_calculator.calculate(
        total_price_usd=float(data['price_usd']),
        hs_code=data.get('hs_code', 'DEFAULT'),
        source_country=data['source_country'],
        usd_to_krw=float(data.get('usd_to_krw', 1350.0)),
    )
    return jsonify(result)


# ---------------------------------------------------------------------------
# 국제 배송
# ---------------------------------------------------------------------------

@global_commerce_bp.post("/shipping/calculate")
def calculate_shipping():
    """국제 배송비 계산."""
    shipping_mgr, insurance, _, _ = _get_shipping()
    data = request.get_json(silent=True) or {}
    required = ("weight_kg", "origin_country", "destination_country")
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"error": f"필수 필드 누락: {', '.join(missing)}"}), 400

    quote = shipping_mgr.calculate(
        weight_kg=float(data['weight_kg']),
        origin_country=data['origin_country'],
        destination_country=data['destination_country'],
        length_cm=float(data.get('length_cm', 0)),
        width_cm=float(data.get('width_cm', 0)),
        height_cm=float(data.get('height_cm', 0)),
    )

    result = quote.to_dict()

    # 보험 견적 (declared_value 있을 때)
    declared_value = float(data.get('declared_value_krw', 0))
    if declared_value > 0:
        ins_quote = insurance.calculate(declared_value, data['destination_country'])
        result['insurance'] = ins_quote.to_dict()

    return jsonify(result)


@global_commerce_bp.get("/shipping/forwarding/status")
def get_forwarding_status():
    """배송대행지 상태 조회."""
    _, _, moltail, ohmyzip = _get_shipping()
    return jsonify({
        "agents": [
            moltail.get_status(),
            ohmyzip.get_status(),
        ]
    })
