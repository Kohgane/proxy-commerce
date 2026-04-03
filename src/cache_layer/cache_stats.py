"""src/cache_layer/cache_stats.py — 캐시 통계."""
from __future__ import annotations


class CacheStats:
    """히트/미스/응답시간 추적."""

    def __init__(self) -> None:
        self._hits = 0
        self._misses = 0
        self._total_hit_ms = 0.0
        self._total_miss_ms = 0.0

    def record_hit(self, ms: float = 0.0) -> None:
        self._hits += 1
        self._total_hit_ms += ms

    def record_miss(self, ms: float = 0.0) -> None:
        self._misses += 1
        self._total_miss_ms += ms

    def get_stats(self) -> dict:
        total = self._hits + self._misses
        hit_rate = self._hits / total if total else 0.0
        avg_hit_ms = self._total_hit_ms / self._hits if self._hits else 0.0
        avg_miss_ms = self._total_miss_ms / self._misses if self._misses else 0.0
        return {
            "hits": self._hits,
            "misses": self._misses,
            "total": total,
            "hit_rate": round(hit_rate, 4),
            "avg_hit_ms": round(avg_hit_ms, 2),
            "avg_miss_ms": round(avg_miss_ms, 2),
        }

    def reset(self) -> None:
        self._hits = 0
        self._misses = 0
        self._total_hit_ms = 0.0
        self._total_miss_ms = 0.0
