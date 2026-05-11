"""tests/test_ai_listing_category_mapper.py — 카테고리 매핑 테스트 (Phase 149)."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestGetCategoryCode:
    def test_coupang_fashion(self):
        from src.ai_listing.category_mapper import get_category_code

        code = get_category_code("패션", "coupang")
        assert code == "56139"

    def test_smartstore_beauty(self):
        from src.ai_listing.category_mapper import get_category_code

        code = get_category_code("뷰티", "smartstore")
        assert code == "50000819"

    def test_11st_electronics(self):
        from src.ai_listing.category_mapper import get_category_code

        code = get_category_code("전자기기", "11st")
        assert code == "1001"

    def test_gmarket_sports(self):
        from src.ai_listing.category_mapper import get_category_code

        code = get_category_code("스포츠", "gmarket")
        assert code == "60010004"

    def test_unknown_category_returns_default(self):
        from src.ai_listing.category_mapper import get_category_code

        code = get_category_code("존재하지않는카테고리", "coupang")
        # default 코드를 반환해야 함
        assert code != ""

    def test_unknown_market_returns_empty(self):
        from src.ai_listing.category_mapper import get_category_code

        code = get_category_code("패션", "unknown_market")
        # 알 수 없는 마켓 → 빈 문자열 또는 default
        assert isinstance(code, str)

    def test_partial_match(self):
        from src.ai_listing.category_mapper import get_category_code

        # "화장품" → "뷰티" 카테고리 코드 (부분 일치는 없으므로 default)
        code = get_category_code("화장품", "coupang")
        assert code != ""  # default 이상은 반환해야 함

    def test_all_supported_markets(self):
        from src.ai_listing.category_mapper import get_category_code

        markets = ["coupang", "smartstore", "11st", "gmarket"]
        for market in markets:
            code = get_category_code("패션", market)
            assert code, f"{market}의 패션 카테고리 코드 없음"


class TestMapCategoriesForMarkets:
    def test_returns_all_markets(self):
        from src.ai_listing.category_mapper import map_categories_for_markets

        markets = ["coupang", "smartstore", "11st", "gmarket"]
        result = map_categories_for_markets("패션", markets)
        assert set(result.keys()) == set(markets)

    def test_all_codes_non_empty(self):
        from src.ai_listing.category_mapper import map_categories_for_markets

        markets = ["coupang", "smartstore"]
        result = map_categories_for_markets("뷰티", markets)
        for market, code in result.items():
            assert code, f"{market} 카테고리 코드 빈 문자열"


class TestGetSupportedCategories:
    def test_returns_list(self):
        from src.ai_listing.category_mapper import get_supported_categories

        cats = get_supported_categories()
        assert isinstance(cats, list)
        assert len(cats) > 0

    def test_default_not_in_list(self):
        from src.ai_listing.category_mapper import get_supported_categories

        cats = get_supported_categories()
        assert "default" not in cats

    def test_common_categories_present(self):
        from src.ai_listing.category_mapper import get_supported_categories

        cats = get_supported_categories()
        for expected in ("패션", "뷰티", "전자기기"):
            assert expected in cats, f"카테고리 '{expected}' 없음"
