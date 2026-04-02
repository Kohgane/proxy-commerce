"""tests/test_api_keys.py — Tests for APIKeyManager and TokenBucketRateLimiter."""

import os
import re
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


# ──────────────────────────────────────────────────────────
# TestAPIKeyManager
# ──────────────────────────────────────────────────────────

class TestAPIKeyManager:

    @pytest.fixture
    def manager(self):
        from src.auth.api_key_manager import APIKeyManager
        return APIKeyManager()

    def test_generate_key_format(self, manager):
        record = manager.generate_key()
        key = record['key']
        assert re.match(r'^pk_[0-9a-f]{32}$', key), f"Key format invalid: {key}"

    def test_generate_key_custom_prefix(self, manager):
        record = manager.generate_key(prefix='sk')
        assert record['key'].startswith('sk_')
        assert record['prefix'] == 'sk'

    def test_generate_key_with_scopes(self, manager):
        scopes = ['read:orders', 'write:products']
        record = manager.generate_key(scopes=scopes)
        assert record['scopes'] == scopes

    def test_validate_key_valid(self, manager):
        record = manager.generate_key()
        result = manager.validate_key(record['key'])
        assert result['valid'] is True
        assert result['expired'] is False

    def test_validate_key_invalid_format(self, manager):
        result = manager.validate_key('badkey')
        assert result['valid'] is False

    def test_validate_key_unknown_key(self, manager):
        # Valid format but not in store
        result = manager.validate_key('pk_' + 'a' * 32)
        assert result['valid'] is False

    def test_revoke_key(self, manager):
        record = manager.generate_key()
        key_id = record['key_id']
        assert manager.revoke_key(key_id) is True
        result = manager.validate_key(record['key'])
        assert result['valid'] is False

    def test_revoke_nonexistent_key(self, manager):
        assert manager.revoke_key('nonexistent_id') is False

    def test_list_keys_excludes_revoked(self, manager):
        r1 = manager.generate_key(prefix='pk')
        r2 = manager.generate_key(prefix='sk')
        manager.revoke_key(r1['key_id'])
        keys = manager.list_keys()
        key_ids = [k['key_id'] for k in keys]
        assert r1['key_id'] not in key_ids
        assert r2['key_id'] in key_ids


# ──────────────────────────────────────────────────────────
# TestTokenBucketRateLimiter
# ──────────────────────────────────────────────────────────

class TestTokenBucketRateLimiter:

    @pytest.fixture
    def limiter(self):
        from src.auth.rate_limiter import TokenBucketRateLimiter
        return TokenBucketRateLimiter(capacity=5, refill_rate=1.0)

    def test_consume_within_capacity_returns_true(self, limiter):
        for _ in range(5):
            assert limiter.consume('user1') is True

    def test_consume_over_capacity_returns_false(self, limiter):
        for _ in range(5):
            limiter.consume('user2')
        assert limiter.consume('user2') is False

    def test_get_remaining(self, limiter):
        limiter.consume('user3')
        limiter.consume('user3')
        remaining = limiter.get_remaining('user3')
        assert remaining == pytest.approx(3.0, abs=0.1)

    def test_reset(self, limiter):
        for _ in range(5):
            limiter.consume('user4')
        limiter.reset('user4')
        assert limiter.get_remaining('user4') == pytest.approx(5.0, abs=0.1)

    def test_different_keys_are_independent(self, limiter):
        for _ in range(5):
            limiter.consume('keyA')
        # keyB should still have full capacity
        assert limiter.consume('keyB') is True

    def test_refill_over_time(self, limiter):
        # Use a fast refill_rate limiter
        from src.auth.rate_limiter import TokenBucketRateLimiter
        fast = TokenBucketRateLimiter(capacity=2, refill_rate=10.0)
        fast.consume('u', 2)
        assert fast.consume('u') is False
        time.sleep(0.2)
        assert fast.consume('u') is True
