"""src/shipping_calculator/shipping_calculator.py — 통합 배송비 계산기."""
from __future__ import annotations

from .weight_based_rule import WeightBasedRule
from .price_based_rule import PriceBasedRule


class ShippingCalculator:
    """통합 배송비 계산기."""

    def __init__(self) -> None:
        self._weight_rule = WeightBasedRule()
        self._price_rule = PriceBasedRule()

    def calculate(
        self,
        weight_g: float,
        zone: str,
        order_price: float = 0,
        carrier: str = 'CJ',
    ) -> dict:
        """배송비를 계산한다."""
        base = self._weight_rule.calculate(weight_g)
        price = self._price_rule.calculate(order_price, base)
        return {
            'zone': zone,
            'weight_g': weight_g,
            'price': price,
            'carrier': carrier,
            'method': 'standard',
        }
