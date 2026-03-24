"""src/middleware/rate_limiter.py — 고급 레이트 리미팅 미들웨어.

IP 기반 + API 키 기반 레이트 리미트를 메모리(TTL 딕셔너리)로 구현한다.
Redis 없이 동작하며, 프로덕션에서는 Flask-Limiter(Redis 백엔드)와 함께 사용 가능.

엔드포인트별 기본 제한:
  - webhook  : RATE_LIMIT_WEBHOOK (기본 100/min)
  - bot      : RATE_LIMIT_BOT     (기본 30/min)
  - health   : 무제한
  - default  : RATE_LIMIT_DEFAULT (기본 60/min)

환경변수:
  RATE_LIMIT_ENABLED  — "1" 이면 활성화 (기본 "1")
  RATE_LIMIT_DEFAULT  — 기본 제한값 (기본 "60/minute")
  RATE_LIMIT_WEBHOOK  — 웹훅 제한값 (기본 "100/minute")
  RATE_LIMIT_BOT      — 봇 제한값 (기본 "30/minute")
"""

import logging
import os
import threading
import time
from collections import deque
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────
# 환경변수 읽기
# ──────────────────────────────────────────────────────────

ENABLED = os.getenv("RATE_LIMIT_ENABLED", "1") == "1"
_DEFAULT_LIMIT = os.getenv("RATE_LIMIT_DEFAULT", "60/minute")
_WEBHOOK_LIMIT = os.getenv("RATE_LIMIT_WEBHOOK", "100/minute")
_BOT_LIMIT = os.getenv("RATE_LIMIT_BOT", "30/minute")


def _parse_limit(limit_str: str) -> Tuple[int, int]:
    """'60/minute' 형식의 문자열을 (횟수, 윈도우초) 튜플로 파싱한다.

    지원 단위: second, minute, hour, day
    """
    unit_map = {
        "second": 1,
        "minute": 60,
        "hour": 3600,
        "day": 86400,
    }
    try:
        parts = limit_str.strip().split("/")
        count = int(parts[0])
        unit = parts[1].lower().rstrip("s")  # "minutes" → "minute"
        window = unit_map.get(unit, 60)
        return count, window
    except Exception:
        logger.warning("레이트 리미트 파싱 실패: '%s' — 기본값 60/minute 사용", limit_str)
        return 60, 60


# ──────────────────────────────────────────────────────────
# 슬라이딩 윈도우 카운터
# ──────────────────────────────────────────────────────────

class _SlidingWindowCounter:
    """슬라이딩 윈도우 방식의 요청 횟수 추적기."""

    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._timestamps: deque = deque()
        self._lock = threading.Lock()

    def is_allowed(self) -> Tuple[bool, int]:
        """요청 허용 여부와 남은 요청 수를 반환한다.

        Returns:
            (allowed, remaining): 허용 여부와 현재 윈도우에서 남은 요청 수
        """
        now = time.time()
        cutoff = now - self.window_seconds

        with self._lock:
            # 만료된 타임스탬프 제거
            while self._timestamps and self._timestamps[0] < cutoff:
                self._timestamps.popleft()

            current = len(self._timestamps)
            if current >= self.max_requests:
                remaining_time = int(self._timestamps[0] - cutoff) + 1
                return False, remaining_time  # remaining_time = retry-after 초

            self._timestamps.append(now)
            return True, self.max_requests - current - 1

    def reset(self):
        """카운터를 초기화한다."""
        with self._lock:
            self._timestamps.clear()


# ──────────────────────────────────────────────────────────
# 고급 레이트 리미터
# ──────────────────────────────────────────────────────────

class AdvancedRateLimiter:
    """IP + API 키 기반 고급 레이트 리미터.

    Flask before_request / after_request 훅으로 통합하거나
    단독으로 사용할 수 있다.

    사용 예:
        limiter = AdvancedRateLimiter()
        allowed, retry_after = limiter.check("127.0.0.1", endpoint="webhook")
        if not allowed:
            return 429, retry_after
    """

    def __init__(self):
        self._enabled = ENABLED
        # 엔드포인트별 제한 설정
        self._limits: Dict[str, Tuple[int, int]] = {
            "webhook": _parse_limit(_WEBHOOK_LIMIT),
            "bot": _parse_limit(_BOT_LIMIT),
            "default": _parse_limit(_DEFAULT_LIMIT),
        }
        # (key, endpoint) → _SlidingWindowCounter
        self._counters: Dict[str, _SlidingWindowCounter] = {}
        self._lock = threading.Lock()
        # 주기적 정리: 마지막 GC 시각
        self._last_gc: float = time.time()

    def _get_endpoint_type(self, path: str) -> str:
        """URL 경로에서 엔드포인트 타입을 결정한다."""
        if path.startswith("/webhook/telegram") or path.startswith("/bot"):
            return "bot"
        if path.startswith("/webhook"):
            return "webhook"
        if path.startswith("/health"):
            return None  # 헬스체크는 무제한
        return "default"

    def _get_counter(self, key: str, endpoint: str) -> _SlidingWindowCounter:
        """(key, endpoint) 조합의 카운터를 반환하거나 새로 생성한다."""
        counter_key = f"{endpoint}:{key}"
        with self._lock:
            if counter_key not in self._counters:
                max_req, window = self._limits.get(endpoint, self._limits["default"])
                self._counters[counter_key] = _SlidingWindowCounter(max_req, window)
            return self._counters[counter_key]

    def check(self, key: str, path: str = "/") -> Tuple[bool, Optional[int]]:
        """요청 허용 여부를 확인한다.

        Args:
            key: IP 주소 또는 API 키
            path: 요청 URL 경로 (엔드포인트 타입 결정에 사용)

        Returns:
            (allowed, retry_after): 허용 여부와 재시도까지 남은 초(허용 시 None)
        """
        if not self._enabled:
            return True, None

        endpoint = self._get_endpoint_type(path)
        if endpoint is None:
            return True, None  # 헬스체크 무제한

        counter = self._get_counter(key, endpoint)
        allowed, value = counter.is_allowed()

        if not allowed:
            logger.warning("레이트 리미트 초과: key=%s path=%s retry_after=%ds", key, path, value)
            return False, value

        # 주기적 GC (10분마다)
        self._maybe_gc()
        return True, None

    def _maybe_gc(self):
        """10분마다 비활성 카운터를 정리한다."""
        now = time.time()
        if now - self._last_gc < 600:
            return
        with self._lock:
            self._last_gc = now
            # 모든 윈도우 초과한 카운터 제거
            to_delete = [k for k, c in self._counters.items() if len(c._timestamps) == 0]
            for k in to_delete:
                del self._counters[k]
            if to_delete:
                logger.debug("레이트 리미터 GC: %d 개 카운터 제거", len(to_delete))

    def reset(self, key: str = None):
        """특정 키(또는 전체)의 카운터를 초기화한다."""
        with self._lock:
            if key is None:
                self._counters.clear()
            else:
                to_delete = [k for k in self._counters if k.endswith(f":{key}")]
                for k in to_delete:
                    del self._counters[k]
