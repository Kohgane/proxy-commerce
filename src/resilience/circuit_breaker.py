"""src/resilience/circuit_breaker.py — 서킷 브레이커 패턴 구현.

외부 API 호출의 연속 실패 시 자동 차단하고, 쿨다운 후 복구를 시도한다.

상태 전이:
  CLOSED  → (실패 임계값 도달)     → OPEN
  OPEN    → (쿨다운 타임아웃 경과)  → HALF_OPEN
  HALF_OPEN → (성공)               → CLOSED
  HALF_OPEN → (실패)               → OPEN

환경변수:
  CIRCUIT_BREAKER_ENABLED            — 활성화 여부 (기본 "1")
  CIRCUIT_BREAKER_FAILURE_THRESHOLD  — 실패 임계값 (기본 5)
  CIRCUIT_BREAKER_TIMEOUT            — 쿨다운 초 (기본 60)
"""

import functools
import logging
import os
import threading
import time
from enum import Enum
from typing import Callable, Optional, Tuple, Type

logger = logging.getLogger(__name__)

_ENABLED = os.getenv("CIRCUIT_BREAKER_ENABLED", "1") == "1"
_DEFAULT_THRESHOLD = int(os.getenv("CIRCUIT_BREAKER_FAILURE_THRESHOLD", "5"))
_DEFAULT_TIMEOUT = int(os.getenv("CIRCUIT_BREAKER_TIMEOUT", "60"))


# ──────────────────────────────────────────────────────────
# 상태 정의
# ──────────────────────────────────────────────────────────

class CircuitState(Enum):
    """서킷 브레이커 상태."""
    CLOSED = "closed"      # 정상 운영
    OPEN = "open"          # 차단 중
    HALF_OPEN = "half_open"  # 복구 시도 중


class CircuitOpenError(Exception):
    """서킷이 열려 있을 때 발생하는 예외."""
    pass


# ──────────────────────────────────────────────────────────
# 서킷 브레이커
# ──────────────────────────────────────────────────────────

class CircuitBreaker:
    """서킷 브레이커 인스턴스.

    Args:
        name: 서킷 브레이커 이름 (로깅/알림용)
        failure_threshold: 차단까지 허용할 연속 실패 횟수 (기본 5)
        timeout: OPEN → HALF_OPEN 전환까지 쿨다운 초 (기본 60)
        expected_exceptions: 실패로 간주할 예외 타입 튜플 (기본 Exception)
        notify_fn: 상태 변경 시 호출할 콜백 (선택). signature: (name, old_state, new_state)
    """

    def __init__(
        self,
        name: str = "default",
        failure_threshold: int = _DEFAULT_THRESHOLD,
        timeout: int = _DEFAULT_TIMEOUT,
        expected_exceptions: Tuple[Type[Exception], ...] = (Exception,),
        notify_fn: Optional[Callable] = None,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.expected_exceptions = expected_exceptions
        self._notify_fn = notify_fn

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: Optional[float] = None
        self._lock = threading.Lock()

    # ── 상태 속성 ─────────────────────────────────────────

    @property
    def state(self) -> CircuitState:
        """현재 상태를 반환한다. OPEN인 경우 쿨다운 만료 시 HALF_OPEN으로 전환."""
        with self._lock:
            if self._state == CircuitState.OPEN:
                if self._last_failure_time and (time.time() - self._last_failure_time) >= self.timeout:
                    self._transition(CircuitState.HALF_OPEN)
            return self._state

    @property
    def is_closed(self) -> bool:
        return self.state == CircuitState.CLOSED

    @property
    def is_open(self) -> bool:
        return self.state == CircuitState.OPEN

    # ── 호출 처리 ─────────────────────────────────────────

    def call(self, func: Callable, *args, **kwargs):
        """서킷 브레이커를 통해 함수를 호출한다.

        Args:
            func: 호출할 함수
            *args, **kwargs: func에 전달할 인자

        Raises:
            CircuitOpenError: 서킷이 열려 있을 때
            Exception: func 실행 중 발생한 예외
        """
        if not _ENABLED:
            return func(*args, **kwargs)

        current_state = self.state
        if current_state == CircuitState.OPEN:
            logger.warning("서킷 브레이커 차단: name=%s state=OPEN", self.name)
            raise CircuitOpenError(f"서킷 브레이커 '{self.name}'이 열려 있습니다.")

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except self.expected_exceptions as exc:
            self._on_failure()
            raise exc

    def _on_success(self):
        """성공 처리: HALF_OPEN이면 CLOSED로 전환, 실패 카운터 초기화."""
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._transition(CircuitState.CLOSED)
            self._failure_count = 0

    def _on_failure(self):
        """실패 처리: 카운터 증가, 임계값 도달 시 OPEN 전환."""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            if self._failure_count >= self.failure_threshold:
                self._transition(CircuitState.OPEN)

    def _transition(self, new_state: CircuitState):
        """상태 전이 (락 보유 상태에서 호출)."""
        old_state = self._state
        if old_state == new_state:
            return
        self._state = new_state
        if new_state == CircuitState.CLOSED:
            self._failure_count = 0
        logger.info(
            "서킷 브레이커 상태 전환: name=%s %s → %s",
            self.name, old_state.value, new_state.value,
        )
        # 상태 변경 알림
        if self._notify_fn:
            try:
                self._notify_fn(self.name, old_state, new_state)
            except Exception as exc:
                logger.warning("서킷 브레이커 알림 실패: %s", exc)

    def reset(self):
        """서킷을 CLOSED 상태로 강제 초기화한다."""
        with self._lock:
            self._transition(CircuitState.CLOSED)
            self._failure_count = 0
            self._last_failure_time = None

    def __repr__(self) -> str:
        return (
            f"CircuitBreaker(name={self.name!r}, state={self._state.value}, "
            f"failures={self._failure_count}/{self.failure_threshold})"
        )


# ──────────────────────────────────────────────────────────
# 데코레이터
# ──────────────────────────────────────────────────────────

def circuit_breaker(
    failures: int = _DEFAULT_THRESHOLD,
    timeout: int = _DEFAULT_TIMEOUT,
    expected_exceptions: Tuple[Type[Exception], ...] = (Exception,),
    name: Optional[str] = None,
    fallback=None,
):
    """서킷 브레이커 데코레이터.

    Args:
        failures: 차단까지 허용할 연속 실패 횟수
        timeout: OPEN → HALF_OPEN 쿨다운 초
        expected_exceptions: 실패로 간주할 예외 타입 튜플
        name: 서킷 브레이커 이름 (기본: 함수명)
        fallback: 서킷이 열렸을 때 반환할 기본값 (None이면 CircuitOpenError 발생)

    사용 예:
        @circuit_breaker(failures=3, timeout=30)
        def call_shopify_api():
            ...
    """
    def decorator(func: Callable) -> Callable:
        cb_name = name or func.__qualname__
        cb = CircuitBreaker(
            name=cb_name,
            failure_threshold=failures,
            timeout=timeout,
            expected_exceptions=expected_exceptions,
        )
        # 서킷 브레이커 인스턴스를 함수 속성으로 노출
        func._circuit_breaker = cb

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return cb.call(func, *args, **kwargs)
            except CircuitOpenError:
                if fallback is not None:
                    logger.warning("서킷 브레이커 폴백 반환: name=%s", cb_name)
                    return fallback
                raise
        wrapper._circuit_breaker = cb
        return wrapper

    return decorator
