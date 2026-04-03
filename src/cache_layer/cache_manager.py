"""src/cache_layer/cache_manager.py — 캐시 매니저 (L1+L2 오케스트레이션)."""
from __future__ import annotations

from typing import Any, Optional

from .l1_cache import L1Cache
from .l2_cache import L2Cache


class CacheManager:
    """L1 → L2 순서로 캐시 조회하고 프로모션."""

    def __init__(self, l1: Optional[L1Cache] = None, l2: Optional[L2Cache] = None) -> None:
        self._l1 = l1 or L1Cache()
        self._l2 = l2 or L2Cache()

    def get(self, key: str) -> Optional[Any]:
        val = self._l1.get(key)
        if val is not None:
            return val
        val = self._l2.get(key)
        if val is not None:
            self._l1.set(key, val)
        return val

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        self._l1.set(key, value, ttl=ttl)
        self._l2.set(key, value, ttl=ttl)

    def delete(self, key: str) -> None:
        self._l1.delete(key)
        self._l2.delete(key)

    def clear(self) -> None:
        self._l1.clear()
        self._l2.clear()

    def keys(self) -> list:
        return self._l1.keys()
