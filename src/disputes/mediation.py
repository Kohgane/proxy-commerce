"""src/disputes/mediation.py — 자동 중재 서비스 (Phase 91).

자동 판정 규칙 엔진:
  - 소액(< 50,000원) → 자동 환불 승인
  - 배송 지연(예상 배송일 +7일 초과) → 자동 환불 승인
  - 사진 증거 존재 → 환불 승인 우선
  - 자동 판정 불가 시 관리자 대기열에 추가
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# 소액 분쟁 기준 금액 (원)
SMALL_AMOUNT_THRESHOLD = 50_000
# 배송 지연 허용 일수 (예상 배송일 초과)
SHIPPING_DELAY_DAYS = 7


class MediationResult(str, Enum):
    """중재 판정 결과."""

    FULL_REFUND = "full_refund"
    PARTIAL_REFUND = "partial_refund"
    REPLACEMENT = "replacement"
    REJECTED = "rejected"
    PENDING_REVIEW = "pending_review"


@dataclass
class MediationDecision:
    """중재 판정 결과 엔티티."""

    dispute_id: str
    result: MediationResult
    reason: str
    refund_ratio: float = 1.0
    decided_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    is_auto: bool = True

    def to_dict(self) -> dict:
        """딕셔너리로 변환한다."""
        return {
            "dispute_id": self.dispute_id,
            "result": self.result.value,
            "reason": self.reason,
            "refund_ratio": self.refund_ratio,
            "decided_at": self.decided_at,
            "is_auto": self.is_auto,
        }


class MediationService:
    """자동 판정 규칙 엔진 및 수동 중재 대기열 관리."""

    def __init__(self) -> None:
        # dispute_id → MediationDecision
        self._decisions: Dict[str, MediationDecision] = {}
        # 수동 중재 대기열
        self._pending_queue: List[str] = []

    def mediate(
        self,
        dispute_id: str,
        amount: float,
        dispute_type: str,
        shipping_delay_days: int = 0,
        has_photo_evidence: bool = False,
    ) -> MediationDecision:
        """자동 판정을 실행한다.

        Args:
            dispute_id: 분쟁 ID
            amount: 분쟁 금액 (원)
            dispute_type: 분쟁 유형
            shipping_delay_days: 예상 배송일 초과 일수
            has_photo_evidence: 사진 증거 존재 여부

        Returns:
            MediationDecision 판정 결과
        """
        result, reason, refund_ratio = self._apply_rules(
            dispute_id, amount, dispute_type, shipping_delay_days, has_photo_evidence
        )

        decision = MediationDecision(
            dispute_id=dispute_id,
            result=result,
            reason=reason,
            refund_ratio=refund_ratio,
            is_auto=(result != MediationResult.PENDING_REVIEW),
        )
        self._decisions[dispute_id] = decision

        if result == MediationResult.PENDING_REVIEW:
            if dispute_id not in self._pending_queue:
                self._pending_queue.append(dispute_id)
            logger.info("분쟁 수동 중재 대기열 추가: %s", dispute_id)
        else:
            logger.info("분쟁 자동 판정: %s → %s", dispute_id, result.value)

        return decision

    def _apply_rules(
        self,
        dispute_id: str,
        amount: float,
        dispute_type: str,
        shipping_delay_days: int,
        has_photo_evidence: bool,
    ):
        """자동 판정 규칙을 순서대로 적용한다."""
        # 규칙 1: 소액 분쟁 → 자동 환불 승인
        if amount > 0 and amount < SMALL_AMOUNT_THRESHOLD:
            return (
                MediationResult.FULL_REFUND,
                f"소액 분쟁 자동 승인 (금액: {amount:,.0f}원 < {SMALL_AMOUNT_THRESHOLD:,}원)",
                1.0,
            )

        # 규칙 2: 배송 지연 → 자동 환불 승인
        if dispute_type == "item_not_received" and shipping_delay_days > SHIPPING_DELAY_DAYS:
            return (
                MediationResult.FULL_REFUND,
                f"배송 지연 자동 승인 (지연: {shipping_delay_days}일 > {SHIPPING_DELAY_DAYS}일)",
                1.0,
            )

        # 규칙 3: 사진 증거 있으면 환불 승인 우선
        if has_photo_evidence and dispute_type in (
            "item_not_as_described",
            "quality_issue",
            "shipping_damage",
            "wrong_item",
            "counterfeit",
        ):
            return (
                MediationResult.FULL_REFUND,
                "사진 증거 기반 자동 환불 승인",
                1.0,
            )

        # 자동 판정 불가 → 관리자 대기열
        return (
            MediationResult.PENDING_REVIEW,
            "자동 판정 기준 미충족 — 관리자 수동 검토 필요",
            0.0,
        )

    def get_decision(self, dispute_id: str) -> Optional[MediationDecision]:
        """판정 결과를 조회한다."""
        return self._decisions.get(dispute_id)

    def pending_queue(self) -> List[str]:
        """수동 중재 대기열을 반환한다."""
        return list(self._pending_queue)

    def remove_from_queue(self, dispute_id: str) -> bool:
        """대기열에서 분쟁을 제거한다."""
        if dispute_id in self._pending_queue:
            self._pending_queue.remove(dispute_id)
            return True
        return False

    def resolve_manually(
        self,
        dispute_id: str,
        result: str,
        reason: str,
        refund_ratio: float = 1.0,
    ) -> MediationDecision:
        """수동으로 판정 결과를 입력한다."""
        try:
            mresult = MediationResult(result)
        except ValueError:
            raise ValueError(f"유효하지 않은 판정 결과: {result}")

        decision = MediationDecision(
            dispute_id=dispute_id,
            result=mresult,
            reason=reason,
            refund_ratio=refund_ratio,
            is_auto=False,
        )
        self._decisions[dispute_id] = decision
        self.remove_from_queue(dispute_id)
        logger.info("분쟁 수동 판정 완료: %s → %s", dispute_id, result)
        return decision
