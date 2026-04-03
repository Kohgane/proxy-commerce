"""src/shipping_calculator/weight_based_rule.py — 무게 기반 배송비 규칙."""
from __future__ import annotations


class WeightBasedRule:
    """무게 기반 배송비 계산 규칙."""

    _TIERS = [
        (0, 500, 3000),
        (501, 2000, 4000),
        (2001, 5000, 6000),
        (5001, float('inf'), 10000),
    ]

    def calculate(self, weight_g: float) -> float:
        """무게에 따른 배송비를 계산한다."""
        for min_g, max_g, price in self._TIERS:
            if min_g <= weight_g <= max_g:
                return float(price)
        return 10000.0
