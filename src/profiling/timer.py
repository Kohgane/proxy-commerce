"""
실행 시간 프로파일러 — 함수 실행 시간 측정 및 느린 호출 알림.

환경변수:
    PROFILING_ENABLED: 1이면 활성화 (기본: 0)
    PROFILING_SLOW_THRESHOLD_MS: 느린 호출 임계값(ms), 초과 시 텔레그램 알림 (기본: 5000)
"""

import functools
import logging
import os
import time
from typing import Callable, Optional

logger = logging.getLogger(__name__)

_PROFILING_ENABLED = int(os.getenv("PROFILING_ENABLED", "0"))
_SLOW_THRESHOLD_MS = int(os.getenv("PROFILING_SLOW_THRESHOLD_MS", "5000"))


def profile_time(func: Optional[Callable] = None, *, label: Optional[str] = None, slow_threshold_ms: Optional[int] = None):
    """함수 실행 시간을 측정하고 로깅하는 데코레이터.

    사용 예::

        @profile_time
        def my_function():
            ...

        @profile_time(label="api_call", slow_threshold_ms=2000)
        def slow_api_call():
            ...

    환경변수 PROFILING_ENABLED=0이면 실행 시간 측정을 건너뛴다.
    """
    def decorator(fn: Callable) -> Callable:
        _label = label or fn.__qualname__
        _threshold = slow_threshold_ms if slow_threshold_ms is not None else _SLOW_THRESHOLD_MS

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            if not _PROFILING_ENABLED:
                return fn(*args, **kwargs)

            start = time.perf_counter()
            try:
                result = fn(*args, **kwargs)
                return result
            finally:
                elapsed_ms = (time.perf_counter() - start) * 1000
                logger.debug("[profile] %s: %.1fms", _label, elapsed_ms)

                if elapsed_ms > _threshold:
                    logger.warning("[profile] 느린 호출 감지: %s %.1fms (임계값: %dms)", _label, elapsed_ms, _threshold)
                    _notify_slow_call(_label, elapsed_ms, _threshold)

        return wrapper

    if func is not None:
        # @profile_time (인자 없이 사용)
        return decorator(func)
    # @profile_time(...) (인자와 함께 사용)
    return decorator


def _notify_slow_call(label: str, elapsed_ms: float, threshold_ms: int) -> None:
    """느린 호출을 텔레그램으로 알린다."""
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not bot_token or not chat_id:
        return

    try:
        import urllib.request
        import json as _json
        msg = f"⚠️ [profiling] 느린 호출: {label}\n시간: {elapsed_ms:.0f}ms (임계값: {threshold_ms}ms)"
        data = _json.dumps({"chat_id": chat_id, "text": msg}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception:  # noqa: BLE001
        pass


class TimingContext:
    """실행 시간을 측정하는 컨텍스트 매니저.

    사용 예::

        with TimingContext("api_call") as ctx:
            result = call_external_api()
        print(f"소요 시간: {ctx.elapsed_ms:.1f}ms")
    """

    def __init__(self, label: str, slow_threshold_ms: Optional[int] = None, log_level: str = "debug"):
        """초기화.

        인자:
            label: 측정 레이블
            slow_threshold_ms: 느린 호출 임계값(ms). None이면 환경변수 사용.
            log_level: 로그 레벨 ('debug', 'info', 'warning')
        """
        self.label = label
        self.slow_threshold_ms = slow_threshold_ms if slow_threshold_ms is not None else _SLOW_THRESHOLD_MS
        self.log_level = log_level
        self.elapsed_ms: float = 0.0
        self._start: float = 0.0

    def __enter__(self) -> "TimingContext":
        self._start = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.elapsed_ms = (time.perf_counter() - self._start) * 1000

        if not _PROFILING_ENABLED:
            return

        log_fn = getattr(logger, self.log_level, logger.debug)
        log_fn("[profile] %s: %.1fms", self.label, self.elapsed_ms)

        if self.elapsed_ms > self.slow_threshold_ms:
            logger.warning(
                "[profile] 느린 실행 감지: %s %.1fms (임계값: %dms)",
                self.label, self.elapsed_ms, self.slow_threshold_ms,
            )
            _notify_slow_call(self.label, self.elapsed_ms, self.slow_threshold_ms)

    def __repr__(self) -> str:
        return f"<TimingContext label={self.label!r} elapsed_ms={self.elapsed_ms:.1f}>"
