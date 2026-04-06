"""src/source_monitor/dashboard.py — 모니터링 대시보드 (Phase 108).

SourceMonitorDashboard: 전체 소싱 상품 현황 + 실시간 변동 피드 + 마켓플레이스별 분포
"""
from __future__ import annotations

import logging
from typing import Dict, List

from .engine import SourceMonitorEngine, SourceStatus
from .change_detector import ChangeDetector, Severity
from .auto_deactivation import AutoDeactivationService
from .scheduler import SourceMonitorScheduler

logger = logging.getLogger(__name__)


class SourceMonitorDashboard:
    """소싱처 모니터링 대시보드."""

    def __init__(
        self,
        engine: SourceMonitorEngine,
        detector: ChangeDetector,
        deactivation_svc: AutoDeactivationService,
        scheduler: SourceMonitorScheduler,
    ):
        self._engine = engine
        self._detector = detector
        self._deactivation_svc = deactivation_svc
        self._scheduler = scheduler

    def get_dashboard(self) -> dict:
        """전체 대시보드 데이터."""
        summary = self._engine.get_summary()
        products = self._engine.list_products()
        events = self._detector.get_events()
        critical_events = self._detector.get_critical_events()
        deactivated = self._deactivation_svc.list_deactivated()
        sched_stats = self._scheduler.get_stats()
        event_stats = self._detector.get_stats()

        # 최근 변동 피드 (최대 20개)
        recent_events = sorted(events, key=lambda e: e.detected_at, reverse=True)[:20]

        # 마켓플레이스별 상태 분포
        marketplace_dist = summary.get('by_source_type', {})

        # 가격 변동 상품 목록
        price_changed = [
            p.to_dict() for p in products
            if p.status == SourceStatus.price_changed
        ]

        # 체크 성공률 계산
        total_products = len(products)
        failed_products = sum(1 for p in products if p.consecutive_failures > 0)
        check_success_rate = (
            round((total_products - failed_products) / total_products * 100, 1)
            if total_products > 0 else 100.0
        )

        return {
            'summary': summary,
            'recent_events': [e.to_dict() for e in recent_events],
            'critical_events_count': len(critical_events),
            'deactivated_count': len(deactivated),
            'marketplace_distribution': marketplace_dist,
            'price_changed_products': price_changed,
            'check_success_rate': check_success_rate,
            'event_stats': event_stats,
            'schedule_stats': sched_stats,
            'auto_processed': len([r for r in self._deactivation_svc.get_history() if r.is_active]),
            'manual_required': len(critical_events),
        }

    def get_price_trend(self, source_product_id: str) -> dict:
        """특정 상품 가격 변동 이력."""
        events = self._detector.get_events(source_product_id=source_product_id)
        price_events = [
            e for e in events
            if e.change_type.value in ('price_increase', 'price_decrease')
        ]
        return {
            'source_product_id': source_product_id,
            'price_events': [e.to_dict() for e in price_events],
            'total_changes': len(price_events),
        }

    def get_status_overview(self) -> dict:
        """간략한 상태 개요."""
        products = self._engine.list_products()
        total = len(products)
        by_status: Dict[str, int] = {}
        for p in products:
            sv = p.status.value if hasattr(p.status, 'value') else str(p.status)
            by_status[sv] = by_status.get(sv, 0) + 1
        return {
            'total': total,
            'by_status': by_status,
            'alive': sum(1 for p in products if p.is_alive),
            'dead': sum(1 for p in products if not p.is_alive),
        }
