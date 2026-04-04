"""src/disputes/refund_decision.py — 환불 판정 및 판매자 패널티 (Phase 91).

환불 판정:
  - 전액 환불 (full_refund)
  - 부분 환불 (partial_refund): 사용 기간, 손상 정도 기반 비율 계산
  - 거절 (rejected)

판매자 패널티:
  - 분쟁률 > 5%  → 경고
  - 분쟁률 > 10% → 판매 제한
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# 판매자 패널티 임계값
PENALTY_WARNING_THRESHOLD = 0.05   # 5%
PENALTY_RESTRICT_THRESHOLD = 0.10  # 10%


class RefundType(str, Enum):
    """환불 유형."""

    FULL = "full_refund"
    PARTIAL = "partial_refund"
    REJECTED = "rejected"


class SellerPenalty(str, Enum):
    """판매자 패널티 등급."""

    NONE = "none"
    WARNING = "warning"
    RESTRICTED = "restricted"


@dataclass
class RefundResult:
    """환불 판정 결과."""

    dispute_id: str
    refund_type: RefundType
    original_amount: float
    refund_amount: float
    refund_ratio: float
    reason: str

    def to_dict(self) -> dict:
        """딕셔너리로 변환한다."""
        return {
            "dispute_id": self.dispute_id,
            "refund_type": self.refund_type.value,
            "original_amount": self.original_amount,
            "refund_amount": self.refund_amount,
            "refund_ratio": self.refund_ratio,
            "reason": self.reason,
        }


class RefundDecision:
    """환불 판정 및 판매자 패널티 관리."""

    def __init__(self) -> None:
        # seller_id → {"disputes": int, "total_orders": int, "penalty": SellerPenalty}
        self._seller_stats: Dict[str, Dict] = {}

    def decide(
        self,
        dispute_id: str,
        original_amount: float,
        refund_type: str,
        usage_days: int = 0,
        damage_level: float = 0.0,
        reason: str = "",
    ) -> RefundResult:
        """환불 판정을 내린다.

        Args:
            dispute_id: 분쟁 ID
            original_amount: 원래 결제 금액
            refund_type: 환불 유형 (RefundType 문자열)
            usage_days: 사용 기간 (일)
            damage_level: 손상 정도 (0.0 ~ 1.0, 1.0이 완전 손상)
            reason: 판정 사유

        Returns:
            RefundResult 판정 결과
        """
        try:
            rtype = RefundType(refund_type)
        except ValueError:
            raise ValueError(f"유효하지 않은 환불 유형: {refund_type}")

        if rtype == RefundType.FULL:
            ratio = 1.0
            refund_amount = original_amount
        elif rtype == RefundType.PARTIAL:
            ratio = self._calculate_partial_ratio(usage_days, damage_level)
            refund_amount = round(original_amount * ratio, 0)
        else:
            ratio = 0.0
            refund_amount = 0.0

        return RefundResult(
            dispute_id=dispute_id,
            refund_type=rtype,
            original_amount=original_amount,
            refund_amount=refund_amount,
            refund_ratio=ratio,
            reason=reason or rtype.value,
        )

    def _calculate_partial_ratio(self, usage_days: int, damage_level: float) -> float:
        """부분 환불 비율을 계산한다.

        사용 기간 패널티:
          - 0~7일:   최대 비율
          - 8~30일:  10% 차감
          - 31~90일: 30% 차감
          - 91일+:   50% 차감

        손상 정도 패널티:
          - 손상 정도만큼 추가 차감 (최소 0%)
        """
        # 사용 기간 패널티
        if usage_days <= 7:
            base_ratio = 1.0
        elif usage_days <= 30:
            base_ratio = 0.9
        elif usage_days <= 90:
            base_ratio = 0.7
        else:
            base_ratio = 0.5

        # 손상 정도 차감
        damage = max(0.0, min(1.0, damage_level))
        ratio = base_ratio * (1.0 - damage)
        return max(0.0, round(ratio, 2))

    def record_seller_dispute(self, seller_id: str, total_orders: int) -> SellerPenalty:
        """판매자 분쟁 기록을 업데이트하고 패널티를 반환한다.

        Args:
            seller_id: 판매자 ID
            total_orders: 판매자 총 주문 수

        Returns:
            현재 패널티 등급
        """
        stats = self._seller_stats.setdefault(seller_id, {"disputes": 0, "penalty": SellerPenalty.NONE})
        stats["disputes"] = stats.get("disputes", 0) + 1
        stats["total_orders"] = total_orders

        penalty = self._evaluate_penalty(stats["disputes"], total_orders)
        stats["penalty"] = penalty
        logger.info(
            "판매자 패널티 평가: seller=%s disputes=%d orders=%d → %s",
            seller_id,
            stats["disputes"],
            total_orders,
            penalty.value,
        )
        return penalty

    def _evaluate_penalty(self, dispute_count: int, total_orders: int) -> SellerPenalty:
        """분쟁률을 기반으로 패널티를 결정한다."""
        if total_orders <= 0:
            return SellerPenalty.NONE
        rate = dispute_count / total_orders
        if rate > PENALTY_RESTRICT_THRESHOLD:
            return SellerPenalty.RESTRICTED
        if rate > PENALTY_WARNING_THRESHOLD:
            return SellerPenalty.WARNING
        return SellerPenalty.NONE

    def get_seller_penalty(self, seller_id: str) -> Optional[SellerPenalty]:
        """판매자 패널티를 조회한다."""
        stats = self._seller_stats.get(seller_id)
        if stats is None:
            return None
        return stats.get("penalty", SellerPenalty.NONE)

    def get_seller_stats(self, seller_id: str) -> Optional[dict]:
        """판매자 분쟁 통계를 조회한다."""
        stats = self._seller_stats.get(seller_id)
        if stats is None:
            return None
        total = stats.get("total_orders", 0)
        disputes = stats.get("disputes", 0)
        rate = disputes / total if total > 0 else 0.0
        return {
            "seller_id": seller_id,
            "dispute_count": disputes,
            "total_orders": total,
            "dispute_rate": round(rate, 4),
            "penalty": stats.get("penalty", SellerPenalty.NONE).value,
        }
