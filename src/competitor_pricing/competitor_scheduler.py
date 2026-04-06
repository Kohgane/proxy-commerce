"""src/competitor_pricing/competitor_scheduler.py — 경쟁사 가격 체크 스케줄러 (Phase 111)."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from .tracker import CompetitorProduct

logger = logging.getLogger(__name__)

# 체크 주기 (분)
INTERVAL_POPULAR = 60
INTERVAL_NORMAL = 240
INTERVAL_INACTIVE = 1440
INTERVAL_PRICE_WAR = 15


@dataclass
class ScheduleEntry:
    competitor_id: str
    interval_minutes: int
    priority: int
    next_check_at: str
    last_checked_at: Optional[str]
    is_price_war: bool = False


class CompetitorCheckScheduler:
    """경쟁사 가격 체크 스케줄 관리."""

    def __init__(self) -> None:
        self._schedules: Dict[str, ScheduleEntry] = {}

    # ── 등록 / 해제 ───────────────────────────────────────────────────────────

    def register(
        self, competitor: CompetitorProduct, priority: int = 5
    ) -> ScheduleEntry:
        """경쟁사 체크 스케줄 등록."""
        interval = self._pick_interval(priority)
        next_check = self._calc_next_check(interval)
        entry = ScheduleEntry(
            competitor_id=competitor.competitor_id,
            interval_minutes=interval,
            priority=priority,
            next_check_at=next_check,
            last_checked_at=competitor.last_checked_at,
        )
        self._schedules[competitor.competitor_id] = entry
        logger.info(
            "스케줄 등록: %s (주기 %d분)", competitor.competitor_id, interval
        )
        return entry

    def unregister(self, competitor_id: str) -> bool:
        """스케줄 해제."""
        if competitor_id not in self._schedules:
            return False
        del self._schedules[competitor_id]
        return True

    # ── 스케줄 조회 ───────────────────────────────────────────────────────────

    def get_next_checks(self, limit: int = 10) -> List[ScheduleEntry]:
        """다음 체크 예정 순으로 정렬된 스케줄 목록."""
        entries = sorted(
            self._schedules.values(),
            key=lambda e: e.next_check_at,
        )
        return entries[:limit]

    def get_stats(self) -> dict:
        """스케줄 통계."""
        total = len(self._schedules)
        price_war = sum(1 for e in self._schedules.values() if e.is_price_war)
        now = datetime.now(tz=timezone.utc).isoformat()
        overdue = sum(
            1 for e in self._schedules.values() if e.next_check_at <= now
        )
        return {
            'total': total,
            'price_war': price_war,
            'overdue': overdue,
            'interval_distribution': self._interval_dist(),
        }

    # ── 업데이트 ─────────────────────────────────────────────────────────────

    def update_schedule(self, competitor_id: str, interval_minutes: int) -> bool:
        """체크 주기 변경."""
        entry = self._schedules.get(competitor_id)
        if not entry:
            return False
        entry.interval_minutes = interval_minutes
        entry.next_check_at = self._calc_next_check(interval_minutes)
        return True

    def mark_checked(self, competitor_id: str, success: bool = True) -> None:
        """체크 완료 표시 및 다음 체크 시간 계산."""
        entry = self._schedules.get(competitor_id)
        if not entry:
            return
        now = datetime.now(tz=timezone.utc)
        entry.last_checked_at = now.isoformat()
        interval = entry.interval_minutes if success else min(
            entry.interval_minutes * 2, INTERVAL_INACTIVE
        )
        entry.next_check_at = (now + timedelta(minutes=interval)).isoformat()

    # ── 내부 헬퍼 ────────────────────────────────────────────────────────────

    @staticmethod
    def _pick_interval(priority: int) -> int:
        if priority >= 9:
            return INTERVAL_POPULAR
        if priority >= 5:
            return INTERVAL_NORMAL
        return INTERVAL_INACTIVE

    @staticmethod
    def _calc_next_check(interval_minutes: int) -> str:
        return (
            datetime.now(tz=timezone.utc) + timedelta(minutes=interval_minutes)
        ).isoformat()

    def _interval_dist(self) -> Dict[str, int]:
        dist: Dict[str, int] = {'popular': 0, 'normal': 0, 'inactive': 0, 'price_war': 0}
        for e in self._schedules.values():
            if e.is_price_war:
                dist['price_war'] += 1
            elif e.interval_minutes <= INTERVAL_POPULAR:
                dist['popular'] += 1
            elif e.interval_minutes <= INTERVAL_NORMAL:
                dist['normal'] += 1
            else:
                dist['inactive'] += 1
        return dist
