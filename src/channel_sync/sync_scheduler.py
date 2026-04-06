"""src/channel_sync/sync_scheduler.py — 채널 동기화 스케줄러 (Phase 109).

ChannelSyncScheduler: 전체/빠른/이벤트 동기화 스케줄 관리
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# 기본 동기화 주기
FULL_SYNC_INTERVAL_HOURS = 6
QUICK_SYNC_INTERVAL_MINUTES = 30


class SyncPriority:
    EVENT = 1       # 이벤트 기반 즉시 동기화 (최고 우선순위)
    QUICK = 2       # 빠른 동기화 (가격/재고)
    FULL = 3        # 전체 동기화 (낮은 우선순위)


@dataclass
class ScheduledSyncJob:
    job_id: str
    product_id: str
    channels: List[str]
    priority: int
    scheduled_at: str
    reason: str = ''
    completed: bool = False
    completed_at: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            'job_id': self.job_id,
            'product_id': self.product_id,
            'channels': self.channels,
            'priority': self.priority,
            'scheduled_at': self.scheduled_at,
            'reason': self.reason,
            'completed': self.completed,
            'completed_at': self.completed_at,
        }


class ChannelSyncScheduler:
    """채널 동기화 스케줄러."""

    def __init__(
        self,
        full_sync_interval_hours: int = FULL_SYNC_INTERVAL_HOURS,
        quick_sync_interval_minutes: int = QUICK_SYNC_INTERVAL_MINUTES,
    ):
        self.full_sync_interval_hours = full_sync_interval_hours
        self.quick_sync_interval_minutes = quick_sync_interval_minutes
        self._jobs: Dict[str, ScheduledSyncJob] = {}
        self._last_full_sync: Optional[str] = None
        self._last_quick_sync: Optional[str] = None

    # ── 스케줄 추가 ──────────────────────────────────────────────────────────

    def schedule_event_sync(
        self,
        product_id: str,
        channels: List[str],
        reason: str = '',
    ) -> ScheduledSyncJob:
        """이벤트 기반 즉시 동기화 스케줄 추가."""
        import uuid
        job_id = str(uuid.uuid4())
        job = ScheduledSyncJob(
            job_id=job_id,
            product_id=product_id,
            channels=channels,
            priority=SyncPriority.EVENT,
            scheduled_at=datetime.now(tz=timezone.utc).isoformat(),
            reason=reason or '이벤트 기반 동기화',
        )
        self._jobs[job_id] = job
        logger.info("이벤트 동기화 스케줄: %s (%s)", product_id, reason)
        return job

    def schedule_quick_sync(self, product_ids: Optional[List[str]] = None) -> List[ScheduledSyncJob]:
        """빠른 동기화 스케줄 추가 (가격/재고)."""
        import uuid
        jobs = []
        ids = product_ids or ['__all__']
        for pid in ids:
            job_id = str(uuid.uuid4())
            job = ScheduledSyncJob(
                job_id=job_id,
                product_id=pid,
                channels=['coupang', 'naver', 'internal'],
                priority=SyncPriority.QUICK,
                scheduled_at=datetime.now(tz=timezone.utc).isoformat(),
                reason='빠른 동기화 (가격/재고)',
            )
            self._jobs[job_id] = job
            jobs.append(job)
        self._last_quick_sync = datetime.now(tz=timezone.utc).isoformat()
        return jobs

    def schedule_full_sync(self, channel: Optional[str] = None) -> ScheduledSyncJob:
        """전체 동기화 스케줄 추가."""
        import uuid
        job_id = str(uuid.uuid4())
        channels = [channel] if channel else ['coupang', 'naver', 'internal']
        job = ScheduledSyncJob(
            job_id=job_id,
            product_id='__all__',
            channels=channels,
            priority=SyncPriority.FULL,
            scheduled_at=datetime.now(tz=timezone.utc).isoformat(),
            reason='전체 동기화',
        )
        self._jobs[job_id] = job
        self._last_full_sync = datetime.now(tz=timezone.utc).isoformat()
        return job

    # ── 스케줄 관리 ──────────────────────────────────────────────────────────

    def get_pending_jobs(self) -> List[ScheduledSyncJob]:
        """우선순위 순 대기 중인 작업 목록."""
        pending = [j for j in self._jobs.values() if not j.completed]
        return sorted(pending, key=lambda j: j.priority)

    def mark_completed(self, job_id: str) -> Optional[ScheduledSyncJob]:
        """작업 완료 처리."""
        job = self._jobs.get(job_id)
        if job:
            job.completed = True
            job.completed_at = datetime.now(tz=timezone.utc).isoformat()
        return job

    def get_job(self, job_id: str) -> Optional[ScheduledSyncJob]:
        return self._jobs.get(job_id)

    def is_full_sync_due(self) -> bool:
        """전체 동기화 실행 필요 여부."""
        if not self._last_full_sync:
            return True
        last = datetime.fromisoformat(self._last_full_sync)
        return datetime.now(tz=timezone.utc) >= last + timedelta(hours=self.full_sync_interval_hours)

    def is_quick_sync_due(self) -> bool:
        """빠른 동기화 실행 필요 여부."""
        if not self._last_quick_sync:
            return True
        last = datetime.fromisoformat(self._last_quick_sync)
        return datetime.now(tz=timezone.utc) >= last + timedelta(minutes=self.quick_sync_interval_minutes)

    def get_stats(self) -> dict:
        """스케줄러 통계."""
        jobs = list(self._jobs.values())
        return {
            'total_jobs': len(jobs),
            'pending_jobs': sum(1 for j in jobs if not j.completed),
            'completed_jobs': sum(1 for j in jobs if j.completed),
            'last_full_sync': self._last_full_sync,
            'last_quick_sync': self._last_quick_sync,
            'full_sync_interval_hours': self.full_sync_interval_hours,
            'quick_sync_interval_minutes': self.quick_sync_interval_minutes,
        }
