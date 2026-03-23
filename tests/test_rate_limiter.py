"""tests/test_rate_limiter.py — 레이트 리미팅 미들웨어 테스트.

AdvancedRateLimiter 슬라이딩 윈도우 카운터의 허용/차단 동작을 검증한다.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


# ──────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────

@pytest.fixture
def limiter():
    """테스트용 AdvancedRateLimiter — 소규모 제한으로 설정."""
    from src.middleware.rate_limiter import AdvancedRateLimiter
    rl = AdvancedRateLimiter()
    # 테스트용으로 제한값을 작게 설정
    rl._limits = {
        "webhook": (3, 60),
        "bot": (2, 60),
        "default": (5, 60),
    }
    return rl


# ──────────────────────────────────────────────────────────
# _parse_limit 테스트
# ──────────────────────────────────────────────────────────

class TestParseLimitString:
    def test_parse_per_minute(self):
        from src.middleware.rate_limiter import _parse_limit
        count, window = _parse_limit("60/minute")
        assert count == 60
        assert window == 60

    def test_parse_per_second(self):
        from src.middleware.rate_limiter import _parse_limit
        count, window = _parse_limit("10/second")
        assert count == 10
        assert window == 1

    def test_parse_per_hour(self):
        from src.middleware.rate_limiter import _parse_limit
        count, window = _parse_limit("1000/hour")
        assert count == 1000
        assert window == 3600

    def test_parse_invalid_fallback(self):
        from src.middleware.rate_limiter import _parse_limit
        count, window = _parse_limit("invalid_string")
        assert count == 60
        assert window == 60


# ──────────────────────────────────────────────────────────
# AdvancedRateLimiter 테스트
# ──────────────────────────────────────────────────────────

class TestAdvancedRateLimiter:
    def test_initial_requests_allowed(self, limiter):
        """제한 내의 요청은 모두 허용된다."""
        for _ in range(3):
            allowed, _ = limiter.check("192.168.1.1", "/webhook/shopify/order")
            assert allowed is True

    def test_exceeds_limit_returns_false(self, limiter):
        """제한을 초과하면 False와 retry_after를 반환한다."""
        ip = "192.168.1.100"
        for _ in range(3):
            limiter.check(ip, "/webhook/shopify/order")
        allowed, retry_after = limiter.check(ip, "/webhook/shopify/order")
        assert allowed is False
        assert retry_after is not None and retry_after > 0

    def test_health_endpoint_always_allowed(self, limiter):
        """헬스체크 엔드포인트는 제한 없이 허용된다."""
        ip = "10.0.0.1"
        for _ in range(100):
            allowed, retry_after = limiter.check(ip, "/health")
            assert allowed is True
            assert retry_after is None

    def test_different_ips_independent(self, limiter):
        """다른 IP의 요청은 독립적으로 카운트된다."""
        for _ in range(3):
            limiter.check("10.0.0.1", "/webhook/shopify/order")
        # 다른 IP는 영향 없음
        allowed, _ = limiter.check("10.0.0.2", "/webhook/shopify/order")
        assert allowed is True

    def test_bot_endpoint_uses_bot_limit(self, limiter):
        """봇 엔드포인트는 bot 제한을 사용한다."""
        ip = "192.168.1.200"
        for _ in range(2):
            allowed, _ = limiter.check(ip, "/webhook/telegram")
            assert allowed is True
        # 3번째는 차단
        allowed, _ = limiter.check(ip, "/webhook/telegram")
        assert allowed is False

    def test_reset_clears_counter(self, limiter):
        """reset() 호출 시 카운터가 초기화된다."""
        ip = "192.168.1.50"
        for _ in range(3):
            limiter.check(ip, "/webhook/shopify/order")
        # 초과 상태
        allowed, _ = limiter.check(ip, "/webhook/shopify/order")
        assert allowed is False

        limiter.reset(ip)
        # 리셋 후 허용
        allowed, _ = limiter.check(ip, "/webhook/shopify/order")
        assert allowed is True

    def test_disabled_limiter_always_allows(self, monkeypatch):
        """RATE_LIMIT_ENABLED=0이면 모든 요청을 허용한다."""
        from src.middleware.rate_limiter import AdvancedRateLimiter
        rl = AdvancedRateLimiter()
        rl._enabled = False
        for _ in range(1000):
            allowed, retry_after = rl.check("any_ip", "/webhook/shopify/order")
            assert allowed is True
            assert retry_after is None
