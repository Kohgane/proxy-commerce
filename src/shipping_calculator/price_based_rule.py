"""src/shipping_calculator/price_based_rule.py — 주문 금액 기반 배송비 규칙."""
from __future__ import annotations


class PriceBasedRule:
    """주문 금액 기반 배송비 계산 규칙."""

    def __init__(self, free_threshold: float = 50000) -> None:
        self.free_threshold = free_threshold

    def calculate(self, order_price: float, base_price: float) -> float:
        """주문 금액에 따른 배송비를 계산한다."""
        if order_price >= self.free_threshold:
            return 0.0
        return base_price
