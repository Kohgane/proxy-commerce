"""src/disputes/dispute_manager.py — 분쟁 관리자 (Phase 91).

분쟁 CRUD 및 상태 전환을 관리한다.

상태 전환:
    opened → under_review → mediation → resolved / rejected
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class DisputeStatus(str, Enum):
    """분쟁 상태."""

    OPENED = "opened"
    UNDER_REVIEW = "under_review"
    MEDIATION = "mediation"
    RESOLVED = "resolved"
    REJECTED = "rejected"


class DisputeType(str, Enum):
    """분쟁 유형."""

    ITEM_NOT_RECEIVED = "item_not_received"
    ITEM_NOT_AS_DESCRIBED = "item_not_as_described"
    QUALITY_ISSUE = "quality_issue"
    SHIPPING_DAMAGE = "shipping_damage"
    WRONG_ITEM = "wrong_item"
    COUNTERFEIT = "counterfeit"


# 허용된 상태 전환 맵
_VALID_TRANSITIONS: Dict[DisputeStatus, List[DisputeStatus]] = {
    DisputeStatus.OPENED: [DisputeStatus.UNDER_REVIEW, DisputeStatus.REJECTED],
    DisputeStatus.UNDER_REVIEW: [DisputeStatus.MEDIATION, DisputeStatus.RESOLVED, DisputeStatus.REJECTED],
    DisputeStatus.MEDIATION: [DisputeStatus.RESOLVED, DisputeStatus.REJECTED],
    DisputeStatus.RESOLVED: [],
    DisputeStatus.REJECTED: [],
}


@dataclass
class Dispute:
    """분쟁 엔티티."""

    dispute_id: str
    order_id: str
    customer_id: str
    reason: str
    dispute_type: DisputeType
    status: DisputeStatus = DisputeStatus.OPENED
    evidence_ids: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    resolved_at: Optional[str] = None
    amount: float = 0.0
    notes: str = ""

    def to_dict(self) -> dict:
        """딕셔너리로 변환한다."""
        return {
            "dispute_id": self.dispute_id,
            "order_id": self.order_id,
            "customer_id": self.customer_id,
            "reason": self.reason,
            "dispute_type": self.dispute_type.value,
            "status": self.status.value,
            "evidence_ids": self.evidence_ids,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "resolved_at": self.resolved_at,
            "amount": self.amount,
            "notes": self.notes,
        }


class DisputeManager:
    """분쟁 CRUD 및 상태 전환 관리자."""

    def __init__(self) -> None:
        self._disputes: Dict[str, Dispute] = {}

    def create(
        self,
        order_id: str,
        customer_id: str,
        reason: str,
        dispute_type: str,
        amount: float = 0.0,
        notes: str = "",
    ) -> Dispute:
        """분쟁을 생성한다.

        Args:
            order_id: 주문 ID
            customer_id: 고객 ID
            reason: 분쟁 사유
            dispute_type: 분쟁 유형 (DisputeType 문자열)
            amount: 분쟁 금액
            notes: 추가 메모

        Returns:
            생성된 Dispute 객체
        """
        try:
            dtype = DisputeType(dispute_type)
        except ValueError:
            raise ValueError(f"유효하지 않은 분쟁 유형: {dispute_type}")

        dispute = Dispute(
            dispute_id=str(uuid.uuid4()),
            order_id=order_id,
            customer_id=customer_id,
            reason=reason,
            dispute_type=dtype,
            amount=amount,
            notes=notes,
        )
        self._disputes[dispute.dispute_id] = dispute
        logger.info("분쟁 생성: %s (order=%s)", dispute.dispute_id, order_id)
        return dispute

    def get(self, dispute_id: str) -> Optional[Dispute]:
        """분쟁 상세 조회."""
        return self._disputes.get(dispute_id)

    def list(
        self,
        status: Optional[str] = None,
        dispute_type: Optional[str] = None,
        customer_id: Optional[str] = None,
    ) -> List[Dispute]:
        """분쟁 목록을 조회한다.

        Args:
            status: 상태 필터 (선택)
            dispute_type: 유형 필터 (선택)
            customer_id: 고객 ID 필터 (선택)

        Returns:
            Dispute 목록
        """
        items = list(self._disputes.values())
        if status:
            items = [d for d in items if d.status.value == status]
        if dispute_type:
            items = [d for d in items if d.dispute_type.value == dispute_type]
        if customer_id:
            items = [d for d in items if d.customer_id == customer_id]
        return items

    def transition(self, dispute_id: str, new_status: str, notes: str = "") -> Dispute:
        """분쟁 상태를 전환한다.

        Args:
            dispute_id: 분쟁 ID
            new_status: 전환할 상태
            notes: 전환 메모

        Returns:
            업데이트된 Dispute 객체

        Raises:
            KeyError: 분쟁을 찾을 수 없는 경우
            ValueError: 허용되지 않은 상태 전환인 경우
        """
        dispute = self._disputes.get(dispute_id)
        if not dispute:
            raise KeyError(f"분쟁을 찾을 수 없습니다: {dispute_id}")

        try:
            target = DisputeStatus(new_status)
        except ValueError:
            raise ValueError(f"유효하지 않은 상태: {new_status}")

        allowed = _VALID_TRANSITIONS.get(dispute.status, [])
        if target not in allowed:
            raise ValueError(
                f"허용되지 않은 상태 전환: {dispute.status.value} → {new_status}"
            )

        dispute.status = target
        dispute.updated_at = datetime.now(timezone.utc).isoformat()
        if notes:
            dispute.notes = notes
        if target in (DisputeStatus.RESOLVED, DisputeStatus.REJECTED):
            dispute.resolved_at = dispute.updated_at

        logger.info("분쟁 상태 전환: %s → %s", dispute_id, new_status)
        return dispute

    def add_evidence(self, dispute_id: str, evidence_id: str) -> None:
        """분쟁에 증거 ID를 추가한다."""
        dispute = self._disputes.get(dispute_id)
        if not dispute:
            raise KeyError(f"분쟁을 찾을 수 없습니다: {dispute_id}")
        if evidence_id not in dispute.evidence_ids:
            dispute.evidence_ids.append(evidence_id)
            dispute.updated_at = datetime.now(timezone.utc).isoformat()

    def stats(self) -> dict:
        """분쟁 현황 통계를 반환한다."""
        disputes = list(self._disputes.values())
        by_status: Dict[str, int] = {}
        by_type: Dict[str, int] = {}
        for d in disputes:
            by_status[d.status.value] = by_status.get(d.status.value, 0) + 1
            by_type[d.dispute_type.value] = by_type.get(d.dispute_type.value, 0) + 1
        return {
            "total": len(disputes),
            "by_status": by_status,
            "by_type": by_type,
        }
