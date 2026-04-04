"""src/points/point_policy.py — 포인트 정책 관리 (Phase 92).

등급별 적립률, 이벤트 보너스, 특별 적립 보너스를 관리한다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List

logger = logging.getLogger(__name__)

# 기본 등급별 적립률 (소수점, ex: 0.01 = 1%)
DEFAULT_RATES: Dict[str, float] = {
    "bronze": 0.01,
    "silver": 0.02,
    "gold": 0.03,
    "vip": 0.05,
}

# 특별 보너스 포인트
FIRST_PURCHASE_BONUS = 1000
BIRTHDAY_BONUS = 500
REVIEW_BONUS = 200


class BonusType(str, Enum):
    """특별 보너스 타입."""

    FIRST_PURCHASE = "first_purchase"
    BIRTHDAY = "birthday"
    REVIEW = "review"
    EVENT = "event"


@dataclass
class EventBonus:
    """이벤트 보너스 정의."""

    event_id: str
    name: str
    multiplier: float  # 기본 적립률에 곱하는 배수 (ex: 2.0 = 더블 포인트)
    active: bool = True

    def to_dict(self) -> dict:
        """딕셔너리로 변환한다."""
        return {
            "event_id": self.event_id,
            "name": self.name,
            "multiplier": self.multiplier,
            "active": self.active,
        }


class PointPolicy:
    """포인트 정책 관리자.

    등급별 적립률 설정/조회, 이벤트 보너스 적립률, 특별 적립 보너스를 관리한다.
    """

    def __init__(self) -> None:
        self._rates: Dict[str, float] = dict(DEFAULT_RATES)
        self._events: Dict[str, EventBonus] = {}
        self._special_bonuses: Dict[BonusType, int] = {
            BonusType.FIRST_PURCHASE: FIRST_PURCHASE_BONUS,
            BonusType.BIRTHDAY: BIRTHDAY_BONUS,
            BonusType.REVIEW: REVIEW_BONUS,
        }

    # ------------------------------------------------------------------
    # 등급별 적립률
    # ------------------------------------------------------------------

    def get_rate(self, grade: str) -> float:
        """등급별 기본 적립률을 반환한다."""
        return self._rates.get(grade.lower(), self._rates["bronze"])

    def set_rate(self, grade: str, rate: float) -> None:
        """등급별 적립률을 설정한다 (0~1 범위)."""
        if not (0 <= rate <= 1):
            raise ValueError(f"적립률은 0~1 범위여야 합니다: {rate}")
        self._rates[grade.lower()] = rate
        logger.info("적립률 업데이트: %s → %.4f", grade, rate)

    def get_all_rates(self) -> Dict[str, float]:
        """전체 등급별 적립률을 반환한다."""
        return dict(self._rates)

    # ------------------------------------------------------------------
    # 이벤트 보너스
    # ------------------------------------------------------------------

    def add_event(self, event_id: str, name: str, multiplier: float) -> EventBonus:
        """이벤트 보너스를 등록한다."""
        if multiplier <= 0:
            raise ValueError(f"배수는 0보다 커야 합니다: {multiplier}")
        ev = EventBonus(event_id=event_id, name=name, multiplier=multiplier)
        self._events[event_id] = ev
        return ev

    def deactivate_event(self, event_id: str) -> bool:
        """이벤트를 비활성화한다."""
        ev = self._events.get(event_id)
        if ev is None:
            return False
        ev.active = False
        return True

    def get_active_events(self) -> List[EventBonus]:
        """활성 이벤트 목록을 반환한다."""
        return [e for e in self._events.values() if e.active]

    def get_event_multiplier(self) -> float:
        """현재 적용 가능한 이벤트 배수를 반환한다 (가장 큰 값)."""
        active = self.get_active_events()
        if not active:
            return 1.0
        return max(e.multiplier for e in active)

    # ------------------------------------------------------------------
    # 특별 적립 보너스
    # ------------------------------------------------------------------

    def get_special_bonus(self, bonus_type: BonusType) -> int:
        """특별 적립 보너스 포인트를 반환한다."""
        return self._special_bonuses.get(bonus_type, 0)

    def set_special_bonus(self, bonus_type: BonusType, amount: int) -> None:
        """특별 적립 보너스 포인트를 설정한다."""
        if amount < 0:
            raise ValueError(f"보너스는 0 이상이어야 합니다: {amount}")
        self._special_bonuses[bonus_type] = amount

    # ------------------------------------------------------------------
    # 적립률 계산 (규칙 엔진)
    # ------------------------------------------------------------------

    def calculate_earn_rate(self, grade: str, apply_event: bool = True) -> float:
        """등급과 이벤트 보너스를 반영한 최종 적립률을 계산한다."""
        base = self.get_rate(grade)
        if apply_event:
            base *= self.get_event_multiplier()
        return base

    def calculate_earn_points(
        self,
        order_amount: int,
        grade: str,
        apply_event: bool = True,
    ) -> int:
        """주문 금액과 등급을 기반으로 적립 포인트를 계산한다."""
        rate = self.calculate_earn_rate(grade, apply_event=apply_event)
        return int(order_amount * rate)

    def to_dict(self) -> dict:
        """정책 전체를 딕셔너리로 반환한다."""
        return {
            "rates": self._rates,
            "events": [e.to_dict() for e in self._events.values()],
            "special_bonuses": {k.value: v for k, v in self._special_bonuses.items()},
        }
