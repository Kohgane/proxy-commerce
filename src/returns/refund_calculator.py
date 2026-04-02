"""src/returns/refund_calculator.py — Phase 37: 환불 금액 계산."""
import logging
from decimal import Decimal
from typing import Optional

logger = logging.getLogger(__name__)

# 등급별 환불 비율
GRADE_REFUND_RATIO = {
    'A': Decimal('1.00'),
    'B': Decimal('0.90'),
    'C': Decimal('0.70'),
    'D': Decimal('0.00'),
}


class RefundCalculator:
    """환불 금액 계산기.

    - 기본 금액 - 배송비 공제
    - 부분 환불 비율 적용 (검수 등급)
    - 쿠폰 사용 시 할인 금액 조정
    """

    def __init__(self, shipping_deduction: Decimal = Decimal('3000')):
        self.shipping_deduction = shipping_deduction

    def calculate(
        self,
        original_amount: Decimal,
        grade: str = 'A',
        deduct_shipping: bool = True,
        coupon_discount: Decimal = Decimal('0'),
        partial_ratio: Optional[Decimal] = None,
    ) -> dict:
        """환불 금액을 계산한다.

        Args:
            original_amount: 원래 결제 금액
            grade: 검수 등급 (A/B/C/D)
            deduct_shipping: 배송비 공제 여부
            coupon_discount: 쿠폰 할인 금액
            partial_ratio: 부분 환불 비율 (None이면 등급 비율 사용)

        Returns:
            계산 결과 딕셔너리
        """
        base = Decimal(str(original_amount))

        # 쿠폰 할인 적용 (쿠폰 할인분은 환불 대상에서 제외)
        coupon = Decimal(str(coupon_discount))
        base = max(base - coupon, Decimal('0'))

        # 배송비 공제
        shipping = self.shipping_deduction if deduct_shipping else Decimal('0')
        after_shipping = max(base - shipping, Decimal('0'))

        # 검수 등급 또는 직접 비율 적용
        if partial_ratio is not None:
            ratio = Decimal(str(partial_ratio))
        else:
            ratio = GRADE_REFUND_RATIO.get(grade.upper(), Decimal('0'))

        refund = (after_shipping * ratio).quantize(Decimal('1'))

        return {
            'original_amount': str(original_amount),
            'coupon_discount': str(coupon_discount),
            'shipping_deduction': str(shipping),
            'grade': grade,
            'ratio': str(ratio),
            'refund_amount': str(refund),
        }

    def calculate_partial(self, original_amount: Decimal, items_returned: int, total_items: int) -> Decimal:
        """부분 반품 시 비율 계산."""
        if total_items <= 0:
            return Decimal('0')
        ratio = Decimal(str(items_returned)) / Decimal(str(total_items))
        return (Decimal(str(original_amount)) * ratio).quantize(Decimal('1'))
