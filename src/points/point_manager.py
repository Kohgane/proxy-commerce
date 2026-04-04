"""src/points/point_manager.py — 포인트 잔액 관리자 (Phase 92).

사용자별 포인트 잔액을 인메모리 dict로 관리하며 적립/사용/조회를 처리한다.

규칙:
  - 최소 사용 포인트: 1,000P
  - 최대 사용 비율: 결제 금액의 50%
  - 포인트 유효기간: 적립일로부터 365일
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from .point_history import HistoryType, PointHistory
from .point_policy import BonusType, PointPolicy

logger = logging.getLogger(__name__)

MIN_USE_POINTS = 1_000
MAX_USE_RATIO = 0.5  # 결제 금액의 50%


@dataclass
class PointLot:
    """포인트 적립 배치 (유효기간 추적용)."""

    lot_id: str
    user_id: str
    amount: int
    remaining: int
    earned_at: str
    expires_at: str
    reason: str
    order_id: Optional[str] = None

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        """현재 시각 기준으로 만료 여부를 반환한다."""
        _now = now or datetime.now(timezone.utc)
        return _now.isoformat() > self.expires_at

    def to_dict(self) -> dict:
        """딕셔너리로 변환한다."""
        return {
            "lot_id": self.lot_id,
            "user_id": self.user_id,
            "amount": self.amount,
            "remaining": self.remaining,
            "earned_at": self.earned_at,
            "expires_at": self.expires_at,
            "reason": self.reason,
            "order_id": self.order_id,
        }


class PointManager:
    """포인트 적립/사용/잔액 관리자.

    인메모리 dict 기반으로 사용자별 포인트를 관리한다.
    """

    def __init__(
        self,
        history: Optional[PointHistory] = None,
        policy: Optional[PointPolicy] = None,
    ) -> None:
        self._balances: Dict[str, int] = {}  # user_id → 현재 잔액
        self._lots: List[PointLot] = []  # 전체 적립 배치
        self._history = history or PointHistory()
        self._policy = policy or PointPolicy()

    # ------------------------------------------------------------------
    # 잔액 조회
    # ------------------------------------------------------------------

    def get_balance(self, user_id: str) -> int:
        """사용자 포인트 잔액을 반환한다."""
        return self._balances.get(user_id, 0)

    # ------------------------------------------------------------------
    # 포인트 적립
    # ------------------------------------------------------------------

    def earn(
        self,
        user_id: str,
        amount: int,
        reason: str,
        order_id: Optional[str] = None,
        expiry_days: int = 365,
    ) -> PointLot:
        """포인트를 적립한다.

        Args:
            user_id: 사용자 ID
            amount: 적립 포인트 (양수)
            reason: 적립 사유
            order_id: 연관 주문 ID
            expiry_days: 유효기간 (기본 365일)

        Returns:
            생성된 PointLot
        """
        if amount <= 0:
            raise ValueError(f"적립 포인트는 양수여야 합니다: {amount}")

        now = datetime.now(timezone.utc)
        expires_at = (now + timedelta(days=expiry_days)).isoformat()
        lot = PointLot(
            lot_id=str(uuid.uuid4()),
            user_id=user_id,
            amount=amount,
            remaining=amount,
            earned_at=now.isoformat(),
            expires_at=expires_at,
            reason=reason,
            order_id=order_id,
        )
        self._lots.append(lot)
        self._balances[user_id] = self.get_balance(user_id) + amount
        self._history.record(
            user_id=user_id,
            history_type=HistoryType.EARN,
            amount=amount,
            balance_after=self._balances[user_id],
            reason=reason,
            order_id=order_id,
        )
        logger.info("포인트 적립: user=%s amount=%d balance=%d", user_id, amount, self._balances[user_id])
        return lot

    def earn_from_order(
        self,
        user_id: str,
        order_amount: int,
        grade: str,
        order_id: Optional[str] = None,
    ) -> PointLot:
        """주문 금액과 등급에 따른 포인트를 자동 적립한다."""
        points = self._policy.calculate_earn_points(order_amount, grade)
        if points <= 0:
            points = 1  # 최소 1 포인트
        return self.earn(
            user_id=user_id,
            amount=points,
            reason=f"주문 적립 ({grade} 등급, 주문 금액 {order_amount:,}원)",
            order_id=order_id,
        )

    def earn_special(
        self,
        user_id: str,
        bonus_type: BonusType,
        order_id: Optional[str] = None,
    ) -> Optional[PointLot]:
        """특별 보너스 포인트를 적립한다."""
        amount = self._policy.get_special_bonus(bonus_type)
        if amount <= 0:
            return None
        return self.earn(
            user_id=user_id,
            amount=amount,
            reason=f"특별 보너스: {bonus_type.value}",
            order_id=order_id,
        )

    # ------------------------------------------------------------------
    # 포인트 사용
    # ------------------------------------------------------------------

    def use(
        self,
        user_id: str,
        use_amount: int,
        payment_amount: int,
        reason: str,
        order_id: Optional[str] = None,
    ) -> int:
        """포인트를 사용한다.

        Args:
            user_id: 사용자 ID
            use_amount: 사용할 포인트
            payment_amount: 결제 금액 (최대 사용 비율 체크용)
            reason: 사용 사유
            order_id: 연관 주문 ID

        Returns:
            실제 차감된 포인트

        Raises:
            ValueError: 최소 사용 포인트 미달, 잔액 부족, 최대 사용 비율 초과
        """
        if use_amount < MIN_USE_POINTS:
            raise ValueError(f"최소 {MIN_USE_POINTS:,}P 이상 사용해야 합니다.")

        max_usable = int(payment_amount * MAX_USE_RATIO)
        if use_amount > max_usable:
            raise ValueError(
                f"결제 금액의 {int(MAX_USE_RATIO * 100)}% 이하만 사용 가능합니다 "
                f"(최대 {max_usable:,}P)."
            )

        balance = self.get_balance(user_id)
        if use_amount > balance:
            raise ValueError(f"포인트 잔액이 부족합니다 (보유 {balance:,}P, 사용 요청 {use_amount:,}P).")

        self._balances[user_id] = balance - use_amount
        self._history.record(
            user_id=user_id,
            history_type=HistoryType.USE,
            amount=use_amount,
            balance_after=self._balances[user_id],
            reason=reason,
            order_id=order_id,
        )
        logger.info("포인트 사용: user=%s amount=%d balance=%d", user_id, use_amount, self._balances[user_id])
        return use_amount

    def cancel_use(
        self,
        user_id: str,
        amount: int,
        reason: str,
        order_id: Optional[str] = None,
    ) -> int:
        """사용 취소 — 사용한 포인트를 되돌린다."""
        if amount <= 0:
            raise ValueError(f"취소 포인트는 양수여야 합니다: {amount}")
        self._balances[user_id] = self.get_balance(user_id) + amount
        self._history.record(
            user_id=user_id,
            history_type=HistoryType.CANCEL,
            amount=amount,
            balance_after=self._balances[user_id],
            reason=reason,
            order_id=order_id,
        )
        logger.info("포인트 사용 취소: user=%s amount=%d", user_id, amount)
        return amount

    # ------------------------------------------------------------------
    # 내부 헬퍼
    # ------------------------------------------------------------------

    def get_lots_for_user(self, user_id: str) -> List[PointLot]:
        """사용자의 전체 적립 배치를 반환한다."""
        return [lot for lot in self._lots if lot.user_id == user_id]

    @property
    def history(self) -> PointHistory:
        """PointHistory 인스턴스를 반환한다."""
        return self._history

    @property
    def policy(self) -> PointPolicy:
        """PointPolicy 인스턴스를 반환한다."""
        return self._policy
