"""src/coupons/rules.py — Phase 38: 쿠폰 적용 규칙."""
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from decimal import Decimal
from typing import List

logger = logging.getLogger(__name__)


class CouponRule(ABC):
    """쿠폰 적용 규칙 추상 기반 클래스."""

    @abstractmethod
    def is_applicable(self, order: dict, coupon: dict) -> bool:
        """쿠폰 적용 가능 여부 확인."""

    @abstractmethod
    def calculate_discount(self, order: dict, coupon: dict) -> Decimal:
        """할인 금액 계산."""


class MinOrderAmountRule(CouponRule):
    """최소 주문 금액 규칙."""

    def is_applicable(self, order: dict, coupon: dict) -> bool:
        order_amount = Decimal(str(order.get('total_amount', 0)))
        min_amount = Decimal(coupon.get('min_order_amount', '0'))
        return order_amount >= min_amount

    def calculate_discount(self, order: dict, coupon: dict) -> Decimal:
        if not self.is_applicable(order, coupon):
            return Decimal('0')
        return _base_discount(order, coupon)


class ProductCategoryRule(CouponRule):
    """상품 카테고리 규칙."""

    def is_applicable(self, order: dict, coupon: dict) -> bool:
        applicable_cats = coupon.get('applicable_categories', [])
        if not applicable_cats:
            return True  # 카테고리 제한 없음
        order_cats = [item.get('category', '') for item in order.get('items', [])]
        return bool(set(applicable_cats) & set(order_cats))

    def calculate_discount(self, order: dict, coupon: dict) -> Decimal:
        if not self.is_applicable(order, coupon):
            return Decimal('0')
        applicable_cats = coupon.get('applicable_categories', [])
        if not applicable_cats:
            return _base_discount(order, coupon)
        # 해당 카테고리 상품 금액에만 적용
        eligible_amount = sum(
            Decimal(str(item.get('price', 0))) * int(item.get('qty', 1))
            for item in order.get('items', [])
            if item.get('category', '') in applicable_cats
        )
        return _apply_coupon_value(coupon, eligible_amount)


class DateRangeRule(CouponRule):
    """유효 기간 규칙."""

    def is_applicable(self, order: dict, coupon: dict) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        valid_from = coupon.get('valid_from', '')
        valid_until = coupon.get('valid_until', '')
        if valid_from and now < valid_from:
            return False
        if valid_until and now > valid_until:
            return False
        return True

    def calculate_discount(self, order: dict, coupon: dict) -> Decimal:
        if not self.is_applicable(order, coupon):
            return Decimal('0')
        return _base_discount(order, coupon)


class FirstPurchaseRule(CouponRule):
    """첫 구매 전용 규칙."""

    def __init__(self, purchase_history: List[str] = None):
        # purchase_history: 이미 구매한 user_id 목록
        self._purchased = set(purchase_history or [])

    def is_applicable(self, order: dict, coupon: dict) -> bool:
        if not coupon.get('first_purchase_only', False):
            return True
        user_id = order.get('user_id', '')
        return user_id not in self._purchased

    def calculate_discount(self, order: dict, coupon: dict) -> Decimal:
        if not self.is_applicable(order, coupon):
            return Decimal('0')
        return _base_discount(order, coupon)


def _base_discount(order: dict, coupon: dict) -> Decimal:
    """기본 할인 금액 계산."""
    order_amount = Decimal(str(order.get('total_amount', 0)))
    return _apply_coupon_value(coupon, order_amount)


def _apply_coupon_value(coupon: dict, amount: Decimal) -> Decimal:
    """쿠폰 타입에 따라 할인 금액 계산."""
    coupon_type = coupon.get('type', 'percentage')
    value = Decimal(str(coupon.get('value', 0)))
    max_discount = Decimal(str(coupon.get('max_discount', 0)))

    if coupon_type == 'percentage':
        discount = amount * value / Decimal('100')
    elif coupon_type == 'fixed_amount':
        discount = min(value, amount)
    elif coupon_type == 'free_shipping':
        shipping = Decimal(str(coupon.get('shipping_amount', '3000')))
        discount = shipping
    else:
        discount = Decimal('0')

    if max_discount > 0:
        discount = min(discount, max_discount)
    return discount.quantize(Decimal('1'))
