"""src/cache_layer/l1_cache.py — L1 인메모리 LRU 캐시."""
from __future__ import annotations

import time
from collections import OrderedDict
from typing import Any, Optional


class L1Cache:
    """OrderedDict 기반 LRU 캐시."""

    def __init__(self, maxsize: int = 1000) -> None:
        self._maxsize = maxsize
        self._cache: OrderedDict = OrderedDict()
        self._expiry: dict = {}

    def get(self, key: str) -> Optional[Any]:
        if key not in self._cache:
            return None
        exp = self._expiry.get(key)
        if exp is not None and time.time() > exp:
            del self._cache[key]
            del self._expiry[key]
            return None
        self._cache.move_to_end(key)
        return self._cache[key]

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = value
        if ttl is not None:
            self._expiry[key] = time.time() + ttl
        elif key in self._expiry:
            del self._expiry[key]
        while len(self._cache) > self._maxsize:
            evicted = next(iter(self._cache))
            del self._cache[evicted]
            self._expiry.pop(evicted, None)

    def delete(self, key: str) -> None:
        self._cache.pop(key, None)
        self._expiry.pop(key, None)

    def clear(self) -> None:
        self._cache.clear()
        self._expiry.clear()

    def keys(self) -> list:
        return list(self._cache.keys())
