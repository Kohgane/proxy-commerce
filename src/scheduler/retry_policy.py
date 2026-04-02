"""src/scheduler/retry_policy.py — Phase 40: 재시도 정책."""
import logging
import time
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class RetryPolicy:
    """재시도 정책.

    - 최대 재시도 횟수
    - 지수 백오프
    """

    def __init__(self, max_retries: int = 3, base_delay: float = 1.0, backoff_factor: float = 2.0,
                 max_delay: float = 60.0):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.backoff_factor = backoff_factor
        self.max_delay = max_delay

    def get_delay(self, attempt: int) -> float:
        """시도 횟수에 따른 대기 시간 (초)."""
        delay = self.base_delay * (self.backoff_factor ** attempt)
        return min(delay, self.max_delay)

    def execute(self, func: Callable, *args, sleep_fn: Optional[Callable] = None, **kwargs):
        """재시도 정책 적용하여 함수 실행.

        Args:
            func: 실행할 함수
            *args: 함수 인자
            sleep_fn: 대기 함수 (테스트 시 mock 가능)
            **kwargs: 함수 키워드 인자

        Returns:
            함수 반환값

        Raises:
            마지막 예외
        """
        _sleep = sleep_fn or time.sleep
        last_exc: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                return func(*args, **kwargs)
            except Exception as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    delay = self.get_delay(attempt)
                    logger.warning("시도 %d/%d 실패, %.1f초 후 재시도: %s", attempt + 1, self.max_retries, delay, exc)
                    _sleep(delay)
                else:
                    logger.error("최대 재시도 초과: %s", exc)
        raise last_exc

    def should_retry(self, attempt: int) -> bool:
        """재시도 여부 확인."""
        return attempt < self.max_retries
