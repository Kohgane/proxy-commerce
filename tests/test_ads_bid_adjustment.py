"""tests/test_ads_bid_adjustment.py — ROAS 기반 입찰가 조정 로직 테스트 (Phase 144)."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def reset_stores():
    from src.ads import auto_campaign
    auto_campaign._campaign_recs.clear()
    auto_campaign._active_campaigns.clear()
    yield
    auto_campaign._campaign_recs.clear()
    auto_campaign._active_campaigns.clear()


def _setup_active_campaign(cid: str = "TEST-CMP-001", bid: int = 500):
    """테스트용 활성 캠페인 등록."""
    from src.ads.auto_campaign import _active_campaigns
    _active_campaigns[cid] = {
        "campaign_id": cid,
        "channel": "coupang",
        "sku": "SKU-TEST",
        "product_name": "테스트 상품",
        "keywords": ["테스트"],
        "daily_budget_krw": 5000,
        "status": "active",
        "current_bid_krw": bid,
    }
    return cid


class TestAdjustBidsRoasLogic:
    """ROAS 기반 입찰가 조정 로직."""

    def test_zero_roas_decreases_bid(self, monkeypatch):
        monkeypatch.setattr("src.ads.auto_campaign._TARGET_ROAS", 3.0)
        monkeypatch.setattr("src.ads.auto_campaign._BID_ADJUST_MAX_PCT", 20.0)
        from src.ads.auto_campaign import adjust_bids, PerformanceData
        cid = _setup_active_campaign(bid=500)
        perf = PerformanceData(
            campaign_id=cid, impressions=1000, clicks=10,
            cost_krw=5000.0, revenue_krw=0.0
        )
        result = adjust_bids(cid, perf)
        assert result["action"] == "decrease", "ROAS=0 인데 decrease 아님"
        assert result["new_bid"] < result["old_bid"], "ROAS=0 인데 입찰가 감소 안 함"
        assert result["new_bid"] >= 50, "최소 입찰가 50원 이하"

    def test_high_roas_increases_bid(self, monkeypatch):
        monkeypatch.setattr("src.ads.auto_campaign._TARGET_ROAS", 3.0)
        monkeypatch.setattr("src.ads.auto_campaign._BID_ADJUST_MAX_PCT", 20.0)
        from src.ads.auto_campaign import adjust_bids, PerformanceData
        cid = _setup_active_campaign(bid=500)
        perf = PerformanceData(
            campaign_id=cid, impressions=1000, clicks=50,
            cost_krw=5000.0, revenue_krw=40000.0  # ROAS=8.0 (목표 3.0의 2배 초과)
        )
        result = adjust_bids(cid, perf)
        assert result["action"] == "increase", f"높은 ROAS인데 increase 아님: {result}"
        assert result["new_bid"] > result["old_bid"], "높은 ROAS인데 입찰가 증가 안 함"

    def test_good_roas_no_change(self, monkeypatch):
        monkeypatch.setattr("src.ads.auto_campaign._TARGET_ROAS", 3.0)
        monkeypatch.setattr("src.ads.auto_campaign._BID_ADJUST_MAX_PCT", 20.0)
        from src.ads.auto_campaign import adjust_bids, PerformanceData
        cid = _setup_active_campaign(bid=500)
        perf = PerformanceData(
            campaign_id=cid, impressions=1000, clicks=30,
            cost_krw=5000.0, revenue_krw=16000.0  # ROAS=3.2 (목표 근접)
        )
        result = adjust_bids(cid, perf)
        assert result["action"] == "no_op", f"ROAS 목표 근접인데 조정함: {result}"

    def test_low_roas_decreases_bid(self, monkeypatch):
        monkeypatch.setattr("src.ads.auto_campaign._TARGET_ROAS", 3.0)
        monkeypatch.setattr("src.ads.auto_campaign._BID_ADJUST_MAX_PCT", 20.0)
        from src.ads.auto_campaign import adjust_bids, PerformanceData
        cid = _setup_active_campaign(bid=500)
        perf = PerformanceData(
            campaign_id=cid, impressions=1000, clicks=10,
            cost_krw=5000.0, revenue_krw=5000.0  # ROAS=1.0 (목표 미달)
        )
        result = adjust_bids(cid, perf)
        assert result["action"] == "decrease", f"ROAS 미달인데 decrease 아님: {result}"

    def test_adjust_bid_max_pct_limit(self, monkeypatch):
        monkeypatch.setattr("src.ads.auto_campaign._TARGET_ROAS", 3.0)
        monkeypatch.setattr("src.ads.auto_campaign._BID_ADJUST_MAX_PCT", 20.0)
        from src.ads.auto_campaign import adjust_bids, PerformanceData
        cid = _setup_active_campaign(bid=1000)
        perf = PerformanceData(
            campaign_id=cid, impressions=1000, clicks=100,
            cost_krw=5000.0, revenue_krw=500000.0  # ROAS=100 (극도로 높음)
        )
        result = adjust_bids(cid, perf)
        if result["action"] == "increase":
            max_allowed = int(1000 * 1.20)  # 20% 이하
            assert result["new_bid"] <= max_allowed + 1, (
                f"입찰가 인상이 max_pct 20% 초과: {result['new_bid']} > {max_allowed}"
            )

    def test_nonexistent_campaign_returns_no_op(self):
        from src.ads.auto_campaign import adjust_bids, PerformanceData
        perf = PerformanceData(campaign_id="NONEXISTENT")
        result = adjust_bids("NONEXISTENT", perf)
        assert result["action"] == "no_op"

    def test_adjust_updates_stored_bid(self, monkeypatch):
        monkeypatch.setattr("src.ads.auto_campaign._TARGET_ROAS", 3.0)
        monkeypatch.setattr("src.ads.auto_campaign._BID_ADJUST_MAX_PCT", 20.0)
        from src.ads.auto_campaign import adjust_bids, PerformanceData, _active_campaigns
        cid = _setup_active_campaign(bid=500)
        perf = PerformanceData(
            campaign_id=cid, impressions=100, clicks=5,
            cost_krw=500.0, revenue_krw=0.0  # ROAS=0
        )
        result = adjust_bids(cid, perf)
        stored_bid = _active_campaigns[cid]["current_bid_krw"]
        assert stored_bid == result["new_bid"], "조정된 입찰가가 저장소에 반영되지 않음"


class TestPerformanceData:
    def test_roas_calculation(self):
        from src.ads.auto_campaign import PerformanceData
        perf = PerformanceData(
            campaign_id="x", cost_krw=10000.0, revenue_krw=30000.0
        )
        assert perf.roas == pytest.approx(3.0)

    def test_zero_cost_roas(self):
        from src.ads.auto_campaign import PerformanceData
        perf = PerformanceData(campaign_id="x", cost_krw=0.0, revenue_krw=1000.0)
        assert perf.roas == 0.0

    def test_cpc_calculation(self):
        from src.ads.auto_campaign import PerformanceData
        perf = PerformanceData(campaign_id="x", cost_krw=1000.0, clicks=10)
        assert perf.cpc_krw == pytest.approx(100.0)

    def test_to_dict(self):
        from src.ads.auto_campaign import PerformanceData
        perf = PerformanceData(
            campaign_id="x", impressions=500, clicks=25,
            cost_krw=5000.0, revenue_krw=20000.0, conversions=3
        )
        d = perf.to_dict()
        assert d["roas"] == pytest.approx(4.0)
        assert d["cpc_krw"] == pytest.approx(200.0)
        assert d["ctr"] == pytest.approx(5.0)
