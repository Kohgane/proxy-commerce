"""src/rate_limiting/rate_limiter.py — 레이트 리미터 기본 클래스."""
from __future__ import annotations

from typing import Dict


class RateLimiter:
    """레이트 리미터 기본 클래스."""

    def __init__(self) -> None:
        self._usage: Dict[str, dict] = {}

    def check(self, key: str, limit: int, window: int) -> bool:
        """요청 허용 여부 반환. 기본 구현은 항상 허용."""
        return True

    def get_usage(self, key: str) -> dict:
        """현재 사용량 반환."""
        return self._usage.get(key, {"count": 0, "key": key})
