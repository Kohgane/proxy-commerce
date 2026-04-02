"""src/scheduler/job_history.py — Phase 40: 작업 실행 이력."""
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

logger = logging.getLogger(__name__)


class JobHistory:
    """작업 실행 이력 저장 및 조회."""

    def __init__(self, max_records: int = 1000):
        self._history: List[dict] = []
        self.max_records = max_records

    def record(
        self,
        job_id: str,
        job_name: str,
        status: str,
        started_at: str,
        ended_at: Optional[str] = None,
        result=None,
        error: Optional[str] = None,
    ) -> dict:
        """실행 이력 기록."""
        record_id = str(uuid.uuid4())[:8]
        record = {
            'id': record_id,
            'job_id': job_id,
            'job_name': job_name,
            'status': status,  # success | failed | running
            'started_at': started_at,
            'ended_at': ended_at or datetime.now(timezone.utc).isoformat(),
            'result': str(result) if result is not None else None,
            'error': error,
        }
        self._history.append(record)
        # 최대 레코드 수 초과 시 오래된 것 삭제
        if len(self._history) > self.max_records:
            self._history = self._history[-self.max_records:]
        return record

    def get_recent(self, job_id: Optional[str] = None, n: int = 10) -> List[dict]:
        """최근 N개 이력 조회."""
        items = self._history
        if job_id:
            items = [h for h in items if h['job_id'] == job_id]
        return items[-n:][::-1]

    def get_by_name(self, job_name: str, n: int = 10) -> List[dict]:
        """작업 이름으로 이력 조회."""
        items = [h for h in self._history if h['job_name'] == job_name]
        return items[-n:][::-1]

    def get_stats(self, job_id: str) -> dict:
        """작업 통계 (성공/실패 횟수)."""
        items = [h for h in self._history if h['job_id'] == job_id]
        success = sum(1 for h in items if h['status'] == 'success')
        failed = sum(1 for h in items if h['status'] == 'failed')
        return {
            'job_id': job_id,
            'total': len(items),
            'success': success,
            'failed': failed,
            'success_rate': round(success / len(items) * 100, 1) if items else 0.0,
        }

    def count(self) -> int:
        """총 이력 레코드 수."""
        return len(self._history)

    def clear(self, job_id: Optional[str] = None) -> int:
        """이력 삭제. 삭제된 레코드 수 반환."""
        before = len(self._history)
        if job_id:
            self._history = [h for h in self._history if h['job_id'] != job_id]
        else:
            self._history = []
        return before - len(self._history)
