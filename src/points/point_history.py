"""src/points/point_history.py — 포인트 이력 관리 (Phase 92).

earn/use/expire/cancel 타입의 포인트 이력을 기록하고 조회한다.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class HistoryType(str, Enum):
    """포인트 이력 타입."""

    EARN = "earn"
    USE = "use"
    EXPIRE = "expire"
    CANCEL = "cancel"


@dataclass
class PointRecord:
    """포인트 이력 레코드."""

    record_id: str
    user_id: str
    type: HistoryType
    amount: int
    balance_after: int
    reason: str
    order_id: Optional[str] = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        """딕셔너리로 변환한다."""
        return {
            "record_id": self.record_id,
            "user_id": self.user_id,
            "type": self.type.value,
            "amount": self.amount,
            "balance_after": self.balance_after,
            "reason": self.reason,
            "order_id": self.order_id,
            "created_at": self.created_at,
        }


class PointHistory:
    """포인트 이력 관리자.

    이력 기록 및 기간/타입 필터, 페이지네이션 조회를 제공한다.
    """

    def __init__(self) -> None:
        self._records: List[PointRecord] = []

    def record(
        self,
        user_id: str,
        history_type: HistoryType,
        amount: int,
        balance_after: int,
        reason: str,
        order_id: Optional[str] = None,
    ) -> PointRecord:
        """포인트 이력을 기록한다."""
        rec = PointRecord(
            record_id=str(uuid.uuid4()),
            user_id=user_id,
            type=history_type,
            amount=amount,
            balance_after=balance_after,
            reason=reason,
            order_id=order_id,
        )
        self._records.append(rec)
        logger.debug(
            "포인트 이력 기록: user=%s type=%s amount=%d",
            user_id,
            history_type.value,
            amount,
        )
        return rec

    def query(
        self,
        user_id: str,
        history_type: Optional[str] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
        page: int = 1,
        per_page: int = 20,
    ) -> Dict:
        """이력을 조회한다 (타입/기간 필터, 페이지네이션).

        Args:
            user_id: 사용자 ID
            history_type: 필터 타입 (earn/use/expire/cancel)
            since: ISO 8601 시작 날짜 (포함)
            until: ISO 8601 종료 날짜 (포함)
            page: 페이지 번호 (1부터)
            per_page: 페이지당 레코드 수

        Returns:
            {"records": [...], "total": int, "page": int, "per_page": int, "pages": int}
        """
        records = [r for r in self._records if r.user_id == user_id]

        if history_type:
            records = [r for r in records if r.type.value == history_type]

        if since:
            records = [r for r in records if r.created_at >= since]

        if until:
            records = [r for r in records if r.created_at <= until]

        total = len(records)
        pages = max(1, (total + per_page - 1) // per_page)
        start = (page - 1) * per_page
        end = start + per_page
        page_records = records[start:end]

        return {
            "records": [r.to_dict() for r in page_records],
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": pages,
        }

    def get_all_for_user(self, user_id: str) -> List[PointRecord]:
        """사용자의 전체 이력을 반환한다."""
        return [r for r in self._records if r.user_id == user_id]
