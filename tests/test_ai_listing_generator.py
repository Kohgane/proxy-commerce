"""tests/test_ai_listing_generator.py — 마켓별 글자수 제한 + 금칙어 테스트 (Phase 149)."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture(autouse=True)
def mock_provider(monkeypatch):
    monkeypatch.setenv("AI_LISTING_VISION_PROVIDER", "mock")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


SAMPLE_ANALYSIS = {
    "category": "패션",
    "brand": "TestBrand",
    "colors": ["화이트", "블랙"],
    "materials": ["면"],
    "keywords": ["티셔츠", "기본", "데일리", "루즈핏", "캐주얼"],
    "estimated_price_range": {"min": 15000, "max": 45000},
    "product_type": "티셔츠",
    "features": ["기본 라운드넥", "루즈핏 실루엣"],
}


class TestTitleGeneration:
    def test_coupang_title_max_50(self):
        from src.ai_listing.generator import generate_title

        title = generate_title(SAMPLE_ANALYSIS, "coupang")
        assert len(title) <= 50, f"쿠팡 제목 50자 초과: {len(title)}자"

    def test_smartstore_title_max_100(self):
        from src.ai_listing.generator import generate_title

        title = generate_title(SAMPLE_ANALYSIS, "smartstore")
        assert len(title) <= 100, f"스마트스토어 제목 100자 초과: {len(title)}자"

    def test_11st_title_max_100(self):
        from src.ai_listing.generator import generate_title

        title = generate_title(SAMPLE_ANALYSIS, "11st")
        assert len(title) <= 100

    def test_gmarket_title_max_80(self):
        from src.ai_listing.generator import generate_title

        title = generate_title(SAMPLE_ANALYSIS, "gmarket")
        assert len(title) <= 80

    def test_title_not_empty(self):
        from src.ai_listing.generator import generate_title

        for market in ("coupang", "smartstore", "11st", "gmarket"):
            title = generate_title(SAMPLE_ANALYSIS, market)
            assert title.strip(), f"{market} 제목이 빈 문자열"

    def test_forbidden_terms_removed(self):
        from src.ai_listing.generator import generate_title, _filter_forbidden_terms

        # 금칙어가 있는 텍스트를 필터링
        text = "최저가 보장 티셔츠"
        filtered = _filter_forbidden_terms(text, ["최저가", "보장"])
        assert "최저가" not in filtered
        assert "보장" not in filtered

    def test_titles_for_all_markets(self):
        from src.ai_listing.generator import generate_titles_for_markets

        markets = ["coupang", "smartstore", "11st", "gmarket"]
        result = generate_titles_for_markets(SAMPLE_ANALYSIS, markets)
        assert set(result.keys()) == set(markets)
        for market, title in result.items():
            assert title, f"{market} 제목 없음"


class TestDescriptionGeneration:
    def test_description_not_empty(self):
        from src.ai_listing.generator import generate_description

        desc = generate_description(SAMPLE_ANALYSIS, "coupang")
        assert desc.strip()

    def test_description_japanese(self):
        from src.ai_listing.generator import generate_description

        desc = generate_description(SAMPLE_ANALYSIS, "coupang", language="jp")
        assert desc.strip()


class TestTagGeneration:
    def test_tags_is_list(self):
        from src.ai_listing.generator import generate_tags

        tags = generate_tags(SAMPLE_ANALYSIS)
        assert isinstance(tags, list)

    def test_tags_max_10(self):
        from src.ai_listing.generator import generate_tags

        tags = generate_tags(SAMPLE_ANALYSIS, max_tags=10)
        assert len(tags) <= 10

    def test_tags_not_empty(self):
        from src.ai_listing.generator import generate_tags

        tags = generate_tags(SAMPLE_ANALYSIS)
        assert len(tags) > 0

    def test_tags_include_keywords(self):
        from src.ai_listing.generator import generate_tags

        tags = generate_tags(SAMPLE_ANALYSIS)
        # 원래 키워드가 태그에 포함되어야 함
        for kw in SAMPLE_ANALYSIS["keywords"][:3]:
            assert kw in tags, f"키워드 '{kw}'가 태그에 없음"


class TestTrimToMaxLen:
    def test_trim_short_text_unchanged(self):
        from src.ai_listing.generator import _trim_to_max_len

        text = "짧은 텍스트"
        assert _trim_to_max_len(text, 100) == text

    def test_trim_long_text(self):
        from src.ai_listing.generator import _trim_to_max_len

        text = "가" * 200
        result = _trim_to_max_len(text, 50)
        assert len(result) <= 50
