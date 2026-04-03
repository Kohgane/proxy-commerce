"""src/recommendation/recommendation_cache.py — 추천 캐시."""
from __future__ import annotations

import time


class RecommendationCache:
    """추천 캐시."""

    def __init__(self, ttl: int = 300) -> None:
        self.ttl = ttl
        self._cache: dict[str, dict] = {}

    def set(self, key: str, data: list) -> None:
        """캐시에 저장한다."""
        self._cache[key] = {'data': data, 'expires_at': time.time() + self.ttl}

    def get(self, key: str) -> list | None:
        """캐시에서 조회한다."""
        entry = self._cache.get(key)
        if entry is None:
            return None
        if time.time() > entry['expires_at']:
            del self._cache[key]
            return None
        return entry['data']

    def invalidate(self, key: str) -> None:
        """캐시를 무효화한다."""
        self._cache.pop(key, None)
