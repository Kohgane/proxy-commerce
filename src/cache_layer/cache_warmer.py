"""src/cache_layer/cache_warmer.py — 캐시 워머."""
from __future__ import annotations

from typing import Any, Callable, List

from .cache_manager import CacheManager


class CacheWarmer:
    """캐시 사전 워밍."""

    def __init__(self, manager: CacheManager) -> None:
        self._manager = manager

    def warm(self, data_loader_fn: Callable[[str], Any], keys: List[str],
             ttl: int | None = None) -> dict:
        results = {"warmed": [], "failed": []}
        for key in keys:
            try:
                value = data_loader_fn(key)
                self._manager.set(key, value, ttl=ttl)
                results["warmed"].append(key)
            except Exception:
                results["failed"].append(key)
        return results
