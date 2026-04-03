"""src/cache_layer/cache_invalidator.py — 태그/패턴 기반 캐시 무효화."""
from __future__ import annotations

import re
from typing import List

from .cache_manager import CacheManager


class CacheInvalidator:
    """태그 기반 및 패턴 기반 캐시 무효화."""

    def __init__(self, manager: CacheManager) -> None:
        self._manager = manager
        self._tag_map: dict = {}  # tag -> [keys]

    def tag_key(self, key: str, tags: List[str]) -> None:
        for tag in tags:
            self._tag_map.setdefault(tag, set()).add(key)

    def invalidate_by_tag(self, tag: str) -> int:
        keys = list(self._tag_map.get(tag, set()))
        for k in keys:
            self._manager.delete(k)
        self._tag_map.pop(tag, None)
        return len(keys)

    def invalidate_by_pattern(self, pattern: str) -> int:
        keys = self._manager.keys()
        count = 0
        # Validate pattern to prevent ReDoS: only allow safe characters
        safe_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_:-/.*?[]^$")
        if not all(c in safe_chars for c in pattern):
            return 0
        try:
            regex = re.compile(pattern)
            for k in keys:
                if regex.search(k):
                    self._manager.delete(k)
                    count += 1
        except re.error:
            pass
        return count
