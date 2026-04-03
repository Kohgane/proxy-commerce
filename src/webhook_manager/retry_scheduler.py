"""src/webhook_manager/retry_scheduler.py — 재시도 스케줄러."""
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

MAX_RETRIES = 5
BASE_DELAY = 60  # seconds


class RetryScheduler:
    """지수 백오프 재시도 스케줄러."""

    def __init__(self):
        self._queue: List[dict] = []

    def schedule_retry(
        self,
        webhook_id: str,
        event: str,
        payload: dict,
        attempt: int,
    ) -> Optional[dict]:
        if attempt > MAX_RETRIES:
            logger.warning("최대 재시도 초과: %s (attempt %d)", webhook_id, attempt)
            return None
        delay = (attempt ** 2) * BASE_DELAY
        entry = {
            'webhook_id': webhook_id,
            'event': event,
            'payload': payload,
            'attempt': attempt,
            'delay_seconds': delay,
        }
        self._queue.append(entry)
        logger.info("재시도 예약: %s (attempt %d, delay %ds)", webhook_id, attempt, delay)
        return entry

    def get_queue(self) -> List[dict]:
        return list(self._queue)

    def clear_queue(self) -> None:
        self._queue.clear()
