"""src/rate_limiting/leaky_bucket_limiter.py — 리키 버킷 레이트 리미터."""
from __future__ import annotations

import time
from typing import Dict

from .rate_limiter import RateLimiter


class LeakyBucketLimiter(RateLimiter):
    """리키 버킷 알고리즘 레이트 리미터."""

    def __init__(self, capacity: int = 100, leak_rate: float = 1.0) -> None:
        super().__init__()
        self._capacity = capacity
        self._leak_rate = leak_rate  # requests per second drained
        self._buckets: Dict[str, dict] = {}

    def _get_bucket(self, key: str) -> dict:
        if key not in self._buckets:
            self._buckets[key] = {"level": 0, "last_leak": time.time()}
        return self._buckets[key]

    def check(self, key: str, limit: int, window: int) -> bool:
        bucket = self._get_bucket(key)
        now = time.time()
        elapsed = now - bucket["last_leak"]
        bucket["level"] = max(0, bucket["level"] - elapsed * self._leak_rate)
        bucket["last_leak"] = now
        if bucket["level"] < self._capacity:
            bucket["level"] += 1
            return True
        return False

    def get_usage(self, key: str) -> dict:
        bucket = self._get_bucket(key)
        return {"key": key, "level": bucket["level"], "capacity": self._capacity}
