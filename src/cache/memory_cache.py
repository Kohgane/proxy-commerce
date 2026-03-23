"""src/cache/memory_cache.py — Thread-safe TTL 인메모리 캐시.

기존 src/utils/cache.py의 TTLCache를 기반으로 스레드 안전성과
히트/미스 통계 기능을 추가한 프로덕션 수준의 캐시 구현.

환경변수:
  CACHE_ENABLED      — 캐시 활성화 여부 (기본 "1")
  CACHE_MAX_SIZE     — 최대 항목 수 (기본 1000, 0=무제한)
  CACHE_DEFAULT_TTL  — 기본 TTL 초 (기본 300)
"""

import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_CACHE_ENABLED = os.getenv("CACHE_ENABLED", "1") == "1"
_DEFAULT_TTL = int(os.getenv("CACHE_DEFAULT_TTL", "300"))
_MAX_SIZE = int(os.getenv("CACHE_MAX_SIZE", "1000"))


class CacheStats:
    """캐시 히트/미스 통계."""

    def __init__(self):
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        self._lock = threading.Lock()

    def record_hit(self):
        with self._lock:
            self._hits += 1

    def record_miss(self):
        with self._lock:
            self._misses += 1

    def record_eviction(self):
        with self._lock:
            self._evictions += 1

    @property
    def hits(self) -> int:
        return self._hits

    @property
    def misses(self) -> int:
        return self._misses

    @property
    def evictions(self) -> int:
        return self._evictions

    @property
    def hit_rate(self) -> float:
        """캐시 히트율 (0.0 ~ 1.0)."""
        total = self._hits + self._misses
        return round(self._hits / total, 4) if total > 0 else 0.0

    def reset(self):
        with self._lock:
            self._hits = 0
            self._misses = 0
            self._evictions = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hits": self._hits,
            "misses": self._misses,
            "evictions": self._evictions,
            "hit_rate": self.hit_rate,
        }


class MemoryCache:
    """Thread-safe TTL 인메모리 캐시 with LRU 정리.

    기존 src/utils/cache.TTLCache와 API 호환을 유지하면서
    스레드 안전성과 히트/미스 통계를 추가한다.

    Args:
        ttl_seconds: 기본 TTL 초 (기본: 환경변수 CACHE_DEFAULT_TTL)
        max_size: 최대 항목 수 (기본: 환경변수 CACHE_MAX_SIZE, 0=무제한)
        enabled: 캐시 활성화 여부 (기본: 환경변수 CACHE_ENABLED)
    """

    def __init__(
        self,
        ttl_seconds: int = _DEFAULT_TTL,
        max_size: int = _MAX_SIZE,
        enabled: bool = _CACHE_ENABLED,
    ):
        self._ttl = ttl_seconds
        self._max_size = max_size
        self._enabled = enabled
        # key → (value, stored_at, ttl)
        self._store: Dict[str, Tuple[Any, float, int]] = {}
        self._lock = threading.Lock()
        self.stats = CacheStats()

    # ── 공개 API ──────────────────────────────────────────

    def get(self, key: str, ttl: Optional[int] = None) -> Optional[Any]:
        """캐시에서 값을 가져온다. 만료 또는 없으면 None 반환."""
        if not self._enabled:
            self.stats.record_miss()
            return None

        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self.stats.record_miss()
                logger.debug("캐시 MISS: key=%s", key)
                return None

            value, stored_at, entry_ttl = entry
            effective_ttl = ttl if ttl is not None else entry_ttl
            if time.time() - stored_at > effective_ttl:
                del self._store[key]
                self.stats.record_miss()
                logger.debug("캐시 MISS (만료): key=%s", key)
                return None

            self.stats.record_hit()
            logger.debug("캐시 HIT: key=%s", key)
            return value

    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """캐시에 값을 저장한다."""
        if not self._enabled:
            return

        entry_ttl = ttl if ttl is not None else self._ttl
        with self._lock:
            # LRU 방식 eviction: max_size 초과 시 오래된 항목 제거
            if self._max_size > 0 and len(self._store) >= self._max_size and key not in self._store:
                oldest_key = min(self._store, key=lambda k: self._store[k][1])
                del self._store[oldest_key]
                self.stats.record_eviction()
                logger.debug("캐시 evict (max_size=%d): key=%s", self._max_size, oldest_key)

            self._store[key] = (value, time.time(), entry_ttl)
            logger.debug("캐시 SET: key=%s ttl=%ds", key, entry_ttl)

    def delete(self, key: str) -> bool:
        """캐시 항목을 삭제한다."""
        with self._lock:
            if key in self._store:
                del self._store[key]
                logger.debug("캐시 DELETE: key=%s", key)
                return True
        return False

    def clear(self):
        """전체 캐시를 비운다."""
        with self._lock:
            count = len(self._store)
            self._store.clear()
            logger.debug("캐시 CLEAR: %d 항목 제거", count)

    def purge_expired(self) -> int:
        """만료된 항목을 제거하고 제거된 수를 반환한다."""
        now = time.time()
        with self._lock:
            expired = [
                k for k, (_, stored_at, ttl) in self._store.items()
                if now - stored_at > ttl
            ]
            for k in expired:
                del self._store[k]
        if expired:
            logger.debug("캐시 만료 항목 정리: %d 개", len(expired))
        return len(expired)

    def keys(self) -> List[str]:
        """유효한 캐시 키 목록을 반환한다."""
        now = time.time()
        with self._lock:
            return [
                k for k, (_, stored_at, ttl) in self._store.items()
                if now - stored_at <= ttl
            ]

    def size(self) -> int:
        """현재 캐시 항목 수 (만료 포함)."""
        with self._lock:
            return len(self._store)

    def is_valid(self, key: str) -> bool:
        """캐시 항목이 유효한지 확인한다."""
        return self.get(key) is not None

    def __len__(self) -> int:
        return self.size()

    def __contains__(self, key: str) -> bool:
        return self.is_valid(key)
