"""src/api/shipping_calculator_api.py — 배송비 계산기 API (Phase 80)."""
from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

shipping_calculator_bp = Blueprint("shipping_calculator", __name__, url_prefix="/api/v1/shipping-calc")


@shipping_calculator_bp.post("/calculate")
def calculate():
    """배송비를 계산한다."""
    from ..shipping_calculator import ShippingCalculator
    data = request.get_json(silent=True) or {}
    calc = ShippingCalculator()
    result = calc.calculate(
        weight_g=float(data.get('weight_g', 500)),
        zone=data.get('zone', 'domestic'),
        order_price=float(data.get('order_price', 0)),
        carrier=data.get('carrier', 'CJ'),
    )
    return jsonify(result)


@shipping_calculator_bp.get("/zones")
def list_zones():
    """배송 구역 목록을 반환한다."""
    from ..shipping_calculator import ShippingZone
    return jsonify(ShippingZone().list_zones())


@shipping_calculator_bp.get("/rates")
def list_rates():
    """배송 요금 목록을 반환한다."""
    from ..shipping_calculator import WeightBasedRule
    rule = WeightBasedRule()
    rates = [
        {'weight_range': '0-500g', 'price': rule.calculate(500)},
        {'weight_range': '501-2000g', 'price': rule.calculate(1000)},
        {'weight_range': '2001-5000g', 'price': rule.calculate(3000)},
        {'weight_range': '5001g+', 'price': rule.calculate(6000)},
    ]
    return jsonify(rates)


@shipping_calculator_bp.post("/estimate")
def estimate():
    """배송 기간을 추정한다."""
    from ..shipping_calculator import ShippingEstimator
    data = request.get_json(silent=True) or {}
    est = ShippingEstimator()
    result = est.estimate(
        carrier=data.get('carrier', 'CJ'),
        zone=data.get('zone', 'domestic'),
    )
    return jsonify(result)
