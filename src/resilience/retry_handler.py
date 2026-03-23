"""src/resilience/retry_handler.py — 지수 백오프 + 지터 재시도 핸들러.

네트워크/API 요청의 일시적 실패를 자동으로 재시도한다.

기능:
  - 지수 백오프 (exponential backoff)
  - 지터(jitter) — 동시 재시도 폭풍 방지
  - 재시도 가능 예외 타입 설정
  - 최대 재시도 횟수 + 총 타임아웃
  - 재시도 상황 로깅

사용 예:
    @retry(max_retries=3, backoff=2.0, exceptions=(requests.RequestException,))
    def fetch_data():
        ...

    # 또는 직접 사용:
    handler = RetryHandler(max_retries=3)
    result = handler.execute(my_func, arg1, arg2)
"""

import functools
import logging
import random
import time
from typing import Callable, Optional, Tuple, Type

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────
# 재시도 핸들러 클래스
# ──────────────────────────────────────────────────────────

class RetryHandler:
    """지수 백오프 + 지터 기반 재시도 핸들러.

    Args:
        max_retries: 최대 재시도 횟수 (초기 시도 제외, 기본 3)
        backoff: 백오프 배수 (기본 2.0)
        initial_delay: 첫 재시도 대기 초 (기본 1.0)
        max_delay: 최대 대기 초 (기본 60.0)
        jitter: 지터 활성화 여부 (기본 True) — 대기 시간에 ±50% 랜덤 변동
        exceptions: 재시도할 예외 타입 튜플 (기본 (Exception,))
        total_timeout: 총 허용 시간 초 (0이면 무제한, 기본 0)
    """

    def __init__(
        self,
        max_retries: int = 3,
        backoff: float = 2.0,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        jitter: bool = True,
        exceptions: Tuple[Type[Exception], ...] = (Exception,),
        total_timeout: float = 0.0,
    ):
        self.max_retries = max_retries
        self.backoff = backoff
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.jitter = jitter
        self.exceptions = exceptions
        self.total_timeout = total_timeout

    def _calc_delay(self, attempt: int) -> float:
        """n번째 재시도 대기 시간을 계산한다 (지터 포함).

        Args:
            attempt: 현재 재시도 번호 (1부터 시작)

        Returns:
            대기 초
        """
        delay = self.initial_delay * (self.backoff ** (attempt - 1))
        delay = min(delay, self.max_delay)
        if self.jitter:
            # ±50% 랜덤 변동
            delay = delay * (0.5 + random.random())
        return delay

    def execute(self, func: Callable, *args, **kwargs):
        """재시도 로직으로 함수를 실행한다.

        Args:
            func: 실행할 함수
            *args, **kwargs: func에 전달할 인자

        Returns:
            func의 반환값

        Raises:
            마지막 재시도에서 발생한 예외
        """
        start_time = time.time()
        last_exc: Optional[Exception] = None

        for attempt in range(self.max_retries + 1):
            # 총 타임아웃 검사
            if self.total_timeout > 0 and (time.time() - start_time) >= self.total_timeout:
                logger.error("재시도 총 타임아웃 초과: func=%s", func.__name__)
                break

            try:
                result = func(*args, **kwargs)
                if attempt > 0:
                    logger.info("재시도 성공: func=%s attempt=%d", func.__name__, attempt)
                return result
            except self.exceptions as exc:
                last_exc = exc
                if attempt >= self.max_retries:
                    logger.error(
                        "최대 재시도 초과: func=%s retries=%d error=%s",
                        func.__name__, self.max_retries, exc,
                    )
                    break

                delay = self._calc_delay(attempt + 1)
                logger.warning(
                    "재시도 예정: func=%s attempt=%d/%d delay=%.2fs error=%s",
                    func.__name__, attempt + 1, self.max_retries, delay, exc,
                )
                time.sleep(delay)

        if last_exc is not None:
            raise last_exc
        raise RuntimeError(f"재시도 핸들러 예기치 않은 종료: func={func.__name__}")


# ──────────────────────────────────────────────────────────
# 데코레이터
# ──────────────────────────────────────────────────────────

def retry(
    max_retries: int = 3,
    backoff: float = 2.0,
    initial_delay: float = 1.0,
    max_delay: float = 60.0,
    jitter: bool = True,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    total_timeout: float = 0.0,
):
    """재시도 데코레이터.

    Args:
        max_retries: 최대 재시도 횟수
        backoff: 백오프 배수
        initial_delay: 첫 재시도 대기 초
        max_delay: 최대 대기 초
        jitter: 지터 활성화 여부
        exceptions: 재시도할 예외 타입 튜플
        total_timeout: 총 허용 시간 초 (0이면 무제한)

    사용 예:
        @retry(max_retries=3, backoff=2.0, exceptions=(requests.RequestException,))
        def call_api():
            ...
    """
    def decorator(func: Callable) -> Callable:
        handler = RetryHandler(
            max_retries=max_retries,
            backoff=backoff,
            initial_delay=initial_delay,
            max_delay=max_delay,
            jitter=jitter,
            exceptions=exceptions,
            total_timeout=total_timeout,
        )

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return handler.execute(func, *args, **kwargs)

        wrapper._retry_handler = handler
        return wrapper

    return decorator
