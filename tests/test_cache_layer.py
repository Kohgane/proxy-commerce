"""tests/test_cache_layer.py — Phase 65: 캐시 계층 테스트."""
from __future__ import annotations

import time

import pytest

from src.cache_layer import (
    L1Cache, L2Cache, CacheManager, CacheInvalidator,
    CacheWarmer, CacheStats, cached,
)


class TestL1Cache:
    def test_set_and_get(self):
        cache = L1Cache()
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_miss_returns_none(self):
        cache = L1Cache()
        assert cache.get("missing") is None

    def test_delete(self):
        cache = L1Cache()
        cache.set("k", "v")
        cache.delete("k")
        assert cache.get("k") is None

    def test_clear(self):
        cache = L1Cache()
        cache.set("a", 1)
        cache.set("b", 2)
        cache.clear()
        assert cache.get("a") is None

    def test_lru_eviction(self):
        cache = L1Cache(maxsize=2)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)  # should evict "a"
        assert cache.get("a") is None
        assert cache.get("b") == 2

    def test_ttl_expiry(self):
        cache = L1Cache()
        cache.set("expire_key", "val", ttl=1)
        assert cache.get("expire_key") == "val"
        time.sleep(1.1)
        assert cache.get("expire_key") is None

    def test_keys(self):
        cache = L1Cache()
        cache.set("x", 1)
        cache.set("y", 2)
        assert "x" in cache.keys()


class TestCacheManager:
    def test_set_and_get(self):
        manager = CacheManager()
        manager.set("key", "value")
        assert manager.get("key") == "value"

    def test_miss_returns_none(self):
        manager = CacheManager()
        assert manager.get("nonexistent") is None

    def test_delete(self):
        manager = CacheManager()
        manager.set("k", "v")
        manager.delete("k")
        assert manager.get("k") is None

    def test_l2_promotion(self):
        l1 = L1Cache()
        l2 = L2Cache(cache_dir="./data/cache_test")
        manager = CacheManager(l1=l1, l2=l2)
        l2.set("promoted", "from_l2")
        val = manager.get("promoted")
        assert val == "from_l2"
        assert l1.get("promoted") == "from_l2"
        # cleanup
        l2.clear()


class TestCacheInvalidator:
    def test_invalidate_by_pattern(self):
        manager = CacheManager()
        manager.set("user:1", "A")
        manager.set("user:2", "B")
        manager.set("product:1", "C")
        invalidator = CacheInvalidator(manager)
        count = invalidator.invalidate_by_pattern(r"^user:")
        assert count == 2
        assert manager.get("product:1") == "C"

    def test_invalidate_by_tag(self):
        manager = CacheManager()
        manager.set("item1", "v1")
        invalidator = CacheInvalidator(manager)
        invalidator.tag_key("item1", ["tag_a"])
        count = invalidator.invalidate_by_tag("tag_a")
        assert count == 1


class TestCacheWarmer:
    def test_warm(self):
        manager = CacheManager()
        warmer = CacheWarmer(manager)
        results = warmer.warm(lambda k: f"data_{k}", ["k1", "k2", "k3"])
        assert len(results["warmed"]) == 3
        assert manager.get("k1") == "data_k1"


class TestCacheStats:
    def test_record_hit(self):
        stats = CacheStats()
        stats.record_hit(5.0)
        s = stats.get_stats()
        assert s["hits"] == 1
        assert s["avg_hit_ms"] == 5.0

    def test_record_miss(self):
        stats = CacheStats()
        stats.record_miss(10.0)
        s = stats.get_stats()
        assert s["misses"] == 1

    def test_hit_rate(self):
        stats = CacheStats()
        stats.record_hit(1.0)
        stats.record_hit(1.0)
        stats.record_miss(1.0)
        s = stats.get_stats()
        assert abs(s["hit_rate"] - 2/3) < 0.01

    def test_reset(self):
        stats = CacheStats()
        stats.record_hit()
        stats.reset()
        assert stats.get_stats()["hits"] == 0
