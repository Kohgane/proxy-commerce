"""tests/test_ai_listing_url_scraper.py — URL 스크래퍼 유닛 테스트 (Phase 150).

JSON-LD 파싱, OG tag, 가격 정규식, 캐시 등을 검증.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── JSON-LD 파싱 ────────────────────────────────────────────────────────────

class TestJsonLdParsing:
    def test_extract_json_ld_product_schema(self):
        from src.ai_listing.url_scraper import _extract_json_ld, _find_product_schema

        try:
            from bs4 import BeautifulSoup
        except ImportError:
            pytest.skip("beautifulsoup4 not installed")

        html = """
        <html><body>
        <script type="application/ld+json">
        {
          "@context": "https://schema.org",
          "@type": "Product",
          "name": "테스트 티셔츠",
          "brand": {"@type": "Brand", "name": "TestBrand"},
          "offers": {"@type": "Offer", "price": "29000", "priceCurrency": "KRW"}
        }
        </script>
        </body></html>
        """
        soup = BeautifulSoup(html, "html.parser")
        items = _extract_json_ld(soup)
        assert len(items) >= 1

        product = _find_product_schema(items)
        assert product is not None
        assert product.get("name") == "테스트 티셔츠"

    def test_find_product_in_graph(self):
        from src.ai_listing.url_scraper import _extract_json_ld, _find_product_schema

        try:
            from bs4 import BeautifulSoup
        except ImportError:
            pytest.skip("beautifulsoup4 not installed")

        html = """
        <html><body>
        <script type="application/ld+json">
        {
          "@context": "https://schema.org",
          "@graph": [
            {"@type": "WebSite", "name": "Shop"},
            {"@type": "Product", "name": "그래프 상품", "offers": {"price": "15000"}}
          ]
        }
        </script>
        </body></html>
        """
        soup = BeautifulSoup(html, "html.parser")
        items = _extract_json_ld(soup)
        product = _find_product_schema(items)
        assert product is not None
        assert product.get("name") == "그래프 상품"

    def test_no_product_schema_returns_none(self):
        from src.ai_listing.url_scraper import _extract_json_ld, _find_product_schema

        try:
            from bs4 import BeautifulSoup
        except ImportError:
            pytest.skip("beautifulsoup4 not installed")

        html = """
        <html><body>
        <script type="application/ld+json">{"@type": "WebSite", "name": "Shop"}</script>
        </body></html>
        """
        soup = BeautifulSoup(html, "html.parser")
        items = _extract_json_ld(soup)
        product = _find_product_schema(items)
        assert product is None

    def test_invalid_json_is_ignored(self):
        from src.ai_listing.url_scraper import _extract_json_ld

        try:
            from bs4 import BeautifulSoup
        except ImportError:
            pytest.skip("beautifulsoup4 not installed")

        html = """
        <html><body>
        <script type="application/ld+json">{ invalid json }</script>
        </body></html>
        """
        soup = BeautifulSoup(html, "html.parser")
        items = _extract_json_ld(soup)
        assert items == []


# ── 가격 추출 정규식 ─────────────────────────────────────────────────────────

class TestPriceExtraction:
    def test_korean_won_prefix(self):
        from src.ai_listing.url_scraper import _extract_prices_from_text

        text = "판매가: ₩29,000 / 정가: ₩35,000"
        prices = _extract_prices_from_text(text)
        assert 29000 in prices
        assert 35000 in prices

    def test_korean_won_suffix(self):
        from src.ai_listing.url_scraper import _extract_prices_from_text

        text = "가격: 29,000원"
        prices = _extract_prices_from_text(text)
        assert 29000 in prices

    def test_price_out_of_range_ignored(self):
        from src.ai_listing.url_scraper import _extract_prices_from_text

        # 99원은 너무 작음, 200억은 너무 큼
        text = "99원짜리 사탕 / 20,000,000,000원 건물"
        prices = _extract_prices_from_text(text)
        assert 99 not in prices
        assert 20_000_000_000 not in prices

    def test_extract_price_from_schema(self):
        from src.ai_listing.url_scraper import _extract_price_from_schema

        product = {
            "offers": {
                "@type": "Offer",
                "price": "45000",
                "priceCurrency": "KRW",
            }
        }
        prices = _extract_price_from_schema(product)
        assert prices == [45000]

    def test_extract_price_multiple_offers(self):
        from src.ai_listing.url_scraper import _extract_price_from_schema

        product = {
            "offers": [
                {"price": "20000"},
                {"price": "25000"},
            ]
        }
        prices = _extract_price_from_schema(product)
        assert set(prices) == {20000, 25000}


# ── OG 태그 추출 ─────────────────────────────────────────────────────────────

class TestOGTagExtraction:
    def _make_soup(self, html):
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            pytest.skip("beautifulsoup4 not installed")
        return BeautifulSoup(html, "html.parser")

    def test_og_title_extracted(self):
        from src.ai_listing.url_scraper import scrape_product_page
        import unittest.mock as mock

        html = """
        <html>
        <head>
          <title>일반 타이틀</title>
          <meta property="og:title" content="OG 타이틀 상품명"/>
          <meta property="og:image" content="https://example.com/img.jpg"/>
        </head>
        <body><p>상품 설명</p></body>
        </html>
        """
        mock_resp = mock.MagicMock()
        mock_resp.text = html
        mock_resp.raise_for_status = mock.MagicMock()

        with mock.patch("requests.get", return_value=mock_resp):
            result = scrape_product_page("https://example.com/product", force_refresh=True)

        assert result["title"] == "OG 타이틀 상품명"
        assert "https://example.com/img.jpg" in result["images"]
        assert result["_scraped"] is True

    def test_scraping_failure_returns_empty(self):
        from src.ai_listing.url_scraper import scrape_product_page
        import unittest.mock as mock

        with mock.patch("requests.get", side_effect=Exception("connection refused")):
            result = scrape_product_page("https://example.com/product", force_refresh=True)

        assert result["_scraped"] is False
        assert result["_error"] is not None
        assert result["title"] == ""


# ── 소재/색상/사이즈 후보 추출 ───────────────────────────────────────────────

class TestCandidateExtraction:
    def test_material_extraction(self):
        from src.ai_listing.url_scraper import _extract_candidates_from_text, _MATERIAL_KEYWORDS

        text = "소재: 면 95% + 스판덱스 5%, 부드러운 폴리에스터 안감"
        result = _extract_candidates_from_text(text, _MATERIAL_KEYWORDS)
        assert "면" in result
        assert "스판덱스" in result
        assert "폴리에스터" in result

    def test_color_extraction(self):
        from src.ai_listing.url_scraper import _extract_candidates_from_text, _COLOR_KEYWORDS

        text = "색상: 블랙 / 화이트 / 네이비 / 그레이"
        result = _extract_candidates_from_text(text, _COLOR_KEYWORDS)
        assert "블랙" in result
        assert "화이트" in result
        assert "네이비" in result

    def test_size_extraction(self):
        from src.ai_listing.url_scraper import _extract_sizes_from_text

        text = "사이즈: S, M, L, XL, XXL"
        result = _extract_sizes_from_text(text)
        assert "S" in result or "M" in result or "L" in result


# ── 캐시 ────────────────────────────────────────────────────────────────────

class TestScrapeCache:
    def test_cache_hit_returns_same_result(self):
        from src.ai_listing.url_scraper import scrape_product_page, _scraper_cache
        import unittest.mock as mock

        html = "<html><head><title>캐시 테스트</title></head><body></body></html>"
        mock_resp = mock.MagicMock()
        mock_resp.text = html
        mock_resp.raise_for_status = mock.MagicMock()

        url = "https://example.com/cache-test-unique-url"
        with mock.patch("requests.get", return_value=mock_resp) as m:
            result1 = scrape_product_page(url, force_refresh=True)
            result2 = scrape_product_page(url, force_refresh=False)

        # 두 번째 호출은 캐시에서 반환 (requests.get 한 번만 호출)
        assert m.call_count == 1
        assert result1["title"] == result2["title"]

    def test_cache_stats(self):
        from src.ai_listing.url_scraper import scraper_cache_stats

        stats = scraper_cache_stats()
        assert "total" in stats
        assert "active" in stats
        assert "ttl_hours" in stats

    def test_invalid_url_returns_error(self):
        from src.ai_listing.url_scraper import scrape_product_page

        result = scrape_product_page("not-a-valid-url")
        assert result["_scraped"] is False
        assert result["_error"] is not None

    def test_disabled_scraper_returns_empty(self, monkeypatch):
        monkeypatch.setenv("AI_LISTING_URL_SCRAPER_ENABLED", "0")
        import importlib
        import src.ai_listing.url_scraper as mod
        # reload to pick up env var
        importlib.reload(mod)
        result = mod.scrape_product_page("https://example.com/test", force_refresh=True)
        assert result["_scraped"] is False
        # restore
        importlib.reload(mod)
