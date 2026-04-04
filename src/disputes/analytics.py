"""src/disputes/analytics.py — 분쟁 분석 통계 (Phase 91).

분석 항목:
  - 분쟁률 계산 (분쟁 수 / 전체 주문 수)
  - 평균 해결 시간
  - 카테고리별/타입별 분석
  - 판매자별 분쟁 통계
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, List, Optional

from .dispute_manager import Dispute, DisputeStatus

logger = logging.getLogger(__name__)


def _parse_iso(ts: str) -> Optional[datetime]:
    """ISO 8601 문자열을 datetime으로 변환한다."""
    try:
        return datetime.fromisoformat(ts)
    except Exception:
        return None


class DisputeAnalytics:
    """분쟁 분석 통계 서비스."""

    def dispute_rate(self, dispute_count: int, total_orders: int) -> float:
        """분쟁률을 계산한다.

        Args:
            dispute_count: 분쟁 건수
            total_orders: 전체 주문 수

        Returns:
            분쟁률 (0.0 ~ 1.0)
        """
        if total_orders <= 0:
            return 0.0
        return round(dispute_count / total_orders, 4)

    def average_resolution_time(self, disputes: List[Dispute]) -> float:
        """평균 해결 시간을 계산한다 (시간 단위).

        Args:
            disputes: Dispute 목록

        Returns:
            평균 해결 시간 (시간)
        """
        resolved = [
            d for d in disputes
            if d.status in (DisputeStatus.RESOLVED, DisputeStatus.REJECTED)
            and d.resolved_at
        ]
        if not resolved:
            return 0.0

        durations = []
        for d in resolved:
            created = _parse_iso(d.created_at)
            resolved_at = _parse_iso(d.resolved_at)
            if created and resolved_at:
                delta = resolved_at - created
                durations.append(delta.total_seconds() / 3600)

        if not durations:
            return 0.0
        return round(sum(durations) / len(durations), 2)

    def by_type(self, disputes: List[Dispute]) -> Dict[str, int]:
        """유형별 분쟁 건수를 반환한다."""
        result: Dict[str, int] = {}
        for d in disputes:
            key = d.dispute_type.value
            result[key] = result.get(key, 0) + 1
        return result

    def by_status(self, disputes: List[Dispute]) -> Dict[str, int]:
        """상태별 분쟁 건수를 반환한다."""
        result: Dict[str, int] = {}
        for d in disputes:
            key = d.status.value
            result[key] = result.get(key, 0) + 1
        return result

    def by_seller(self, disputes: List[Dispute], order_seller_map: Dict[str, str]) -> Dict[str, dict]:
        """판매자별 분쟁 통계를 반환한다.

        Args:
            disputes: Dispute 목록
            order_seller_map: {order_id: seller_id} 맵핑

        Returns:
            {seller_id: {"count": int, "types": {...}}} 딕셔너리
        """
        result: Dict[str, dict] = {}
        for d in disputes:
            seller_id = order_seller_map.get(d.order_id, "unknown")
            stats = result.setdefault(seller_id, {"count": 0, "types": {}})
            stats["count"] += 1
            key = d.dispute_type.value
            stats["types"][key] = stats["types"].get(key, 0) + 1
        return result

    def summary(self, disputes: List[Dispute], total_orders: int) -> dict:
        """분쟁 분석 요약을 반환한다.

        Args:
            disputes: Dispute 목록
            total_orders: 전체 주문 수

        Returns:
            요약 통계 딕셔너리
        """
        return {
            "total_disputes": len(disputes),
            "total_orders": total_orders,
            "dispute_rate": self.dispute_rate(len(disputes), total_orders),
            "average_resolution_hours": self.average_resolution_time(disputes),
            "by_type": self.by_type(disputes),
            "by_status": self.by_status(disputes),
        }
