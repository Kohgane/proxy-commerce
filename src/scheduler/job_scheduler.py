"""src/scheduler/job_scheduler.py — Phase 40: 작업 스케줄러."""
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


def _parse_cron_simple(expr: str, dt: datetime) -> bool:
    """간단한 cron 표현식 파싱 (분 시 * * *)."""
    parts = expr.strip().split()
    if len(parts) != 5:
        return False
    minute_expr, hour_expr = parts[0], parts[1]

    def match(val_expr: str, val: int) -> bool:
        if val_expr == '*':
            return True
        if '/' in val_expr:
            step = int(val_expr.split('/')[1])
            return val % step == 0
        if ',' in val_expr:
            return str(val) in val_expr.split(',')
        if '-' in val_expr:
            lo, hi = val_expr.split('-')
            return int(lo) <= val <= int(hi)
        return str(val) == val_expr

    return match(minute_expr, dt.minute) and match(hour_expr, dt.hour)


class JobScheduler:
    """인터벌/크론 기반 작업 스케줄러.

    - every_minutes / every_hours / daily_at
    - 간단한 cron 표현식 지원
    - 실행/일시정지/재개/삭제
    """

    def __init__(self):
        self._jobs: Dict[str, dict] = {}

    def _add_job(
        self,
        name: str,
        func: Callable,
        schedule_type: str,
        schedule_value,
        enabled: bool = True,
    ) -> dict:
        job_id = str(uuid.uuid4())[:8]
        job = {
            'id': job_id,
            'name': name,
            'func': func,
            'schedule_type': schedule_type,
            'schedule_value': schedule_value,
            'enabled': enabled,
            'status': 'active' if enabled else 'paused',
            'created_at': datetime.now(timezone.utc).isoformat(),
            'last_run': None,
            'next_run': None,
            'run_count': 0,
        }
        self._jobs[job_id] = job
        logger.info("작업 등록: %s (%s=%s)", name, schedule_type, schedule_value)
        return job

    def every_minutes(self, name: str, func: Callable, minutes: int) -> dict:
        """분 인터벌 작업."""
        return self._add_job(name, func, 'interval_minutes', minutes)

    def every_hours(self, name: str, func: Callable, hours: int) -> dict:
        """시간 인터벌 작업."""
        return self._add_job(name, func, 'interval_hours', hours)

    def daily_at(self, name: str, func: Callable, time_str: str) -> dict:
        """매일 특정 시각 실행 (HH:MM)."""
        return self._add_job(name, func, 'daily', time_str)

    def cron(self, name: str, func: Callable, expression: str) -> dict:
        """크론 표현식 기반 작업."""
        return self._add_job(name, func, 'cron', expression)

    def get(self, job_id: str) -> Optional[dict]:
        return self._jobs.get(job_id)

    def get_by_name(self, name: str) -> Optional[dict]:
        for job in self._jobs.values():
            if job['name'] == name:
                return job
        return None

    def list_all(self, enabled_only: bool = False) -> List[dict]:
        jobs = list(self._jobs.values())
        if enabled_only:
            jobs = [j for j in jobs if j['enabled']]
        return jobs

    def pause(self, job_id: str) -> Optional[dict]:
        """작업 일시정지."""
        job = self._jobs.get(job_id)
        if not job:
            return None
        job['enabled'] = False
        job['status'] = 'paused'
        return job

    def resume(self, job_id: str) -> Optional[dict]:
        """작업 재개."""
        job = self._jobs.get(job_id)
        if not job:
            return None
        job['enabled'] = True
        job['status'] = 'active'
        return job

    def delete(self, job_id: str) -> bool:
        """작업 삭제."""
        if job_id in self._jobs:
            del self._jobs[job_id]
            return True
        return False

    def run_job(self, job_id: str) -> dict:
        """작업 즉시 실행."""
        job = self._jobs.get(job_id)
        if not job:
            raise ValueError(f"작업 없음: {job_id}")
        func = job['func']
        started_at = datetime.now(timezone.utc).isoformat()
        try:
            result = func()
            job['last_run'] = started_at
            job['run_count'] += 1
            logger.info("작업 실행 완료: %s", job['name'])
            return {'job_id': job_id, 'status': 'success', 'result': result, 'started_at': started_at}
        except Exception as exc:
            logger.error("작업 실행 실패: %s — %s", job['name'], exc)
            return {'job_id': job_id, 'status': 'failed', 'error': str(exc), 'started_at': started_at}

    def should_run(self, job_id: str, now: Optional[datetime] = None) -> bool:
        """현재 시각에 실행해야 하는지 확인."""
        job = self._jobs.get(job_id)
        if not job or not job['enabled']:
            return False
        if now is None:
            now = datetime.now(timezone.utc)
        schedule_type = job['schedule_type']
        schedule_value = job['schedule_value']
        last_run_str = job.get('last_run')

        if schedule_type == 'cron':
            return _parse_cron_simple(schedule_value, now)
        if schedule_type == 'daily':
            time_str = schedule_value  # HH:MM
            parts = time_str.split(':')
            if len(parts) == 2:
                return now.hour == int(parts[0]) and now.minute == int(parts[1])
            return False
        if schedule_type in ('interval_minutes', 'interval_hours'):
            if not last_run_str:
                return True
            last_run = datetime.fromisoformat(last_run_str)
            if schedule_type == 'interval_minutes':
                delta = timedelta(minutes=schedule_value)
            else:
                delta = timedelta(hours=schedule_value)
            return now >= last_run + delta
        return False
