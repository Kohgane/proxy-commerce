"""tests/test_ai_listing_multi_publisher.py — 부분 성공 허용 테스트 (Phase 149)."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


SAMPLE_PRODUCT = {
    "listing_id": "test-listing-001",
    "analysis": {"category": "패션", "product_type": "티셔츠"},
    "language": "kr",
    "market_data": {
        "coupang": {"title": "테스트 티셔츠", "price_krw": 29000},
        "smartstore": {"title": "테스트 티셔츠 NS", "price_krw": 28000},
    },
}


class TestPublishToMarkets:
    def test_publish_returns_result_object(self):
        from src.ai_listing.multi_publisher import publish_to_markets

        result = publish_to_markets(
            ai_listing_id="test-001",
            product_data=SAMPLE_PRODUCT,
            markets=["coupang", "smartstore"],
        )
        assert result is not None

    def test_result_has_jobs(self):
        from src.ai_listing.multi_publisher import publish_to_markets

        result = publish_to_markets(
            ai_listing_id="test-002",
            product_data=SAMPLE_PRODUCT,
            markets=["coupang", "smartstore"],
        )
        assert len(result.jobs) == 2

    def test_each_market_has_job(self):
        from src.ai_listing.multi_publisher import publish_to_markets

        markets = ["coupang", "smartstore", "11st"]
        result = publish_to_markets(
            ai_listing_id="test-003",
            product_data=SAMPLE_PRODUCT,
            markets=markets,
        )
        job_markets = {j.market for j in result.jobs}
        assert job_markets == set(markets)

    def test_no_credentials_is_honest_failure_not_mock(self):
        """자격증명 미설정 시 가짜 MOCK 성공이 아니라 정직한 실패 (Phase 211)."""
        from src.ai_listing.multi_publisher import publish_to_markets

        result = publish_to_markets(
            ai_listing_id="test-004",
            product_data=SAMPLE_PRODUCT,
            markets=["coupang"],
        )
        # 가짜 MOCK 성공 ID를 만들지 않는다
        for j in result.jobs:
            assert not (j.external_product_id or "").startswith("MOCK-")
        assert result.success_count + result.failed_count == len(result.jobs)

    def test_unsupported_market_honest_failure(self):
        """쇼피/아마존 등 미연동 마켓은 가짜 성공이 아니라 실패 + 사유."""
        from src.ai_listing.multi_publisher import publish_to_markets

        result = publish_to_markets(
            ai_listing_id="test-004b",
            product_data=SAMPLE_PRODUCT,
            markets=["shopee"],
        )
        job = result.jobs[0]
        assert job.status == "failed"
        assert "미연동" in (job.error_message or "")

    def test_real_dispatch_success_maps_url(self, monkeypatch):
        """UploadDispatcher 성공 시 external_product_id + product_url 매핑."""
        from unittest.mock import MagicMock
        import src.ai_listing.multi_publisher as mp

        fake_result = MagicMock()
        fake_result.results = [MagicMock(success=True, queued=False,
                                         external_product_id="CP-77",
                                         external_url="https://coupang.com/vp/products/CP-77")]
        fake_dispatcher = MagicMock()
        fake_dispatcher.return_value.dispatch.return_value = fake_result
        monkeypatch.setattr(
            "src.seller_console.upload_dispatcher.UploadDispatcher", fake_dispatcher
        )
        result = mp.publish_to_markets(
            ai_listing_id="test-004c", product_data=SAMPLE_PRODUCT, markets=["coupang"],
        )
        job = result.jobs[0]
        assert job.status == "success"
        assert job.external_product_id == "CP-77"
        assert job.product_url == "https://coupang.com/vp/products/CP-77"

    def test_to_dict_structure(self):
        from src.ai_listing.multi_publisher import publish_to_markets

        result = publish_to_markets(
            ai_listing_id="test-005",
            product_data=SAMPLE_PRODUCT,
            markets=["coupang"],
        )
        d = result.to_dict()
        assert "ai_listing_id" in d
        assert "success_count" in d
        assert "failed_count" in d
        assert "markets" in d
        assert isinstance(d["markets"], list)

    def test_success_and_failed_counts(self):
        from src.ai_listing.multi_publisher import publish_to_markets, PublishResult, PublishJob

        # 수동으로 부분 성공 결과 만들기
        jobs = [
            PublishJob(ai_listing_id="x", market="coupang", product_data={}, status="success"),
            PublishJob(ai_listing_id="x", market="smartstore", product_data={}, status="failed"),
        ]
        result = PublishResult(ai_listing_id="x", jobs=jobs)
        assert result.success_count == 1
        assert result.failed_count == 1
        assert result.partial_success is True

    def test_all_success_not_partial(self):
        from src.ai_listing.multi_publisher import PublishResult, PublishJob

        jobs = [
            PublishJob(ai_listing_id="x", market="coupang", product_data={}, status="success"),
            PublishJob(ai_listing_id="x", market="smartstore", product_data={}, status="success"),
        ]
        result = PublishResult(ai_listing_id="x", jobs=jobs)
        assert result.partial_success is False
        assert result.success_count == 2
        assert result.failed_count == 0

    def test_publish_job_initial_status_queued(self):
        from src.ai_listing.multi_publisher import PublishJob

        job = PublishJob(ai_listing_id="x", market="coupang", product_data={})
        assert job.status == "queued"
        assert job.external_product_id is None

    def test_publisher_stats_structure(self):
        from src.ai_listing.multi_publisher import publisher_stats

        stats = publisher_stats()
        assert "attempts_24h" in stats
        assert "success_24h" in stats
        assert "failed_24h" in stats
        assert "by_market" in stats
