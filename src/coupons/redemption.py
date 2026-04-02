"""src/coupons/redemption.py — Phase 38: 쿠폰 사용 처리."""
import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class RedemptionService:
    """쿠폰 사용 처리 서비스.

    - 쿠폰 사용 (중복 방지)
    - 사용 이력 추적
    """

    def __init__(self):
        self._history: Dict[str, dict] = {}  # redemption_id → record
        self._used: Dict[str, set] = {}  # coupon_id → set of order_ids

    def redeem(
        self,
        coupon_id: str,
        order_id: str,
        user_id: str,
        discount_amount: Decimal,
    ) -> dict:
        """쿠폰 사용 처리.

        Args:
            coupon_id: 쿠폰 ID
            order_id: 주문 ID
            user_id: 사용자 ID
            discount_amount: 적용된 할인 금액

        Returns:
            사용 이력 레코드

        Raises:
            ValueError: 이미 사용된 경우
        """
        # 중복 사용 방지
        used_orders = self._used.get(coupon_id, set())
        if order_id in used_orders:
            raise ValueError(f"쿠폰 {coupon_id}은 이미 주문 {order_id}에 사용되었습니다")

        redemption_id = str(uuid.uuid4())[:8]
        record = {
            'id': redemption_id,
            'coupon_id': coupon_id,
            'order_id': order_id,
            'user_id': user_id,
            'discount_amount': str(discount_amount),
            'redeemed_at': datetime.now(timezone.utc).isoformat(),
        }
        self._history[redemption_id] = record
        if coupon_id not in self._used:
            self._used[coupon_id] = set()
        self._used[coupon_id].add(order_id)
        logger.info("쿠폰 사용: %s → order=%s user=%s", coupon_id, order_id, user_id)
        return record

    def get_history(self, coupon_id: Optional[str] = None, user_id: Optional[str] = None) -> List[dict]:
        """사용 이력 조회."""
        items = list(self._history.values())
        if coupon_id:
            items = [r for r in items if r['coupon_id'] == coupon_id]
        if user_id:
            items = [r for r in items if r['user_id'] == user_id]
        return sorted(items, key=lambda x: x['redeemed_at'], reverse=True)

    def is_used(self, coupon_id: str, order_id: str) -> bool:
        """쿠폰이 특정 주문에 이미 사용되었는지 확인."""
        return order_id in self._used.get(coupon_id, set())

    def usage_count(self, coupon_id: str) -> int:
        """쿠폰 총 사용 횟수."""
        return len(self._used.get(coupon_id, set()))
