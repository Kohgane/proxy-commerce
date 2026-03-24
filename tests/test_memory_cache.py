"""tests/test_memory_cache.py — 인메모리 캐시 테스트.

MemoryCache TTL, LRU eviction, 스레드 안전성, 통계 기능을 검증한다.
"""

import os
import sys
import threading
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.cache.memory_cache import MemoryCache
from src.cache.api_cache import ApiCache, cached, _make_cache_key


# ──────────────────────────────────────────────────────────
# MemoryCache 기본 동작 테스트
# ──────────────────────────────────────────────────────────

class TestMemoryCacheBasic:
    def test_set_and_get(self):
        """set 후 get으로 값을 가져올 수 있다."""
        cache = MemoryCache(ttl_seconds=300)
        cache.set("key1", {"data": 42})
        result = cache.get("key1")
        assert result == {"data": 42}

    def test_get_missing_key_returns_none(self):
        """없는 키는 None을 반환한다."""
        cache = MemoryCache()
        assert cache.get("nonexistent") is None

    def test_ttl_expiry(self):
        """TTL 만료 후 None을 반환한다."""
        cache = MemoryCache(ttl_seconds=1)
        cache.set("expire_key", "value")
        assert cache.get("expire_key") is not None
        time.sleep(1.1)
        assert cache.get("expire_key") is None

    def test_delete(self):
        """delete()로 항목을 제거할 수 있다."""
        cache = MemoryCache()
        cache.set("del_key", "value")
        assert cache.delete("del_key") is True
        assert cache.get("del_key") is None

    def test_delete_nonexistent_returns_false(self):
        """없는 키 삭제 시 False를 반환한다."""
        cache = MemoryCache()
        assert cache.delete("ghost_key") is False

    def test_clear(self):
        """clear()로 전체 캐시를 비울 수 있다."""
        cache = MemoryCache()
        cache.set("a", 1)
        cache.set("b", 2)
        cache.clear()
        assert cache.size() == 0

    def test_contains(self):
        """in 연산자로 유효한 키를 확인할 수 있다."""
        cache = MemoryCache(ttl_seconds=300)
        cache.set("exists", True)
        assert "exists" in cache
        assert "not_here" not in cache


# ──────────────────────────────────────────────────────────
# LRU Eviction 테스트
# ──────────────────────────────────────────────────────────

class TestMemoryCacheEviction:
    def test_lru_eviction_on_max_size(self):
        """max_size 초과 시 오래된 항목이 제거된다."""
        cache = MemoryCache(ttl_seconds=300, max_size=3)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        # 4번째 추가 시 "a"가 제거됨
        cache.set("d", 4)
        assert cache.size() == 3
        assert cache.stats.evictions == 1

    def test_updating_existing_key_no_eviction(self):
        """기존 키 업데이트는 eviction을 발생시키지 않는다."""
        cache = MemoryCache(ttl_seconds=300, max_size=2)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("a", 99)  # 기존 키 업데이트
        assert cache.stats.evictions == 0
        assert cache.get("a") == 99


# ──────────────────────────────────────────────────────────
# 통계 테스트
# ──────────────────────────────────────────────────────────

class TestCacheStats:
    def test_hit_rate_calculation(self):
        """hit_rate가 올바르게 계산된다."""
        cache = MemoryCache(ttl_seconds=300)
        cache.set("k", "v")
        cache.get("k")   # hit
        cache.get("k")   # hit
        cache.get("x")   # miss
        assert cache.stats.hits == 2
        assert cache.stats.misses == 1
        assert cache.stats.hit_rate == pytest.approx(2 / 3, rel=0.01)

    def test_stats_reset(self):
        """stats.reset()으로 통계를 초기화한다."""
        cache = MemoryCache(ttl_seconds=300)
        cache.set("k", "v")
        cache.get("k")
        cache.stats.reset()
        assert cache.stats.hits == 0
        assert cache.stats.misses == 0


# ──────────────────────────────────────────────────────────
# 스레드 안전성 테스트
# ──────────────────────────────────────────────────────────

class TestMemoryCacheThreadSafety:
    def test_concurrent_set_and_get(self):
        """멀티스레드 환경에서 데이터 일관성이 유지된다."""
        cache = MemoryCache(ttl_seconds=60, max_size=1000)
        errors = []

        def writer(n):
            try:
                for i in range(50):
                    cache.set(f"key_{n}_{i}", n * 100 + i)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []


# ──────────────────────────────────────────────────────────
# ApiCache 및 @cached 데코레이터 테스트
# ──────────────────────────────────────────────────────────

class TestApiCache:
    def test_cached_decorator_returns_cached_value(self):
        """@cached 데코레이터가 두 번째 호출에 캐시 값을 반환한다."""
        call_count = {"n": 0}

        @cached(ttl=300, key_prefix="test")
        def expensive_call(x):
            call_count["n"] += 1
            return x * 2

        result1 = expensive_call(5)
        result2 = expensive_call(5)
        assert result1 == result2 == 10
        assert call_count["n"] == 1  # 실제 호출은 1번

    def test_different_args_different_cache_keys(self):
        """인자가 다르면 별도 캐시 항목으로 저장된다."""
        call_count = {"n": 0}

        @cached(ttl=300, key_prefix="test2")
        def compute(x):
            call_count["n"] += 1
            return x ** 2

        compute(3)
        compute(4)
        assert call_count["n"] == 2

    def test_make_cache_key_deterministic(self):
        """동일 인자에 대한 캐시 키는 항상 같다."""
        key1 = _make_cache_key("pfx", "func", (1, 2), {"a": "b"})
        key2 = _make_cache_key("pfx", "func", (1, 2), {"a": "b"})
        assert key1 == key2

    def test_api_cache_get_or_fetch(self):
        """ApiCache.get_or_fetch가 캐시 미스 시 fetch_fn을 호출한다."""
        api_cache = ApiCache(name="shopify", ttl=300)
        call_count = {"n": 0}

        def fetch():
            call_count["n"] += 1
            return [{"id": 1}]

        result1 = api_cache.get_or_fetch("products", fetch)
        result2 = api_cache.get_or_fetch("products", fetch)

        assert result1 == result2 == [{"id": 1}]
        assert call_count["n"] == 1

    def test_api_cache_invalidate(self):
        """invalidate()로 캐시 항목을 무효화한다."""
        api_cache = ApiCache(name="woo", ttl=300)
        call_count = {"n": 0}

        def fetch():
            call_count["n"] += 1
            return "data"

        api_cache.get_or_fetch("orders", fetch)
        api_cache.invalidate("orders")
        api_cache.get_or_fetch("orders", fetch)

        assert call_count["n"] == 2
