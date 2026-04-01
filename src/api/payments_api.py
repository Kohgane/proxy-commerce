"""src/api/payments_api.py — 결제/정산 API Blueprint.

엔드포인트:
  GET  /api/v1/payments/status              — 모듈 상태 확인
  POST /api/v1/payments/calculate-settlement — 단건 정산 계산
  GET  /api/v1/payments/fee-rates           — 플랫폼별 수수료율
"""

import logging

from flask import Blueprint, jsonify, request

from ..payments.fee_calculator import FeeCalculator
from ..payments.settlement import SettlementCalculator

logger = logging.getLogger(__name__)

payments_bp = Blueprint("payments", __name__, url_prefix="/api/v1/payments")

_fee_calc = FeeCalculator()
_settlement_calc = SettlementCalculator()


@payments_bp.get("/status")
def get_status():
    """결제 모듈 상태를 반환한다."""
    return jsonify({"status": "ok", "module": "payments"})


@payments_bp.post("/calculate-settlement")
def calculate_settlement():
    """단건 주문 정산을 계산한다.

    요청 본문: {"order": {order_id, sale_price, cost_price, platform, shipping_fee, fx_diff}}
    """
    body = request.get_json(force=True, silent=True) or {}
    order = body.get("order")
    if not order:
        return jsonify({"error": "order 필드가 필요합니다."}), 400
    required = {"order_id", "sale_price", "cost_price", "platform"}
    missing = required - set(order.keys())
    if missing:
        return jsonify({"error": f"필수 필드 누락: {missing}"}), 400
    try:
        settlement = _settlement_calc.calculate(order)
        return jsonify({
            "order_id": settlement.order_id,
            "sale_price": settlement.sale_price,
            "cost_price": settlement.cost_price,
            "platform_fee": settlement.platform_fee,
            "shipping_fee": settlement.shipping_fee,
            "fx_diff": settlement.fx_diff,
            "net_profit": settlement.net_profit,
            "settled": settlement.settled,
        })
    except Exception as exc:
        logger.error("calculate_settlement 오류: %s", exc)
        return jsonify({"error": "정산 계산 중 오류가 발생했습니다."}), 500


@payments_bp.get("/fee-rates")
def get_fee_rates():
    """플랫폼별 수수료율을 반환한다."""
    rates = {p: _fee_calc.get_fee_rate(p) for p in _fee_calc.list_platforms()}
    return jsonify({"fee_rates": rates})
