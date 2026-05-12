"""tests/test_ai_listing_analyzer_v2.py — URL 스크래퍼 통합 분석 테스트 (Phase 150)."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("AI_LISTING_VISION_PROVIDER", "mock")


@pytest.fixture(autouse=True)
def mock_provider(monkeypatch):
    monkeypatch.setenv("AI_LISTING_VISION_PROVIDER", "mock")


class TestAnalyzeWithPageUrl:
    def test_analyze_with_page_url_returns_scrape_metadata(self):
        import unittest.mock as mock
        from src.ai_listing.analyzer import analyze_image

        scrape_result = {
            "title": "스크래핑된 티셔츠",
            "description": "베스트 셀러 티셔츠",
            "price_candidates": [29000, 35000],
            "brand_candidates": ["TestBrand"],
            "material_candidates": ["면", "폴리에스터"],
            "size_candidates": ["S", "M", "L"],
            "color_candidates": ["블랙", "화이트"],
            "origin_country": "한국",
            "images": ["https://example.com/img1.jpg"],
            "raw_text_truncated": "면 100% 최고 품질",
            "_source_url": "https://example.com/product",
            "_scraped": True,
            "_error": None,
        }

        with mock.patch(
            "src.ai_listing.url_scraper.scrape_product_page",
            return_value=scrape_result,
        ):
            result = analyze_image(
                image_url="https://example.com/img.jpg",
                page_url="https://example.com/product",
                force_refresh=True,
            )

        assert result is not None
        # 스크래핑 데이터가 결과에 반영되어야 함
        assert result.get("_scraped") is True
        assert result.get("brand") == "TestBrand" or result.get("brand") is not None

    def test_analyze_without_page_url_still_works(self):
        from src.ai_listing.analyzer import analyze_image

        result = analyze_image(
            image_url="https://example.com/img.jpg",
            force_refresh=True,
        )
        assert result is not None
        assert "category" in result

    def test_analyze_with_failed_scrape_still_works(self):
        import unittest.mock as mock
        from src.ai_listing.analyzer import analyze_image

        failed_scrape = {
            "title": "",
            "description": "",
            "price_candidates": [],
            "brand_candidates": [],
            "material_candidates": [],
            "size_candidates": [],
            "color_candidates": [],
            "origin_country": None,
            "images": [],
            "raw_text_truncated": "",
            "_source_url": "https://example.com/product",
            "_scraped": False,
            "_error": "connection error",
        }

        with mock.patch(
            "src.ai_listing.url_scraper.scrape_product_page",
            return_value=failed_scrape,
        ):
            result = analyze_image(
                image_url="https://example.com/img.jpg",
                page_url="https://example.com/product",
                force_refresh=True,
            )

        # 스크래핑 실패해도 이미지 분석은 계속 진행
        assert result is not None
        assert "category" in result

    def test_analyze_page_url_only_no_image(self):
        """이미지 없이 page_url만 있을 때 스크래핑 이미지 사용."""
        import unittest.mock as mock
        from src.ai_listing.analyzer import analyze_image

        scrape_result = {
            "title": "이미지 없는 테스트",
            "description": "",
            "price_candidates": [19000],
            "brand_candidates": [],
            "material_candidates": [],
            "size_candidates": [],
            "color_candidates": [],
            "origin_country": None,
            "images": ["https://example.com/scraped-img.jpg"],
            "raw_text_truncated": "",
            "_source_url": "https://example.com/product2",
            "_scraped": True,
            "_error": None,
        }

        with mock.patch(
            "src.ai_listing.url_scraper.scrape_product_page",
            return_value=scrape_result,
        ):
            result = analyze_image(
                page_url="https://example.com/product2",
                force_refresh=True,
            )

        assert result is not None


class TestMergeScrapIntoResult:
    def test_brand_merged_from_scrape(self):
        from src.ai_listing.analyzer import _merge_scrape_into_result

        result = {"category": "패션", "brand": None, "materials": [], "colors": []}
        scrape = {
            "brand_candidates": ["SuperBrand"],
            "material_candidates": [],
            "color_candidates": [],
            "price_candidates": [],
            "size_candidates": [],
            "origin_country": None,
            "images": [],
        }
        merged = _merge_scrape_into_result(result, scrape)
        assert merged["brand"] == "SuperBrand"
        assert merged.get("_brand_source") == "scraping"

    def test_price_merged_from_scrape(self):
        from src.ai_listing.analyzer import _merge_scrape_into_result

        result = {"category": "패션", "brand": None}
        scrape = {
            "brand_candidates": [],
            "material_candidates": [],
            "color_candidates": [],
            "price_candidates": [25000, 30000],
            "size_candidates": [],
            "origin_country": None,
            "images": [],
        }
        merged = _merge_scrape_into_result(result, scrape)
        assert merged["price_candidates"] == [25000, 30000]
        assert merged["estimated_price_range"]["min"] == 25000
        assert merged["estimated_price_range"]["max"] == 30000

    def test_materials_combined(self):
        from src.ai_listing.analyzer import _merge_scrape_into_result

        result = {"category": "패션", "materials": ["면"]}
        scrape = {
            "brand_candidates": [],
            "material_candidates": ["폴리에스터", "스판덱스"],
            "color_candidates": [],
            "price_candidates": [],
            "size_candidates": [],
            "origin_country": None,
            "images": [],
        }
        merged = _merge_scrape_into_result(result, scrape)
        assert "폴리에스터" in merged["materials"]
        assert "면" in merged["materials"]


class TestV2Prompt:
    def test_build_v2_prompt_with_scrape_data(self):
        from src.ai_listing.templates_prompts import build_v2_analysis_prompt

        scrape = {
            "title": "테스트 상품",
            "description": "좋은 상품입니다",
            "price_candidates": [25000],
            "brand_candidates": ["BrandX"],
            "material_candidates": ["면"],
            "size_candidates": ["M", "L"],
            "color_candidates": ["블랙"],
            "origin_country": "한국",
            "raw_text_truncated": "상품 본문 텍스트",
        }
        prompt = build_v2_analysis_prompt(language="kr", scrape_data=scrape)
        assert "BrandX" in prompt
        assert "25000" in prompt
        assert "테스트 상품" in prompt

    def test_build_v2_prompt_no_scrape(self):
        from src.ai_listing.templates_prompts import build_v2_analysis_prompt

        prompt = build_v2_analysis_prompt(language="kr", scrape_data=None)
        assert "스크래핑 없음" in prompt

    def test_build_v2_prompt_japanese(self):
        from src.ai_listing.templates_prompts import build_v2_analysis_prompt

        prompt = build_v2_analysis_prompt(language="jp", scrape_data=None)
        assert "スクレイピング" in prompt or "スクレイピング情報" in prompt
