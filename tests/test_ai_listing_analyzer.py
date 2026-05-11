"""tests/test_ai_listing_analyzer.py — Vision API mock + 캐시 테스트 (Phase 149)."""
from __future__ import annotations

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture(autouse=True)
def mock_provider(monkeypatch):
    """항상 mock provider 사용."""
    monkeypatch.setenv("AI_LISTING_VISION_PROVIDER", "mock")
    # OPENAI/ANTHROPIC 키 제거 → mock 강제
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


class TestAnalyzeImage:
    def test_analyze_with_url_returns_dict(self):
        from src.ai_listing.analyzer import analyze_image

        result = analyze_image(image_url="https://example.com/product.jpg")
        assert isinstance(result, dict)
        assert "category" in result
        assert "keywords" in result

    def test_analyze_mock_flag_set(self):
        from src.ai_listing.analyzer import analyze_image

        result = analyze_image(image_url="https://example.com/product.jpg")
        assert result.get("_mock") is True

    def test_analyze_returns_expected_fields(self):
        from src.ai_listing.analyzer import analyze_image

        result = analyze_image(image_url="https://example.com/product.jpg")
        for field in ("category", "brand", "colors", "materials", "keywords", "estimated_price_range"):
            assert field in result, f"필드 누락: {field}"

    def test_analyze_price_range_is_dict(self):
        from src.ai_listing.analyzer import analyze_image

        result = analyze_image(image_url="https://example.com/product.jpg")
        pr = result.get("estimated_price_range")
        assert isinstance(pr, dict)
        assert "min" in pr and "max" in pr

    def test_analyze_keywords_is_list(self):
        from src.ai_listing.analyzer import analyze_image

        result = analyze_image(image_url="https://example.com/product.jpg")
        assert isinstance(result.get("keywords"), list)

    def test_analyze_no_image_returns_error(self):
        from src.ai_listing.analyzer import analyze_image

        result = analyze_image()
        assert "error" in result

    def test_analyze_with_bytes(self):
        from src.ai_listing.analyzer import analyze_image

        result = analyze_image(image_bytes=b"fake_bytes")
        assert isinstance(result, dict)
        assert "category" in result


class TestAnalysisCache:
    def test_same_url_cached(self):
        from src.ai_listing import analyzer

        # 캐시 초기화
        analyzer._analysis_cache.clear()
        url = "https://example.com/cache_test.jpg"

        r1 = analyzer.analyze_image(image_url=url)
        r2 = analyzer.analyze_image(image_url=url)

        # 두 번째 호출은 캐시에서
        assert r1["category"] == r2["category"]

    def test_force_refresh_bypasses_cache(self):
        from src.ai_listing import analyzer

        analyzer._analysis_cache.clear()
        url = "https://example.com/force_refresh.jpg"

        r1 = analyzer.analyze_image(image_url=url)
        r2 = analyzer.analyze_image(image_url=url, force_refresh=True)

        # 결과 구조는 동일
        assert r1.keys() == r2.keys()

    def test_cache_stats(self):
        from src.ai_listing.analyzer import cache_stats, analyze_image

        analyze_image(image_url="https://example.com/stats_test.jpg")
        stats = cache_stats()
        assert "total" in stats
        assert "active" in stats
        assert "ttl_hours" in stats
        assert stats["total"] >= 1


class TestImageHash:
    def test_hash_from_url(self):
        from src.ai_listing.analyzer import _compute_image_hash

        h1 = _compute_image_hash(image_url="https://a.com/img.jpg")
        h2 = _compute_image_hash(image_url="https://b.com/img.jpg")
        assert h1 != h2

    def test_hash_from_bytes(self):
        from src.ai_listing.analyzer import _compute_image_hash

        h1 = _compute_image_hash(image_bytes=b"data1")
        h2 = _compute_image_hash(image_bytes=b"data2")
        assert h1 != h2

    def test_same_url_same_hash(self):
        from src.ai_listing.analyzer import _compute_image_hash

        url = "https://example.com/same.jpg"
        assert _compute_image_hash(image_url=url) == _compute_image_hash(image_url=url)
