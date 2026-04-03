"""tests/test_rate_limiting.py — Phase 62: 레이트 리미팅 테스트."""
from __future__ import annotations

import time

import pytest

from src.rate_limiting import (
    RateLimiter, SlidingWindowLimiter, TokenBucketLimiter,
    LeakyBucketLimiter, RateLimitPolicy, RateLimitDashboard,
)


class TestSlidingWindowLimiter:
    def test_allows_within_limit(self):
        limiter = SlidingWindowLimiter()
        for _ in range(5):
            assert limiter.check("key1", limit=10, window=60) is True

    def test_blocks_when_exceeded(self):
        limiter = SlidingWindowLimiter()
        for _ in range(5):
            limiter.check("key2", limit=5, window=60)
        assert limiter.check("key2", limit=5, window=60) is False

    def test_get_usage(self):
        limiter = SlidingWindowLimiter()
        limiter.check("key3", limit=10, window=60)
        usage = limiter.get_usage("key3")
        assert usage["count"] >= 1


class TestTokenBucketLimiter:
    def test_allows_within_capacity(self):
        limiter = TokenBucketLimiter(capacity=10, refill_rate=1.0)
        assert limiter.check("key", limit=10, window=60) is True

    def test_get_usage(self):
        limiter = TokenBucketLimiter(capacity=10, refill_rate=1.0)
        limiter.check("key", limit=10, window=60)
        usage = limiter.get_usage("key")
        assert "tokens_remaining" in usage


class TestLeakyBucketLimiter:
    def test_allows_within_capacity(self):
        limiter = LeakyBucketLimiter(capacity=10, leak_rate=1.0)
        assert limiter.check("key", limit=10, window=60) is True

    def test_blocks_when_full(self):
        limiter = LeakyBucketLimiter(capacity=3, leak_rate=0.0)
        for _ in range(3):
            limiter.check("key", limit=3, window=60)
        assert limiter.check("key", limit=3, window=60) is False


class TestRateLimitPolicy:
    def test_set_and_get_policy(self):
        policy = RateLimitPolicy()
        p = policy.set_policy("/api/test", limit=100, window=60)
        assert p["endpoint"] == "/api/test"
        assert p["limit"] == 100

    def test_list_policies(self):
        policy = RateLimitPolicy()
        policy.set_policy("/a", 10, 60)
        policy.set_policy("/b", 20, 60)
        policies = policy.list_policies()
        assert len(policies) == 2

    def test_get_nonexistent_policy(self):
        policy = RateLimitPolicy()
        assert policy.get_policy("/missing") is None

    def test_delete_policy(self):
        policy = RateLimitPolicy()
        policy.set_policy("/del", 10, 60)
        policy.delete_policy("/del")
        assert policy.get_policy("/del") is None


class TestRateLimitDashboard:
    def test_get_stats(self):
        limiter = SlidingWindowLimiter()
        policy = RateLimitPolicy()
        policy.set_policy("/test", 100, 60)
        dashboard = RateLimitDashboard(limiter=limiter, policy=policy)
        stats = dashboard.get_stats()
        assert "total_policies" in stats
        assert stats["total_policies"] == 1
