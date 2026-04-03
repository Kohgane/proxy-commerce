"""src/rate_limiting/token_bucket_limiter.py — 토큰 버킷 레이트 리미터."""
from __future__ import annotations

import time
from typing import Dict

from .rate_limiter import RateLimiter


class TokenBucketLimiter(RateLimiter):
    """토큰 버킷 알고리즘 레이트 리미터."""

    def __init__(self, capacity: int = 100, refill_rate: float = 1.0) -> None:
        super().__init__()
        self._capacity = capacity
        self._refill_rate = refill_rate  # tokens per second
        self._buckets: Dict[str, dict] = {}

    def _get_bucket(self, key: str) -> dict:
        if key not in self._buckets:
            self._buckets[key] = {"tokens": float(self._capacity), "last_refill": time.time()}
        return self._buckets[key]

    def check(self, key: str, limit: int, window: int) -> bool:
        bucket = self._get_bucket(key)
        now = time.time()
        elapsed = now - bucket["last_refill"]
        bucket["tokens"] = min(self._capacity, bucket["tokens"] + elapsed * self._refill_rate)
        bucket["last_refill"] = now
        if bucket["tokens"] >= 1:
            bucket["tokens"] -= 1
            return True
        return False

    def get_usage(self, key: str) -> dict:
        bucket = self._get_bucket(key)
        return {"key": key, "tokens_remaining": bucket["tokens"], "capacity": self._capacity}
