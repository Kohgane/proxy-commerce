"""tests/test_ai_listing_budget_guard.py — 한도 초과 시 거절 테스트 (Phase 149)."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestDailyLimitGuard:
    def test_within_limit_returns_true(self):
        from src.ai_listing.routes import _check_daily_limit, _daily_usage
        _daily_usage.clear()
        # 한도 내에서는 True
        assert _check_daily_limit("user_a") is True

    def test_exceeds_limit_returns_false(self, monkeypatch):
        from src.ai_listing import routes as r
        r._daily_usage.clear()
        monkeypatch.setattr(r, "_MAX_DAILY_PER_USER", 2)

        user_id = "user_limit_test"
        assert r._check_daily_limit(user_id) is True   # 1번
        assert r._check_daily_limit(user_id) is True   # 2번
        assert r._check_daily_limit(user_id) is False  # 3번 → 초과

    def test_different_users_independent(self):
        from src.ai_listing.routes import _check_daily_limit, _daily_usage
        _daily_usage.clear()
        # 서로 다른 사용자는 독립적
        assert _check_daily_limit("user_x") is True
        assert _check_daily_limit("user_y") is True

    def test_api_returns_429_when_limit_exceeded(self, monkeypatch):
        """한도 초과 시 /api/ai-listing/analyze → 429 반환."""
        os.environ.setdefault("SECRET_KEY", "test-secret")
        os.environ["AI_LISTING_ENABLED"] = "1"
        os.environ["AI_LISTING_VISION_PROVIDER"] = "mock"

        import json
        from src.ai_listing import routes as r
        r._daily_usage.clear()
        monkeypatch.setattr(r, "_MAX_DAILY_PER_USER", 0)  # 한도 0 → 즉시 초과

        from src.order_webhook import app as flask_app
        flask_app.config["TESTING"] = True
        with flask_app.test_client() as client:
            resp = client.post(
                "/api/ai-listing/analyze",
                data=json.dumps({"image_url": "https://example.com/img.jpg"}),
                content_type="application/json",
            )
            assert resp.status_code == 429
            data = json.loads(resp.data)
            assert data.get("ok") is False


class TestBudgetGuardIntegration:
    def test_budget_exceeded_returns_mock_result(self, monkeypatch):
        """BudgetGuard 초과 시 analyzer가 mock 결과를 반환한다."""
        from src.ai import budget as budget_mod

        # BudgetGuard.check()가 BudgetExceededError를 raise하도록 mock
        class FakeBudgetGuard:
            def check(self):
                raise budget_mod.BudgetExceededError({"limit_usd": "1.00", "used_usd": "1.50"})
            def summary(self):
                return {"pct": 110.0}

        monkeypatch.setenv("AI_LISTING_VISION_PROVIDER", "openai")
        monkeypatch.setenv("OPENAI_API_KEY", "fake-key")
        monkeypatch.setattr(budget_mod, "BudgetGuard", FakeBudgetGuard)

        from src.ai_listing.analyzer import analyze_image, _analysis_cache
        _analysis_cache.clear()

        result = analyze_image(image_url="https://example.com/budget_test.jpg", force_refresh=True)
        # 예산 초과 시 mock 결과가 반환되어야 함
        assert isinstance(result, dict)
        assert result.get("_budget_exceeded") is True or result.get("_mock") is True


class TestFeatureToggle:
    def test_disabled_api_returns_403(self, monkeypatch):
        """AI_LISTING_ENABLED=0 일 때 403 반환."""
        import json
        monkeypatch.setenv("AI_LISTING_ENABLED", "0")

        from src.ai_listing import routes as r
        monkeypatch.setattr(r, "_ENABLED", False)

        os.environ.setdefault("SECRET_KEY", "test-secret")
        from src.order_webhook import app as flask_app
        flask_app.config["TESTING"] = True
        with flask_app.test_client() as client:
            resp = client.post(
                "/api/ai-listing/analyze",
                data=json.dumps({"image_url": "https://example.com/img.jpg"}),
                content_type="application/json",
            )
            assert resp.status_code == 403
            data = json.loads(resp.data)
            assert data.get("ok") is False
