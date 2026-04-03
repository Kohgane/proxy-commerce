"""src/rate_limiting/sliding_window_limiter.py — 슬라이딩 윈도우 레이트 리미터."""
from __future__ import annotations

import time
from typing import Dict, List

from .rate_limiter import RateLimiter


class SlidingWindowLimiter(RateLimiter):
    """슬라이딩 윈도우 알고리즘으로 요청 횟수 제한."""

    def __init__(self) -> None:
        super().__init__()
        self._timestamps: Dict[str, List[float]] = {}

    def check(self, key: str, limit: int, window: int) -> bool:
        now = time.time()
        cutoff = now - window
        ts_list = self._timestamps.get(key, [])
        ts_list = [t for t in ts_list if t > cutoff]
        if len(ts_list) >= limit:
            self._timestamps[key] = ts_list
            return False
        ts_list.append(now)
        self._timestamps[key] = ts_list
        return True

    def get_usage(self, key: str) -> dict:
        now = time.time()
        ts_list = self._timestamps.get(key, [])
        return {"key": key, "count": len(ts_list), "timestamps": len(ts_list)}
