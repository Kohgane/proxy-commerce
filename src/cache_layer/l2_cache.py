"""src/cache_layer/l2_cache.py — L2 파일 기반 캐시."""
from __future__ import annotations

import json
import os
import time
from typing import Any, Optional


class L2Cache:
    """JSON 파일 기반 캐시 (TTL 지원)."""

    def __init__(self, cache_dir: str = "./data/cache") -> None:
        self._dir = cache_dir
        os.makedirs(self._dir, exist_ok=True)

    def _path(self, key: str) -> str:
        safe_key = key.replace("/", "_").replace(":", "_")
        return os.path.join(self._dir, f"{safe_key}.json")

    def get(self, key: str) -> Optional[Any]:
        path = self._path(key)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                entry = json.load(f)
            exp = entry.get("expiry")
            if exp is not None and time.time() > exp:
                os.remove(path)
                return None
            return entry.get("value")
        except (OSError, json.JSONDecodeError):
            return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        path = self._path(key)
        entry = {"value": value, "expiry": time.time() + ttl if ttl else None}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(entry, f, ensure_ascii=False, default=str)

    def delete(self, key: str) -> None:
        path = self._path(key)
        if os.path.exists(path):
            os.remove(path)

    def clear(self) -> None:
        for fn in os.listdir(self._dir):
            if fn.endswith(".json"):
                try:
                    os.remove(os.path.join(self._dir, fn))
                except OSError:
                    pass
