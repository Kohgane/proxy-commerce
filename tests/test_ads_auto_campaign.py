"""tests/test_ads_auto_campaign.py — 광고 자동 운영 테스트 (Phase 144).

추천/생성/예산 가드/pause 로직 검증.
"""
from __future__ import annotations

import os
import pytest


@pytest.fixture(autouse=True)
def reset_stores():
    """각 테스트 전후 인메모리 저장소 초기화."""
    from src.ads import auto_campaign
    auto_campaign._campaign_recs.clear()
    auto_campaign._active_campaigns.clear()
    yield
    auto_campaign._campaign_recs.clear()
    auto_campaign._active_campaigns.clear()


class TestRecommendCampaigns:
    def test_recommend_returns_list(self):
        from src.ads.auto_campaign import recommend_campaigns
        recs = recommend_campaigns(roas_target=2.0)
        assert isinstance(recs, list)

    def test_recommend_filters_low_roas(self):
        from src.ads.auto_campaign import recommend_campaigns
        # roas_target 매우 높게 → 대부분 필터됨
        recs = recommend_campaigns(roas_target=100.0)
        assert len(recs) == 0

    def test_recommend_creates_pending_status(self):
        from src.ads.auto_campaign import recommend_campaigns
        recs = recommend_campaigns(roas_target=1.0)
        assert all(r.status == "pending" for r in recs)

    def test_recommend_covers_channels(self):
        from src.ads.auto_campaign import recommend_campaigns
        recs = recommend_campaigns(roas_target=1.0)
        channels = {r.channel for r in recs}
        assert "coupang" in channels
        assert "naver" in channels

    def test_recommend_has_keywords(self):
        from src.ads.auto_campaign import recommend_campaigns
        recs = recommend_campaigns(roas_target=1.0)
        for r in recs:
            assert len(r.keywords) > 0

    def test_rec_to_dict(self):
        from src.ads.auto_campaign import CampaignRec
        rec = CampaignRec(sku="TEST-001", product_name="테스트 상품", channel="coupang")
        d = rec.to_dict()
        assert d["sku"] == "TEST-001"
        assert d["channel"] == "coupang"
        assert "rec_id" in d


class TestCreateCampaign:
    def test_create_campaign_auto_launch_off(self, monkeypatch):
        """ADS_AUTO_CAMPAIGN_AUTO_LAUNCH=0 → PENDING 반환."""
        monkeypatch.setattr("src.ads.auto_campaign._AUTO_LAUNCH", False)
        from src.ads.auto_campaign import CampaignRec, create_campaign
        rec = CampaignRec(sku="SKU-999", product_name="테스트", channel="coupang")
        cid = create_campaign(rec, "coupang")
        assert cid.startswith("PENDING-"), f"예상: PENDING-... 실제: {cid}"
        assert rec.status == "pending"

    def test_create_campaign_auto_launch_on(self, monkeypatch):
        """ADS_AUTO_CAMPAIGN_AUTO_LAUNCH=1 → launched 상태."""
        monkeypatch.setattr("src.ads.auto_campaign._AUTO_LAUNCH", True)
        monkeypatch.setattr("src.ads.auto_campaign._ENABLED", True)
        from src.ads.auto_campaign import CampaignRec, create_campaign, _active_campaigns
        rec = CampaignRec(sku="SKU-999", product_name="테스트", channel="coupang")
        cid = create_campaign(rec, "coupang")
        assert not cid.startswith("PENDING-"), "AUTO_LAUNCH=1인데 PENDING 반환"
        assert rec.status == "launched"
        assert cid in _active_campaigns


class TestBudgetGuard:
    def test_daily_budget_positive(self):
        """일일 예산이 양수인지 확인."""
        from src.ads.auto_campaign import _DAILY_BUDGET_KRW
        assert _DAILY_BUDGET_KRW > 0

    def test_recommend_respects_budget(self):
        """추천 캠페인의 일일 예산이 전체 일일 예산 초과하지 않음."""
        from src.ads.auto_campaign import recommend_campaigns, _DAILY_BUDGET_KRW
        recs = recommend_campaigns(roas_target=1.0)
        for r in recs:
            assert r.daily_budget_krw <= _DAILY_BUDGET_KRW, (
                f"캠페인 {r.rec_id} 예산 {r.daily_budget_krw} > 일일 한도 {_DAILY_BUDGET_KRW}"
            )


class TestPauseLowPerformers:
    def test_pause_zero_roas_campaigns(self, monkeypatch):
        monkeypatch.setattr("src.ads.auto_campaign._AUTO_LAUNCH", True)
        monkeypatch.setattr("src.ads.auto_campaign._ENABLED", True)
        from src.ads.auto_campaign import (
            CampaignRec, create_campaign, pause_low_performers, _active_campaigns
        )
        rec = CampaignRec(sku="SKU-P1", product_name="P1", channel="coupang")
        cid = create_campaign(rec, "coupang")
        # ROAS=0으로 설정
        _active_campaigns[cid]["roas"] = 0.0
        paused = pause_low_performers(min_roas=0.5)
        assert cid in paused
        assert _active_campaigns[cid]["status"] == "paused"

    def test_no_pause_when_good_roas(self, monkeypatch):
        monkeypatch.setattr("src.ads.auto_campaign._AUTO_LAUNCH", True)
        monkeypatch.setattr("src.ads.auto_campaign._ENABLED", True)
        from src.ads.auto_campaign import (
            CampaignRec, create_campaign, pause_low_performers, _active_campaigns
        )
        rec = CampaignRec(sku="SKU-P2", product_name="P2", channel="naver")
        cid = create_campaign(rec, "naver")
        _active_campaigns[cid]["roas"] = 5.0
        paused = pause_low_performers(min_roas=0.5)
        assert cid not in paused


class TestAdsStats:
    def test_ads_stats_returns_dict(self):
        from src.ads.auto_campaign import ads_stats
        s = ads_stats()
        assert isinstance(s, dict)
        assert "active_campaigns" in s
        assert "target_roas" in s
        assert "daily_budget_krw" in s

    def test_ads_stats_zero_when_empty(self):
        from src.ads.auto_campaign import ads_stats
        s = ads_stats()
        assert s["active_campaigns"] == 0
        assert s["roas_24h"] == 0.0
