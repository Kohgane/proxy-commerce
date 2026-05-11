"""tests/test_product_subscriptions.py — 정기구독 상품 테스트 (Phase 148)."""
from __future__ import annotations

import os
import pytest
from datetime import datetime, timedelta, timezone


class TestProductSubscriptionManager:
    def _mgr(self, tmp_path):
        from src.product_subscriptions.subscription_products import ProductSubscriptionManager
        return ProductSubscriptionManager(path=str(tmp_path / "subs.jsonl"))

    def _make_sub(self, user_id="user1", product_id="prod1"):
        from src.product_subscriptions.subscription_products import (
            ProductSubscription,
            SubscriptionCycle,
        )
        return ProductSubscription(
            user_id=user_id,
            product_id=product_id,
            product_name="테스트 상품",
            cycle=SubscriptionCycle.MONTHLY,
            unit_price=10000,
        )

    def test_subscribe_and_list(self, tmp_path):
        mgr = self._mgr(tmp_path)
        sub = self._make_sub()
        mgr.subscribe(sub)
        active = mgr.list_active()
        assert len(active) == 1
        assert active[0].user_id == "user1"

    def test_cancel(self, tmp_path):
        from src.product_subscriptions.subscription_products import SubscriptionStatus
        mgr = self._mgr(tmp_path)
        sub = self._make_sub()
        mgr.subscribe(sub)
        ok = mgr.cancel(sub.subscription_id)
        assert ok is True
        active = mgr.list_active()
        assert len(active) == 0

    def test_pause_and_resume(self, tmp_path):
        from src.product_subscriptions.subscription_products import SubscriptionStatus
        mgr = self._mgr(tmp_path)
        sub = self._make_sub()
        mgr.subscribe(sub)
        ok_pause = mgr.pause(sub.subscription_id)
        assert ok_pause is True
        active = mgr.list_active()
        assert len(active) == 0  # paused = not active
        ok_resume = mgr.resume(sub.subscription_id)
        assert ok_resume is True
        active = mgr.list_active()
        assert len(active) == 1

    def test_skip_next_advances_billing_date(self, tmp_path):
        from src.product_subscriptions.subscription_products import (
            ProductSubscription,
            SubscriptionCycle,
        )
        mgr = self._mgr(tmp_path)
        next_dt = datetime.now(timezone.utc) + timedelta(days=28)
        sub = ProductSubscription(
            user_id="u1",
            product_id="p1",
            cycle=SubscriptionCycle.MONTHLY,
            next_billing_at=next_dt.isoformat(),
        )
        mgr.subscribe(sub)
        ok = mgr.skip_next(sub.subscription_id)
        assert ok is True
        updated = mgr.list_for_user("u1")[0]
        updated_dt = datetime.fromisoformat(updated.next_billing_at)
        expected_dt = next_dt + timedelta(days=28)
        diff = abs((updated_dt - expected_dt).total_seconds())
        assert diff < 2, f"skip_next 후 다음 결제일이 예상과 다릅니다: {updated_dt} vs {expected_dt}"
        assert updated.skip_count == 1

    def test_list_for_user(self, tmp_path):
        mgr = self._mgr(tmp_path)
        mgr.subscribe(self._make_sub("alice", "p1"))
        mgr.subscribe(self._make_sub("alice", "p2"))
        mgr.subscribe(self._make_sub("bob", "p1"))
        assert len(mgr.list_for_user("alice")) == 2
        assert len(mgr.list_for_user("bob")) == 1

    def test_process_billing_mock(self, tmp_path):
        mgr = self._mgr(tmp_path)
        sub = self._make_sub()
        mgr.subscribe(sub)
        result = mgr.process_billing_mock(sub.subscription_id)
        assert result["ok"] is True
        assert result["provider"] == "mock"

    def test_upcoming_billing(self, tmp_path):
        from src.product_subscriptions.subscription_products import (
            ProductSubscription,
            SubscriptionCycle,
        )
        mgr = self._mgr(tmp_path)
        soon = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
        later = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        mgr.subscribe(ProductSubscription(user_id="u1", product_id="p1", cycle=SubscriptionCycle.MONTHLY, next_billing_at=soon))
        mgr.subscribe(ProductSubscription(user_id="u2", product_id="p2", cycle=SubscriptionCycle.MONTHLY, next_billing_at=later))
        upcoming = mgr.upcoming_billing(days_ahead=7)
        assert len(upcoming) == 1
        assert upcoming[0].user_id == "u1"

    def test_summary_structure(self, tmp_path):
        mgr = self._mgr(tmp_path)
        summary = mgr.summary()
        assert "enabled" in summary
        assert "active_count" in summary
        assert "billed_this_week" in summary
        assert "failed_count" in summary
        assert "pg_provider" in summary

    def test_enabled_env(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SUBSCRIPTION_ENABLED", "0")
        from src.product_subscriptions.subscription_products import ProductSubscriptionManager
        mgr = ProductSubscriptionManager(path=str(tmp_path / "subs2.jsonl"))
        assert mgr.enabled is False

    def test_cycle_days(self):
        from src.product_subscriptions.subscription_products import SubscriptionCycle
        assert SubscriptionCycle.WEEKLY.days == 7
        assert SubscriptionCycle.BIWEEKLY.days == 14
        assert SubscriptionCycle.MONTHLY.days == 28
        assert SubscriptionCycle.BIMONTHLY.days == 56


# ---------------------------------------------------------------------------
# Seller 라우트 테스트
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def app():
    os.environ.setdefault("TESTING", "1")
    os.environ.setdefault("SECRET_KEY", "test-secret")
    import src.order_webhook as wh
    wh.app.config["TESTING"] = True
    return wh.app


@pytest.fixture(scope="module")
def client(app):
    with app.test_client() as c:
        yield c


def test_seller_subscriptions_route_not_404(client):
    resp = client.get("/seller/subscriptions")
    assert resp.status_code != 404


def test_me_subscriptions_route_not_404(client):
    resp = client.get("/seller/me/subscriptions")
    assert resp.status_code != 404


def test_seller_subscriptions_in_sidebar(client):
    html = client.get("/seller/dashboard").get_data(as_text=True)
    assert "/seller/subscriptions" in html
