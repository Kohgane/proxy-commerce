"""src/source_monitor/scheduler.py — 모니터링 스케줄러 (Phase 108).

SourceMonitorScheduler: 상품별 체크 주기 설정 및 우선순위 기반 체크 순서 관리
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .engine import SourceProduct, SourceStatus

logger = logging.getLogger(__name__)

# 상품 유형별 기본 체크 주기 (분)
INTERVAL_POPULAR = 30
INTERVAL_NORMAL = 120
INTERVAL_INACTIVE = 1440  # 24시간


class ScheduleEntry:
    def __init__(self, source_product_id: str, interval_minutes: int, priority: int = 5):
        self.source_product_id = source_product_id
        self.interval_minutes = interval_minutes
        self.priority = priority  # 1=highest, 10=lowest
        self.next_check_at: Optional[str] = None
        self.last_check_at: Optional[str] = None
        self.failure_count: int = 0

    def to_dict(self) -> dict:
        return {
            'source_product_id': self.source_product_id,
            'interval_minutes': self.interval_minutes,
            'priority': self.priority,
            'next_check_at': self.next_check_at,
            'last_check_at': self.last_check_at,
            'failure_count': self.failure_count,
        }


class SourceMonitorScheduler:
    """소싱처 모니터링 스케줄러."""

    def __init__(self):
        self._schedule: Dict[str, ScheduleEntry] = {}

    def register(self, product: SourceProduct, priority: int = 5) -> ScheduleEntry:
        """상품 스케줄 등록."""
        interval = self._determine_interval(product, priority)
        entry = ScheduleEntry(
            source_product_id=product.source_product_id,
            interval_minutes=interval,
            priority=priority,
        )
        entry.next_check_at = datetime.now(tz=timezone.utc).isoformat()
        self._schedule[product.source_product_id] = entry
        logger.info(
            "스케줄 등록: %s (주기: %d분, 우선순위: %d)",
            product.source_product_id,
            interval,
            priority,
        )
        return entry

    def unregister(self, source_product_id: str) -> bool:
        if source_product_id in self._schedule:
            del self._schedule[source_product_id]
            return True
        return False

    def get_due_products(self) -> List[ScheduleEntry]:
        """체크 시간이 된 상품 목록 (우선순위순)."""
        now = datetime.now(tz=timezone.utc).isoformat()
        due = [
            e for e in self._schedule.values()
            if e.next_check_at is not None and e.next_check_at <= now
        ]
        due.sort(key=lambda e: (e.priority, e.next_check_at or ''))
        return due

    def mark_checked(self, source_product_id: str, success: bool = True) -> None:
        """체크 완료 마킹."""
        entry = self._schedule.get(source_product_id)
        if not entry:
            return
        entry.last_check_at = datetime.now(tz=timezone.utc).isoformat()
        if success:
            entry.failure_count = 0
        else:
            entry.failure_count += 1
            # 연속 실패 시 체크 주기 단축
            if entry.failure_count >= 3:
                entry.interval_minutes = max(10, entry.interval_minutes // 2)
                logger.warning(
                    "연속 실패 %d회: %s — 체크 주기 단축 → %d분",
                    entry.failure_count,
                    source_product_id,
                    entry.interval_minutes,
                )
        self._advance_next_check(entry)

    def _advance_next_check(self, entry: ScheduleEntry) -> None:
        from datetime import timedelta
        now = datetime.now(tz=timezone.utc)
        entry.next_check_at = (now + timedelta(minutes=entry.interval_minutes)).isoformat()

    def _determine_interval(self, product: SourceProduct, priority: int) -> int:
        if not product.is_alive or product.status == SourceStatus.listing_removed:
            return INTERVAL_INACTIVE
        if priority <= 2:
            return INTERVAL_POPULAR
        return INTERVAL_NORMAL

    def update_interval(self, source_product_id: str, interval_minutes: int) -> bool:
        entry = self._schedule.get(source_product_id)
        if entry:
            entry.interval_minutes = interval_minutes
            return True
        return False

    def get_stats(self) -> dict:
        total = len(self._schedule)
        popular = sum(1 for e in self._schedule.values() if e.interval_minutes <= INTERVAL_POPULAR)
        normal = sum(1 for e in self._schedule.values() if INTERVAL_POPULAR < e.interval_minutes <= INTERVAL_NORMAL)
        inactive = sum(1 for e in self._schedule.values() if e.interval_minutes > INTERVAL_NORMAL)
        return {
            'total_scheduled': total,
            'popular': popular,
            'normal': normal,
            'inactive': inactive,
        }

    def list_schedule(self) -> List[ScheduleEntry]:
        return sorted(self._schedule.values(), key=lambda e: e.priority)
