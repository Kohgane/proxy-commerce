"""src/ai_pricing/pricing_scheduler.py — 가격 업데이트 스케줄러 (Phase 97)."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# 스케줄 유형
SCHEDULE_HOURLY = 'hourly'
SCHEDULE_DAILY = 'daily'
SCHEDULE_MANUAL = 'manual'

# 가격 유형
PRICE_TYPE_PEAK = 'peak'
PRICE_TYPE_OFF_PEAK = 'off_peak'
PRICE_TYPE_PROMO = 'promo'

# 피크 타임 시간대 (KST 기준) — 10~12, 19~22시
_PEAK_HOURS = set(range(10, 13)) | set(range(19, 23))


class ScheduledJob:
    """스케줄 작업 데이터."""

    def __init__(
        self,
        schedule_type: str,
        skus: List[str] = None,
        category: str = '',
        hour: int = None,
    ) -> None:
        self.job_id: str = str(uuid.uuid4())
        self.schedule_type: str = schedule_type
        self.skus: List[str] = skus or []
        self.category: str = category
        self.hour: Optional[int] = hour
        self.enabled: bool = True
        self.last_run: Optional[datetime] = None
        self.next_run: Optional[datetime] = None
        self.run_count: int = 0
        self.created_at: datetime = datetime.now(timezone.utc)

    def to_dict(self) -> Dict:
        return {
            'job_id': self.job_id,
            'schedule_type': self.schedule_type,
            'skus': self.skus,
            'category': self.category,
            'hour': self.hour,
            'enabled': self.enabled,
            'last_run': self.last_run.isoformat() if self.last_run else None,
            'next_run': self.next_run.isoformat() if self.next_run else None,
            'run_count': self.run_count,
            'created_at': self.created_at.isoformat(),
        }


class PromoSchedule:
    """프로모션 가격 예약."""

    def __init__(
        self,
        sku: str,
        promo_price: float,
        start_at: datetime,
        end_at: datetime,
        reason: str = '',
    ) -> None:
        self.promo_id: str = str(uuid.uuid4())
        self.sku: str = sku
        self.promo_price: float = promo_price
        self.start_at: datetime = start_at
        self.end_at: datetime = end_at
        self.reason: str = reason
        self.active: bool = False
        self.applied: bool = False

    def is_active(self, now: datetime = None) -> bool:
        """현재 시점에 프로모션이 활성 상태인지 확인한다."""
        t = now or datetime.now(timezone.utc)
        return self.start_at <= t <= self.end_at

    def to_dict(self) -> Dict:
        return {
            'promo_id': self.promo_id,
            'sku': self.sku,
            'promo_price': self.promo_price,
            'start_at': self.start_at.isoformat(),
            'end_at': self.end_at.isoformat(),
            'reason': self.reason,
            'active': self.is_active(),
            'applied': self.applied,
        }


class PricingScheduler:
    """가격 업데이트 스케줄 관리.

    - 매시간/매일/수동 스케줄 등록
    - 피크타임/오프피크 가격 구분
    - 프로모션 가격 예약 (시작/종료 시간)
    - 배치 가격 업데이트
    """

    def __init__(self) -> None:
        self._jobs: Dict[str, ScheduledJob] = {}
        self._promos: Dict[str, PromoSchedule] = {}
        self._batch_history: List[Dict] = []

    # ── 스케줄 관리 ───────────────────────────────────────────────────────

    def add_schedule(
        self,
        schedule_type: str,
        skus: List[str] = None,
        category: str = '',
        hour: int = None,
    ) -> ScheduledJob:
        """스케줄 작업을 등록한다."""
        job = ScheduledJob(
            schedule_type=schedule_type,
            skus=skus or [],
            category=category,
            hour=hour,
        )
        self._jobs[job.job_id] = job
        logger.info('스케줄 등록: %s [%s]', job.job_id, schedule_type)
        return job

    def remove_schedule(self, job_id: str) -> bool:
        """스케줄 작업을 제거한다."""
        if job_id in self._jobs:
            del self._jobs[job_id]
            return True
        return False

    def get_schedules(self) -> List[Dict]:
        """모든 스케줄을 반환한다."""
        return [job.to_dict() for job in self._jobs.values()]

    def get_schedule(self, job_id: str) -> Optional[ScheduledJob]:
        """특정 스케줄을 반환한다."""
        return self._jobs.get(job_id)

    def mark_ran(self, job_id: str) -> None:
        """스케줄 작업 실행 완료를 표시한다."""
        job = self._jobs.get(job_id)
        if job:
            job.last_run = datetime.now(timezone.utc)
            job.run_count += 1

    # ── 피크타임 가격 ─────────────────────────────────────────────────────

    def get_current_price_type(self, hour: int = None) -> str:
        """현재 시간대의 가격 유형을 반환한다 (peak/off_peak)."""
        h = hour if hour is not None else datetime.now(timezone.utc).hour
        # KST = UTC+9
        kst_hour = (h + 9) % 24
        return PRICE_TYPE_PEAK if kst_hour in _PEAK_HOURS else PRICE_TYPE_OFF_PEAK

    def get_peak_multiplier(self, hour: int = None) -> float:
        """피크타임 가격 배율을 반환한다."""
        price_type = self.get_current_price_type(hour)
        return 1.05 if price_type == PRICE_TYPE_PEAK else 1.0

    # ── 프로모션 예약 ─────────────────────────────────────────────────────

    def schedule_promo(
        self,
        sku: str,
        promo_price: float,
        start_at: datetime,
        end_at: datetime,
        reason: str = '',
    ) -> PromoSchedule:
        """프로모션 가격을 예약한다."""
        promo = PromoSchedule(
            sku=sku,
            promo_price=promo_price,
            start_at=start_at,
            end_at=end_at,
            reason=reason,
        )
        self._promos[promo.promo_id] = promo
        logger.info('프로모션 예약: %s [%s] %s~%s', promo.promo_id, sku, start_at, end_at)
        return promo

    def get_active_promo(self, sku: str) -> Optional[PromoSchedule]:
        """현재 활성 프로모션을 반환한다."""
        now = datetime.now(timezone.utc)
        for promo in self._promos.values():
            if promo.sku == sku and promo.is_active(now):
                return promo
        return None

    def get_promos(self, sku: str = None) -> List[Dict]:
        """프로모션 목록을 반환한다."""
        promos = list(self._promos.values())
        if sku:
            promos = [p for p in promos if p.sku == sku]
        return [p.to_dict() for p in promos]

    # ── 배치 업데이트 ─────────────────────────────────────────────────────

    def run_batch_update(
        self,
        skus: List[str],
        price_map: Dict[str, float],
        dry_run: bool = False,
    ) -> Dict:
        """배치 가격 업데이트를 실행한다.

        Args:
            skus: 업데이트 대상 SKU 목록
            price_map: {sku: new_price} 매핑
            dry_run: True이면 실제 적용 안 함

        Returns:
            배치 업데이트 결과
        """
        results = []
        applied = 0
        skipped = 0

        for sku in skus:
            new_price = price_map.get(sku)
            if new_price is None:
                skipped += 1
                continue
            result = {
                'sku': sku,
                'new_price': new_price,
                'applied': not dry_run,
            }
            results.append(result)
            if not dry_run:
                applied += 1

        batch_result = {
            'batch_id': str(uuid.uuid4()),
            'dry_run': dry_run,
            'total': len(skus),
            'applied': applied,
            'skipped': skipped,
            'results': results,
            'executed_at': datetime.now(timezone.utc).isoformat(),
        }
        self._batch_history.append(batch_result)
        logger.info(
            '배치 업데이트: %d건 처리 (%s)',
            len(skus),
            'dry_run' if dry_run else '적용',
        )
        return batch_result

    def get_batch_history(self) -> List[Dict]:
        """배치 업데이트 이력을 반환한다."""
        return list(self._batch_history)
