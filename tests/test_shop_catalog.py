"""tests/test_shop_catalog.py — 자체몰 카탈로그 테스트 (Phase 131).

Sheets mock + 진열 필터링 검증.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# 픽스처
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_catalog_rows():
    """테스트용 catalog 시트 rows."""
    return [
        {
            "sku": "ALO-001",
            "title_ko": "Alo Yoga 레깅스 XS",
            "title_en": "Alo Yoga Legging XS",
            "price_krw": 89000,
            "sale_price_krw": 75000,
            "marketplace": "kohganemultishop",
            "state": "active",
            "slug": "alo-yoga-legging-xs",
            "featured": "true",
            "category": "yoga",
            "thumbnail_url": "https://example.com/img1.jpg",
            "gallery_urls_json": '["https://example.com/img1.jpg"]',
            "description_html_short": "최고급 요가 레깅스",
            "description_html_long": "<p>상세 설명</p>",
            "stock_qty": 10,
            "shipping_fee_krw": 3000,
            "options_json": '[{"name": "size", "values": ["XS", "S", "M"]}]',
        },
        {
            "sku": "ALO-002",
            "title_ko": "Alo 스포츠 탑",
            "title_en": "Alo Sports Top",
            "price_krw": 55000,
            "sale_price_krw": "",
            "marketplace": "all",
            "state": "active",
            "slug": "alo-sports-top",
            "featured": "false",
            "category": "yoga",
            "thumbnail_url": "",
            "gallery_urls_json": "",
            "description_html_short": "스포츠 탑",
            "description_html_long": "",
            "stock_qty": 5,
            "shipping_fee_krw": 3000,
            "options_json": "",
        },
        {
            # 비진열 (marketplace 불일치)
            "sku": "OTHER-001",
            "title_ko": "다른 마켓 상품",
            "price_krw": 10000,
            "marketplace": "coupang",
            "state": "active",
            "slug": "other-product",
            "featured": "false",
            "category": "etc",
            "thumbnail_url": "",
            "gallery_urls_json": "",
            "description_html_short": "",
            "description_html_long": "",
            "stock_qty": 1,
            "shipping_fee_krw": 0,
            "options_json": "",
            "sale_price_krw": "",
        },
        {
            # 비진열 (state inactive)
            "sku": "INACTIVE-001",
            "title_ko": "비활성 상품",
            "price_krw": 20000,
            "marketplace": "kohganemultishop",
            "state": "inactive",
            "slug": "inactive-product",
            "featured": "false",
            "category": "yoga",
            "thumbnail_url": "",
            "gallery_urls_json": "",
            "description_html_short": "",
            "description_html_long": "",
            "stock_qty": 0,
            "shipping_fee_krw": 0,
            "options_json": "",
            "sale_price_krw": "",
        },
    ]


# ---------------------------------------------------------------------------
# 1. ShopProduct 도메인 모델
# ---------------------------------------------------------------------------

class TestShopProduct:
    def test_import(self):
        from src.shop.catalog import ShopProduct
        assert ShopProduct is not None

    def test_to_dict(self):
        from src.shop.catalog import ShopProduct
        p = ShopProduct(
            slug="test-slug",
            sku="TEST-001",
            title_ko="테스트 상품",
            price_krw=10000,
            sale_price_krw=8000,
            thumbnail_url="",
            gallery_urls=[],
            short_desc="설명",
            long_desc_html="",
            options=[],
            stock_qty=5,
            shipping_fee_krw=3000,
            category="yoga",
            featured=True,
        )
        d = p.to_dict()
        assert d["slug"] == "test-slug"
        assert d["price_krw"] == 10000
        assert d["featured"] is True


# ---------------------------------------------------------------------------
# 2. _row_to_product 필터링
# ---------------------------------------------------------------------------

class TestRowToProduct:
    def test_valid_kohganemultishop(self, mock_catalog_rows):
        from src.shop.catalog import _row_to_product
        p = _row_to_product(mock_catalog_rows[0])
        assert p is not None
        assert p.slug == "alo-yoga-legging-xs"
        assert p.price_krw == 89000
        assert p.sale_price_krw == 75000
        assert p.featured is True
        assert p.category == "yoga"

    def test_valid_all_marketplace(self, mock_catalog_rows):
        from src.shop.catalog import _row_to_product
        p = _row_to_product(mock_catalog_rows[1])
        assert p is not None
        assert p.slug == "alo-sports-top"

    def test_filtered_wrong_marketplace(self, mock_catalog_rows):
        from src.shop.catalog import _row_to_product
        p = _row_to_product(mock_catalog_rows[2])
        assert p is None

    def test_filtered_inactive(self, mock_catalog_rows):
        from src.shop.catalog import _row_to_product
        p = _row_to_product(mock_catalog_rows[3])
        assert p is None

    def test_options_parsed(self, mock_catalog_rows):
        from src.shop.catalog import _row_to_product
        p = _row_to_product(mock_catalog_rows[0])
        assert p is not None
        assert len(p.options) == 1
        assert p.options[0]["name"] == "size"
        assert "XS" in p.options[0]["values"]

    def test_gallery_urls_parsed(self, mock_catalog_rows):
        from src.shop.catalog import _row_to_product
        p = _row_to_product(mock_catalog_rows[0])
        assert p is not None
        assert len(p.gallery_urls) == 1


# ---------------------------------------------------------------------------
# 3. ShopCatalog — mock Sheets
# ---------------------------------------------------------------------------

class TestShopCatalog:
    def test_import(self):
        from src.shop.catalog import ShopCatalog
        assert ShopCatalog is not None

    def test_list_all_no_sheet_id(self, monkeypatch):
        """GOOGLE_SHEET_ID 미설정 시 빈 목록 반환."""
        monkeypatch.delenv("GOOGLE_SHEET_ID", raising=False)
        from src.shop.catalog import ShopCatalog
        cat = ShopCatalog(sheet_id="")
        result = cat.list_all()
        assert result == []

    def test_list_all_with_mock(self, monkeypatch, mock_catalog_rows):
        """Sheets mock → 2개 상품만 필터링."""
        from src.shop.catalog import ShopCatalog, _row_to_product

        cat = ShopCatalog(sheet_id="fake-id")
        # _fetch를 mock
        products = [_row_to_product(r) for r in mock_catalog_rows if _row_to_product(r)]
        cat._cache = products
        cat._cache_at = float("inf")  # 캐시 만료 없음

        result = cat.list_all()
        assert len(result) == 2

    def test_list_featured(self, mock_catalog_rows):
        from src.shop.catalog import ShopCatalog, _row_to_product

        cat = ShopCatalog(sheet_id="fake-id")
        products = [_row_to_product(r) for r in mock_catalog_rows if _row_to_product(r)]
        cat._cache = products
        cat._cache_at = float("inf")

        featured = cat.list_featured()
        assert len(featured) == 1
        assert featured[0].slug == "alo-yoga-legging-xs"

    def test_get_by_slug(self, mock_catalog_rows):
        from src.shop.catalog import ShopCatalog, _row_to_product

        cat = ShopCatalog(sheet_id="fake-id")
        products = [_row_to_product(r) for r in mock_catalog_rows if _row_to_product(r)]
        cat._cache = products
        cat._cache_at = float("inf")

        p = cat.get_by_slug("alo-yoga-legging-xs")
        assert p is not None
        assert p.title_ko == "Alo Yoga 레깅스 XS"

        missing = cat.get_by_slug("nonexistent")
        assert missing is None

    def test_search(self, mock_catalog_rows):
        from src.shop.catalog import ShopCatalog, _row_to_product

        cat = ShopCatalog(sheet_id="fake-id")
        products = [_row_to_product(r) for r in mock_catalog_rows if _row_to_product(r)]
        cat._cache = products
        cat._cache_at = float("inf")

        results = cat.search("요가")
        assert len(results) >= 1

        results_none = cat.search("존재하지않는상품12345")
        assert results_none == []

    def test_get_categories(self, mock_catalog_rows):
        from src.shop.catalog import ShopCatalog, _row_to_product

        cat = ShopCatalog(sheet_id="fake-id")
        products = [_row_to_product(r) for r in mock_catalog_rows if _row_to_product(r)]
        cat._cache = products
        cat._cache_at = float("inf")

        cats = cat.get_categories()
        assert len(cats) >= 1
        # yoga 카테고리가 있어야 함
        names = [c["name"] for c in cats]
        assert "yoga" in names

    def test_list_by_category(self, mock_catalog_rows):
        from src.shop.catalog import ShopCatalog, _row_to_product

        cat = ShopCatalog(sheet_id="fake-id")
        products = [_row_to_product(r) for r in mock_catalog_rows if _row_to_product(r)]
        cat._cache = products
        cat._cache_at = float("inf")

        items, total = cat.list_by_category("yoga")
        assert total == 2
        assert len(items) == 2

        items2, total2 = cat.list_by_category("nonexistent_category")
        assert total2 == 0


# ---------------------------------------------------------------------------
# 4. slugify
# ---------------------------------------------------------------------------

class TestSlugify:
    def test_basic(self):
        from src.shop.catalog import _slugify
        assert _slugify("Alo Yoga Legging XS") == "alo-yoga-legging-xs"

    def test_korean(self):
        from src.shop.catalog import _slugify
        result = _slugify("요가 레깅스")
        assert len(result) > 0  # 빈 문자열 아닌 결과

    def test_empty(self):
        from src.shop.catalog import _slugify
        assert _slugify("") == "product"


# ---------------------------------------------------------------------------
# 5. get_catalog 싱글턴
# ---------------------------------------------------------------------------

def test_get_catalog_singleton():
    from src.shop.catalog import get_catalog, _default_catalog
    c1 = get_catalog()
    c2 = get_catalog()
    assert c1 is c2
