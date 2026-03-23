"""src/utils/cache.py — TTL 기반 범용 인메모리 캐시 유틸리티.

환율, 번역, 재고 조회 결과 등 외부 API 호출 결과를 캐싱하여
불필요한 네트워크 요청을 줄인다.

사용 예:
    cache = TTLCache(ttl_seconds=300)
    cache.set('my_key', {'data': 123})
    value = cache.get('my_key')  # 300초 내이면 반환, 만료 시 None
    cache.delete('my_key')
    cache.clear()
"""

import logging
import time

logger = logging.getLogger(__name__)


class TTLCache:
    """TTL(Time-To-Live) 기반 범용 인메모리 캐시.

    스레드 안전하지 않으므로 멀티프로세스 환경에서는 Redis 등을 사용할 것.

    Args:
        ttl_seconds: 기본 캐시 유효 시간 (초). get() 호출 시 ttl 파라미터로 오버라이드 가능.
        max_size: 최대 캐시 항목 수. 초과 시 가장 오래된 항목 제거 (0=무제한).
    """

    def __init__(self, ttl_seconds: int = 300, max_size: int = 0):
        self._ttl = ttl_seconds
        self._max_size = max_size
        self._store: dict = {}   # key → (value, stored_at, ttl)

    # ── public API ────────────────────────────────────────────

    def get(self, key: str, ttl: int = None) -> object:
        """캐시에서 값을 가져온다. 만료 또는 없으면 None 반환.

        Args:
            key: 캐시 키
            ttl: 이 조회에만 적용할 TTL (초). None이면 기본 TTL 사용.
        """
        entry = self._store.get(key)
        if entry is None:
            return None

        value, stored_at, entry_ttl = entry
        effective_ttl = ttl if ttl is not None else entry_ttl
        if time.time() - stored_at > effective_ttl:
            # 만료된 항목 제거
            del self._store[key]
            logger.debug("Cache MISS (expired): key=%s", key)
            return None

        logger.debug("Cache HIT: key=%s", key)
        return value

    def set(self, key: str, value: object, ttl: int = None):
        """캐시에 값을 저장한다.

        Args:
            key: 캐시 키
            value: 저장할 값
            ttl: 이 항목의 TTL (초). None이면 기본 TTL 사용.
        """
        entry_ttl = ttl if ttl is not None else self._ttl

        # max_size 초과 시 가장 오래된 항목 제거
        if self._max_size > 0 and len(self._store) >= self._max_size and key not in self._store:
            oldest_key = min(self._store, key=lambda k: self._store[k][1])
            del self._store[oldest_key]
            logger.debug("Cache evicted (max_size=%d): key=%s", self._max_size, oldest_key)

        self._store[key] = (value, time.time(), entry_ttl)
        logger.debug("Cache SET: key=%s ttl=%ds", key, entry_ttl)

    def delete(self, key: str) -> bool:
        """캐시 항목을 삭제한다. 삭제 성공 시 True, 없으면 False."""
        if key in self._store:
            del self._store[key]
            logger.debug("Cache DELETE: key=%s", key)
            return True
        return False

    def clear(self):
        """전체 캐시를 비운다."""
        count = len(self._store)
        self._store.clear()
        logger.debug("Cache CLEAR: removed %d entries", count)

    def is_valid(self, key: str) -> bool:
        """캐시 항목이 유효한지 확인한다 (존재하고 만료되지 않음)."""
        return self.get(key) is not None

    def size(self) -> int:
        """현재 캐시에 저장된 항목 수 (만료 항목 포함)."""
        return len(self._store)

    def purge_expired(self) -> int:
        """만료된 항목을 모두 제거하고 제거된 수를 반환한다."""
        now = time.time()
        expired = [
            k for k, (_, stored_at, ttl) in self._store.items()
            if now - stored_at > ttl
        ]
        for k in expired:
            del self._store[k]
        if expired:
            logger.debug("Cache purge: removed %d expired entries", len(expired))
        return len(expired)

    def keys(self) -> list:
        """유효한 캐시 키 목록을 반환한다."""
        now = time.time()
        return [
            k for k, (_, stored_at, ttl) in self._store.items()
            if now - stored_at <= ttl
        ]

    def __len__(self) -> int:
        return self.size()

    def __contains__(self, key: str) -> bool:
        return self.is_valid(key)


# ──────────────────────────────────────────────────────────
# 모듈별 싱글톤 캐시 인스턴스
# ──────────────────────────────────────────────────────────

# 환율 캐시: 1시간 TTL
fx_cache = TTLCache(ttl_seconds=3600)

# 번역 캐시: 24시간 TTL
translate_cache = TTLCache(ttl_seconds=86400)

# 재고 조회 캐시: 30분 TTL
inventory_cache = TTLCache(ttl_seconds=1800)
