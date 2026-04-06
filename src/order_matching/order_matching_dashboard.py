"""src/order_matching/order_matching_dashboard.py — 주문 매칭 대시보드 (Phase 112).

OrderMatchingDashboard: 오늘 매칭 현황 + SLA + 리스크 분포 + 이행 불가 사유 + 소싱처 빈도
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class OrderMatchingDashboard:
    """주문 매칭 대시보드."""

    def __init__(
        self,
        matcher=None,
        fulfillment_checker=None,
        risk_assessor=None,
        sla_tracker=None,
    ) -> None:
        self._matcher = matcher
        self._fulfillment_checker = fulfillment_checker
        self._risk_assessor = risk_assessor
        self._sla_tracker = sla_tracker

    # ── 대시보드 ──────────────────────────────────────────────────────────────

    def get_dashboard_data(self) -> dict:
        """대시보드 전체 데이터."""
        return {
            'timestamp': datetime.now(tz=timezone.utc).isoformat(),
            'matching_summary': self._get_matching_summary(),
            'sla_summary': self._get_sla_summary(),
            'risk_distribution': self._get_risk_distribution(),
            'unfulfillable_reasons': self._get_unfulfillable_reasons(),
            'source_match_frequency': self._get_source_frequency(),
            'recent_match_feed': self._get_recent_feed(),
        }

    def get_daily_stats(self, date: Optional[str] = None) -> dict:
        """일별 매칭 통계."""
        target_date = date or datetime.now(tz=timezone.utc).date().isoformat()
        match_stats = {}
        if self._matcher:
            match_stats = self._matcher.get_match_stats()

        sla_perf = {}
        if self._sla_tracker:
            sla_perf = self._sla_tracker.get_sla_performance()

        return {
            'date': target_date,
            'match_stats': match_stats,
            'sla_performance': sla_perf,
        }

    def get_unfulfillable_summary(self) -> dict:
        """이행 불가 요약 (사유별 그룹핑)."""
        if not self._fulfillment_checker:
            return {'total': 0, 'by_reason': {}}

        actions = self._fulfillment_checker.get_unfulfillable_actions()
        by_reason: Dict[str, int] = {}
        for action in actions:
            reason = action.get('reason', 'unknown')
            by_reason[reason] = by_reason.get(reason, 0) + 1

        return {
            'total': len(actions),
            'by_reason': by_reason,
        }

    # ── 내부 헬퍼 ─────────────────────────────────────────────────────────────

    def _get_matching_summary(self) -> dict:
        if not self._matcher:
            return {}
        return self._matcher.get_match_stats()

    def _get_sla_summary(self) -> dict:
        if not self._sla_tracker:
            return {}
        perf = self._sla_tracker.get_sla_performance()
        overdue = self._sla_tracker.get_overdue_orders()
        return {
            'performance': perf,
            'overdue_count': len(overdue),
        }

    def _get_risk_distribution(self) -> dict:
        if not self._risk_assessor:
            return {}
        return self._risk_assessor.get_risk_summary()

    def _get_unfulfillable_reasons(self) -> dict:
        return self.get_unfulfillable_summary().get('by_reason', {})

    def _get_source_frequency(self) -> Dict[str, int]:
        """소싱처별 매칭 빈도."""
        if not self._matcher:
            return {}
        history = self._matcher.get_match_history(limit=200)
        freq: Dict[str, int] = {}
        for result in history:
            if result.best_source:
                freq[result.best_source] = freq.get(result.best_source, 0) + 1
        return freq

    def _get_recent_feed(self) -> List[dict]:
        """최근 매칭 피드."""
        if not self._matcher:
            return []
        history = self._matcher.get_match_history(limit=20)
        feed = []
        for r in history:
            feed.append({
                'match_id': r.match_id,
                'order_id': r.order_id,
                'product_id': r.product_id,
                'best_source': r.best_source,
                'status': r.fulfillment_status.value,
                'risk_score': r.risk_score,
                'matched_at': r.matched_at,
            })
        return feed
