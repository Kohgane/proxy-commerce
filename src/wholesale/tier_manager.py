"""src/wholesale/tier_manager.py — 도매 등급/할인 룰 관리 (Phase 148).

등급별 가격:
  - 일반 (retail):   기준가 × 1.0
  - 도매 (wholesale): 기준가 × 0.9 (10~49개) / 0.8 (50+개)
  - VIP:             별도 계약가

최소 주문 수량(MOQ):
  - 도매: 10개
  - VIP: 1개 (별도 협의)
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import List

logger = logging.getLogger(__name__)


class PriceLevel(str, Enum):
    RETAIL = "retail"
    WHOLESALE = "wholesale"
    VIP = "vip"


@dataclass
class QuantityBracket:
    """수량 구간별 할인율."""
    min_qty: int
    max_qty: int | None  # None = 무제한
    multiplier: float

    def applies(self, qty: int) -> bool:
        if qty < self.min_qty:
            return False
        if self.max_qty is not None and qty > self.max_qty:
            return False
        return True


@dataclass
class WholesaleTier:
    """도매 등급 정의."""
    level: PriceLevel
    label: str
    moq: int  # 최소 주문 수량
    brackets: List[QuantityBracket] = field(default_factory=list)
    description: str = ""

    def price_multiplier(self, qty: int) -> float:
        """수량에 따른 가격 배수 반환."""
        for bracket in self.brackets:
            if bracket.applies(qty):
                return bracket.multiplier
        # 기본값 (어떤 bracket도 해당 없으면 첫 bracket 또는 1.0)
        return self.brackets[0].multiplier if self.brackets else 1.0


_DEFAULT_TIERS: List[WholesaleTier] = [
    WholesaleTier(
        level=PriceLevel.RETAIL,
        label="일반",
        moq=1,
        brackets=[QuantityBracket(1, None, 1.0)],
        description="일반 소비자 가격",
    ),
    WholesaleTier(
        level=PriceLevel.WHOLESALE,
        label="도매",
        moq=10,
        brackets=[
            QuantityBracket(10, 49, 0.9),
            QuantityBracket(50, None, 0.8),
        ],
        description="사업자 도매가 (10개 이상 주문 시)",
    ),
    WholesaleTier(
        level=PriceLevel.VIP,
        label="VIP",
        moq=1,
        brackets=[QuantityBracket(1, None, 0.75)],
        description="VIP 계약가 (별도 협의)",
    ),
]


class WholesaleTierManager:
    """도매 등급/할인 룰 관리자."""

    def __init__(self) -> None:
        self._tiers: List[WholesaleTier] = list(_DEFAULT_TIERS)

    @property
    def enabled(self) -> bool:
        return os.getenv("WHOLESALE_ENABLED", "1") == "1"

    def list_tiers(self) -> List[WholesaleTier]:
        return list(self._tiers)

    def get_tier(self, level: PriceLevel | str) -> WholesaleTier | None:
        level_val = level.value if isinstance(level, PriceLevel) else level
        for t in self._tiers:
            if t.level.value == level_val:
                return t
        return None

    def calculate_price(
        self, base_price: float, level: PriceLevel | str, qty: int
    ) -> float:
        """기준가 × 수량에 따른 실제 판매가 계산.

        Args:
            base_price: 기준(소비자) 가격
            level: 등급
            qty: 주문 수량

        Returns:
            계산된 가격 (원 단위 반올림)
        """
        tier = self.get_tier(level)
        if tier is None:
            return base_price
        if qty < tier.moq:
            raise ValueError(f"최소 주문 수량(MOQ)은 {tier.moq}개 이상이어야 합니다.")
        multiplier = tier.price_multiplier(qty)
        return int(base_price * multiplier)

    def moq_ok(self, level: PriceLevel | str, qty: int) -> bool:
        """MOQ 충족 여부."""
        tier = self.get_tier(level)
        if tier is None:
            return True
        return qty >= tier.moq

    def summary(self) -> dict:
        return {
            "enabled": self.enabled,
            "tier_count": len(self._tiers),
            "tiers": [
                {
                    "level": t.level.value,
                    "label": t.label,
                    "moq": t.moq,
                    "description": t.description,
                }
                for t in self._tiers
            ],
        }
