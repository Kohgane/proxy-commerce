"""src/webhook_manager/retry_scheduler.py — 지수 백오프 재시도 스케줄러."""
from __future__ import annotations

import time
from typing import Callable, Dict, List


class RetryScheduler:
    """실패 시 지수 백오프 재시도 (최대 5회)."""

    MAX_RETRIES = 5
    BASE_DELAY = 1.0  # 초

    def __init__(self) -> None:
        self._pending: List[dict] = []

    def schedule(self, webhook_id: str, event: str, payload: dict,
                 attempt: int = 1) -> dict:
        """재시도 작업 등록."""
        delay = self._backoff(attempt)
        task = {
            "webhook_id": webhook_id,
            "event": event,
            "payload": payload,
            "attempt": attempt,
            "retry_at": time.time() + delay,
            "delay_seconds": delay,
        }
        self._pending.append(task)
        return dict(task)

    def get_due(self) -> List[dict]:
        """실행 시간이 된 재시도 작업 목록."""
        now = time.time()
        due = [t for t in self._pending if t["retry_at"] <= now]
        self._pending = [t for t in self._pending if t["retry_at"] > now]
        return due

    def cancel(self, webhook_id: str) -> int:
        """특정 웹훅의 미완료 재시도 작업 취소."""
        before = len(self._pending)
        self._pending = [t for t in self._pending if t["webhook_id"] != webhook_id]
        return before - len(self._pending)

    def pending_count(self) -> int:
        return len(self._pending)

    def _backoff(self, attempt: int) -> float:
        """지수 백오프: 1, 2, 4, 8, 16초."""
        return self.BASE_DELAY * (2 ** (attempt - 1))

    def should_retry(self, attempt: int) -> bool:
        """최대 재시도 횟수 초과 여부 확인."""
        return attempt < self.MAX_RETRIES
