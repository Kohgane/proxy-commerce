"""src/shipping_calculator/free_shipping_promotion.py — 무료 배송 프로모션."""
from __future__ import annotations


class FreeShippingPromotion:
    """무료 배송 프로모션."""

    def __init__(self, threshold: float = 50000) -> None:
        self.threshold = threshold

    def qualifies(self, order_price: float) -> bool:
        """무료 배송 자격 여부를 반환한다."""
        return order_price >= self.threshold
