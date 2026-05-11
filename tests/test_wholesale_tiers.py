"""tests/test_wholesale_tiers.py — B2B 도매 모드 테스트 (Phase 148)."""
from __future__ import annotations

import os
import tempfile
import pytest


# ---------------------------------------------------------------------------
# WholesaleTierManager
# ---------------------------------------------------------------------------

class TestWholesaleTierManager:
    def _mgr(self):
        from src.wholesale.tier_manager import WholesaleTierManager
        return WholesaleTierManager()

    def test_list_tiers_returns_three(self):
        mgr = self._mgr()
        tiers = mgr.list_tiers()
        assert len(tiers) == 3

    def test_tier_levels(self):
        mgr = self._mgr()
        levels = {t.level.value for t in mgr.list_tiers()}
        assert levels == {"retail", "wholesale", "vip"}

    def test_retail_multiplier(self):
        mgr = self._mgr()
        assert mgr.calculate_price(10000, "retail", 1) == 10000

    def test_wholesale_10_49_multiplier(self):
        """10~49개 도매: × 0.9"""
        mgr = self._mgr()
        assert mgr.calculate_price(10000, "wholesale", 10) == 9000
        assert mgr.calculate_price(10000, "wholesale", 49) == 9000

    def test_wholesale_50_plus_multiplier(self):
        """50개+ 도매: × 0.8"""
        mgr = self._mgr()
        assert mgr.calculate_price(10000, "wholesale", 50) == 8000
        assert mgr.calculate_price(10000, "wholesale", 100) == 8000

    def test_vip_multiplier(self):
        """VIP: × 0.75"""
        mgr = self._mgr()
        assert mgr.calculate_price(10000, "vip", 1) == 7500

    def test_moq_check_wholesale_fail(self):
        """도매 MOQ(10) 미달 시 ValueError 발생."""
        mgr = self._mgr()
        with pytest.raises(ValueError, match="MOQ"):
            mgr.calculate_price(10000, "wholesale", 9)

    def test_moq_check_wholesale_pass(self):
        mgr = self._mgr()
        result = mgr.calculate_price(10000, "wholesale", 10)
        assert result == 9000

    def test_moq_ok(self):
        mgr = self._mgr()
        assert mgr.moq_ok("wholesale", 10) is True
        assert mgr.moq_ok("wholesale", 9) is False
        assert mgr.moq_ok("retail", 1) is True

    def test_summary_structure(self):
        mgr = self._mgr()
        summary = mgr.summary()
        assert "enabled" in summary
        assert "tier_count" in summary
        assert "tiers" in summary
        assert summary["tier_count"] == 3

    def test_enabled_env(self, monkeypatch):
        monkeypatch.setenv("WHOLESALE_ENABLED", "0")
        from src.wholesale.tier_manager import WholesaleTierManager
        mgr = WholesaleTierManager()
        assert mgr.enabled is False

    def test_get_tier_by_string(self):
        mgr = self._mgr()
        t = mgr.get_tier("wholesale")
        assert t is not None
        assert t.moq == 10


# ---------------------------------------------------------------------------
# WholesaleApplicationManager
# ---------------------------------------------------------------------------

class TestWholesaleApplicationManager:
    def _mgr(self, tmp_path):
        from src.wholesale.application_manager import WholesaleApplicationManager
        return WholesaleApplicationManager(path=str(tmp_path / "apps.jsonl"))

    def test_submit_and_list(self, tmp_path):
        from src.wholesale.application_manager import WholesaleApplication, ApplicationStatus
        mgr = self._mgr(tmp_path)
        app = WholesaleApplication(
            user_id="user1",
            business_name="테스트 주식회사",
            business_reg_number="123-45-67890",
            contact_email="test@company.com",
        )
        mgr.submit(app)
        pending = mgr.list_applications(ApplicationStatus.PENDING)
        assert len(pending) == 1
        assert pending[0].business_name == "테스트 주식회사"

    def test_approve(self, tmp_path):
        from src.wholesale.application_manager import WholesaleApplication, ApplicationStatus
        mgr = self._mgr(tmp_path)
        app = WholesaleApplication(user_id="user2", business_name="승인테스트")
        mgr.submit(app)
        ok = mgr.approve(app.application_id, reviewer_note="OK")
        assert ok is True
        approved = mgr.list_applications(ApplicationStatus.APPROVED)
        assert len(approved) == 1

    def test_reject(self, tmp_path):
        from src.wholesale.application_manager import WholesaleApplication, ApplicationStatus
        mgr = self._mgr(tmp_path)
        app = WholesaleApplication(user_id="user3", business_name="거절테스트")
        mgr.submit(app)
        ok = mgr.reject(app.application_id, reviewer_note="거절 사유")
        assert ok is True
        rejected = mgr.list_applications(ApplicationStatus.REJECTED)
        assert len(rejected) == 1

    def test_count(self, tmp_path):
        from src.wholesale.application_manager import WholesaleApplication, ApplicationStatus
        mgr = self._mgr(tmp_path)
        for i in range(3):
            mgr.submit(WholesaleApplication(user_id=f"u{i}", business_name=f"사{i}"))
        assert mgr.count() == 3
        assert mgr.count(ApplicationStatus.PENDING) == 3

    def test_summary_structure(self, tmp_path):
        mgr = self._mgr(tmp_path)
        summary = mgr.summary()
        assert "total" in summary
        assert "pending" in summary
        assert "approved" in summary
        assert "rejected" in summary


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


def test_wholesale_tiers_route_not_404(client):
    resp = client.get("/seller/wholesale/tiers")
    assert resp.status_code != 404


def test_wholesale_applications_route_not_404(client):
    resp = client.get("/seller/wholesale/applications")
    assert resp.status_code != 404


def test_wholesale_tiers_in_sidebar(client):
    html = client.get("/seller/dashboard").get_data(as_text=True)
    assert "/seller/wholesale/tiers" in html
