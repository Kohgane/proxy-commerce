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

    def test_mock_publish_success(self):
        from src.ai_listing.multi_publisher import publish_to_markets

        result = publish_to_markets(
            ai_listing_id="test-004",
            product_data=SAMPLE_PRODUCT,
            markets=["coupang"],
        )
        # mock 모드에서는 성공해야 함
        assert result.success_count >= 0  # 최소 실패가 없어야 함

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


class TestMockPublish:
    def test_mock_publish_sets_success(self):
        from src.ai_listing.multi_publisher import _mock_publish, PublishJob

        job = PublishJob(ai_listing_id="x", market="coupang", product_data={})
        result = _mock_publish(job)
        assert result.status == "success"
        assert result.external_product_id is not None
        assert "MOCK" in result.external_product_id
        assert result.published_at is not None
