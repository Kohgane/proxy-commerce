"""src/exception_handler/retry_manager.py — 자동 재시도 관리 (Phase 105)."""
from __future__ import annotations

import logging
import math
import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class BackoffStrategy(str, Enum):
    fixed = 'fixed'
    exponential = 'exponential'
    linear = 'linear'
    jitter = 'jitter'


class RetryStatus(str, Enum):
    pending = 'pending'
    running = 'running'
    succeeded = 'succeeded'
    failed = 'failed'
    exhausted = 'exhausted'
    manual_required = 'manual_required'


@dataclass
class RetryPolicy:
    max_retries: int = 3
    backoff_strategy: BackoffStrategy = BackoffStrategy.exponential
    delay_seconds: float = 1.0
    timeout: float = 30.0
    max_delay_seconds: float = 300.0

    def compute_delay(self, attempt: int) -> float:
        """attempt는 1-based (첫 재시도=1)."""
        if self.backoff_strategy == BackoffStrategy.fixed:
            delay = self.delay_seconds
        elif self.backoff_strategy == BackoffStrategy.exponential:
            delay = self.delay_seconds * (2 ** (attempt - 1))
        elif self.backoff_strategy == BackoffStrategy.linear:
            delay = self.delay_seconds * attempt
        elif self.backoff_strategy == BackoffStrategy.jitter:
            base = self.delay_seconds * (2 ** (attempt - 1))
            delay = random.uniform(0, base)
        else:
            delay = self.delay_seconds
        return min(delay, self.max_delay_seconds)

    def to_dict(self) -> Dict:
        return {
            'max_retries': self.max_retries,
            'backoff_strategy': self.backoff_strategy.value,
            'delay_seconds': self.delay_seconds,
            'timeout': self.timeout,
            'max_delay_seconds': self.max_delay_seconds,
        }


@dataclass
class RetryRecord:
    record_id: str
    task_type: str
    order_id: Optional[str]
    policy: RetryPolicy
    status: RetryStatus = RetryStatus.pending
    attempt_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_attempt_at: Optional[str] = None
    next_attempt_at: Optional[str] = None
    last_error: Optional[str] = None
    result: Optional[Any] = None

    def to_dict(self) -> Dict:
        return {
            'record_id': self.record_id,
            'task_type': self.task_type,
            'order_id': self.order_id,
            'policy': self.policy.to_dict(),
            'status': self.status.value,
            'attempt_count': self.attempt_count,
            'created_at': self.created_at,
            'last_attempt_at': self.last_attempt_at,
            'next_attempt_at': self.next_attempt_at,
            'last_error': self.last_error,
        }


class RetryManager:
    """실패한 작업 자동 재시도 관리."""

    _DEFAULT_POLICY = RetryPolicy()

    def __init__(self) -> None:
        self._records: Dict[str, RetryRecord] = {}

    def register(
        self,
        task_type: str,
        order_id: Optional[str] = None,
        policy: Optional[RetryPolicy] = None,
    ) -> RetryRecord:
        record_id = f'retry_{uuid.uuid4().hex[:10]}'
        record = RetryRecord(
            record_id=record_id,
            task_type=task_type,
            order_id=order_id,
            policy=policy or RetryPolicy(),
        )
        self._records[record_id] = record
        logger.info("재시도 등록: %s (task=%s)", record_id, task_type)
        return record

    def execute(
        self,
        record_id: str,
        task_fn: Callable[[], Any],
    ) -> RetryRecord:
        """등록된 재시도 레코드로 작업 실행. task_fn은 예외를 throw하면 실패."""
        record = self._get_or_raise(record_id)
        policy = record.policy

        record.status = RetryStatus.running

        for attempt in range(1, policy.max_retries + 1):
            record.attempt_count = attempt
            record.last_attempt_at = datetime.now(timezone.utc).isoformat()

            try:
                result = task_fn()
                record.result = result
                record.status = RetryStatus.succeeded
                record.last_error = None
                logger.info("재시도 성공: %s (attempt=%d)", record_id, attempt)
                return record
            except Exception as exc:
                record.last_error = str(exc)
                logger.warning(
                    "재시도 실패 %s (attempt=%d/%d): %s",
                    record_id, attempt, policy.max_retries, exc,
                )

                if attempt < policy.max_retries:
                    delay = policy.compute_delay(attempt)
                    # 실제 sleep은 하지 않음 (mock 환경); next_attempt_at만 기록
                    record.next_attempt_at = f'(delay={delay:.1f}s)'

        record.status = RetryStatus.exhausted
        logger.error("재시도 소진: %s (최대 %d회)", record_id, policy.max_retries)
        self._on_exhausted(record)
        return record

    def _on_exhausted(self, record: RetryRecord) -> None:
        """최대 재시도 초과 시 수동 전환."""
        record.status = RetryStatus.manual_required
        logger.warning("수동 처리 필요: %s", record.record_id)

    def get_record(self, record_id: str) -> Optional[RetryRecord]:
        return self._records.get(record_id)

    def list_records(
        self,
        task_type: Optional[str] = None,
        status: Optional[RetryStatus] = None,
    ) -> List[RetryRecord]:
        records = list(self._records.values())
        if task_type:
            records = [r for r in records if r.task_type == task_type]
        if status:
            records = [r for r in records if r.status == status]
        return records

    def get_stats(self) -> Dict:
        records = list(self._records.values())
        by_status: Dict[str, int] = {}
        by_task: Dict[str, int] = {}
        for r in records:
            by_status[r.status.value] = by_status.get(r.status.value, 0) + 1
            by_task[r.task_type] = by_task.get(r.task_type, 0) + 1
        succeeded = by_status.get(RetryStatus.succeeded.value, 0)
        total = len(records)
        return {
            'total': total,
            'succeeded': succeeded,
            'success_rate': succeeded / total if total else 0.0,
            'by_status': by_status,
            'by_task_type': by_task,
        }

    def _get_or_raise(self, record_id: str) -> RetryRecord:
        record = self._records.get(record_id)
        if record is None:
            raise KeyError(f'재시도 레코드를 찾을 수 없습니다: {record_id}')
        return record
