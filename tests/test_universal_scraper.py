"""tests/test_universal_scraper.py — 범용 수집기 테스트 (Phase 135).

JSON-LD / OG / Microdata / Heuristic 각 케이스 검증.
ADAPTER_DRY_RUN=1 환경에서 실행.
"""
from __future__ import annotations

import json
import os
import sys
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("ADAPTER_DRY_RUN", "1")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.collectors.universal_scraper import (
    ScrapedProduct,
    UniversalScraper,
    _detect_currency_from_symbol,
    _extract_domain,
    _is_safe_url,
    _parse_price,
)


# ---------------------------------------------------------------------------
# ScrapedProduct 기본 테스트
# ---------------------------------------------------------------------------

class TestScrapedProduct:
    def test_to_dict_basic(self):
        p = ScrapedProduct(
            source_url="https://example.com/p",
            domain="example.com",
            title="테스트 상품",
            description="설명",
            images=["https://example.com/img.jpg"],
            price=Decimal("99.99"),
            currency="USD",
            brand="TestBrand",
            extraction_method="json-ld",
            confidence=0.9,
        )
        d = p.to_dict()
        assert d["title"] == "테스트 상품"
        assert d["price"] == "99.99"
        assert d["currency"] == "USD"
        assert d["confidence"] == 0.9
        assert len(d["images"]) == 1

    def test_to_dict_no_price(self):
        p = ScrapedProduct(source_url="x", domain="x.com", title="T", description="")
        assert p.to_dict()["price"] is None

    def test_needs_adapter_true(self):
        p = ScrapedProduct(source_url="x", domain="x.com", title="T", description="", confidence=0.3)
        assert p.needs_adapter is True

    def test_needs_adapter_false(self):
        p = ScrapedProduct(source_url="x", domain="x.com", title="T", description="", confidence=0.7)
        assert p.needs_adapter is False


# ---------------------------------------------------------------------------
# 유틸 함수 테스트
# ---------------------------------------------------------------------------

class TestUtils:
    def test_parse_price_usd(self):
        assert _parse_price("29.99") == Decimal("29.99")

    def test_parse_price_with_comma(self):
        assert _parse_price("1,299") == Decimal("1299")

    def test_parse_price_with_symbol(self):
        assert _parse_price("$99.99") == Decimal("99.99")

    def test_parse_price_yen(self):
        assert _parse_price("¥33,000") == Decimal("33000")

    def test_parse_price_empty(self):
        assert _parse_price("") is None

    def test_parse_price_invalid(self):
        assert _parse_price("가격미정") is None

    def test_extract_domain_with_www(self):
        assert _extract_domain("https://www.aloyoga.com/products/test") == "aloyoga.com"

    def test_extract_domain_no_www(self):
        assert _extract_domain("https://pleasuresnow.com/products/tee") == "pleasuresnow.com"

    def test_is_safe_url_valid(self):
        assert _is_safe_url("https://aloyoga.com/p/item") is True

    def test_is_safe_url_localhost_blocked(self):
        assert _is_safe_url("http://localhost:5000/admin") is False

    def test_is_safe_url_private_ip_blocked(self):
        assert _is_safe_url("http://192.168.1.1/api") is False

    def test_is_safe_url_internal_blocked(self):
        assert _is_safe_url("http://10.0.0.1/secret") is False

    def test_detect_currency_usd(self):
        assert _detect_currency_from_symbol("$99.99") == "USD"

    def test_detect_currency_jpy(self):
        assert _detect_currency_from_symbol("¥33000") == "JPY"

    def test_detect_currency_krw(self):
        assert _detect_currency_from_symbol("₩99000") == "KRW"


# ---------------------------------------------------------------------------
# UniversalScraper 파싱 테스트 (HTML fixture)
# ---------------------------------------------------------------------------

class TestUniversalScraperJsonLD:
    """JSON-LD 파싱 테스트."""

    def _make_soup(self, html: str):
        from bs4 import BeautifulSoup
        return BeautifulSoup(html, "html.parser")

    def test_parse_jsonld_basic_product(self):
        html = """
        <html><head>
        <script type="application/ld+json">
        {"@type":"Product","name":"Alo Yoga Legging","description":"최고의 레깅스",
         "image":["https://cdn.alo.com/img.jpg"],
         "offers":{"price":"98.00","priceCurrency":"USD","availability":"https://schema.org/InStock"}}
        </script>
        </head></html>
        """
        scraper = UniversalScraper()
        soup = self._make_soup(html)
        result = scraper._parse_jsonld(soup, "https://aloyoga.com/p", "aloyoga.com")
        assert result is not None
        assert result.title == "Alo Yoga Legging"
        assert result.price == Decimal("98.00")
        assert result.currency == "USD"
        assert result.in_stock is True
        assert result.confidence >= 0.5
        assert result.extraction_method == "json-ld"

    def test_parse_jsonld_no_product_type(self):
        html = """
        <script type="application/ld+json">
        {"@type":"Organization","name":"Some Org"}
        </script>
        """
        scraper = UniversalScraper()
        soup = self._make_soup(html)
        result = scraper._parse_jsonld(soup, "https://example.com", "example.com")
        assert result is None

    def test_parse_jsonld_missing_name(self):
        html = """
        <script type="application/ld+json">
        {"@type":"Product","description":"desc only"}
        </script>
        """
        scraper = UniversalScraper()
        soup = self._make_soup(html)
        result = scraper._parse_jsonld(soup, "https://example.com", "example.com")
        assert result is None

    def test_parse_jsonld_list_format(self):
        html = """
        <script type="application/ld+json">
        [{"@type":"Product","name":"List Product","offers":{"price":"50","priceCurrency":"USD"}}]
        </script>
        """
        scraper = UniversalScraper()
        soup = self._make_soup(html)
        result = scraper._parse_jsonld(soup, "https://example.com", "example.com")
        assert result is not None
        assert result.title == "List Product"


class TestUniversalScraperOpenGraph:
    """Open Graph 파싱 테스트."""

    def _make_soup(self, html: str):
        from bs4 import BeautifulSoup
        return BeautifulSoup(html, "html.parser")

    def test_parse_og_basic(self):
        html = """
        <html><head>
        <meta property="og:title" content="Pleasures Tee">
        <meta property="og:image" content="https://cdn.pleasuresnow.com/tee.jpg">
        <meta property="og:description" content="최고의 티셔츠">
        <meta property="product:price:amount" content="65.00">
        <meta property="product:price:currency" content="USD">
        </head></html>
        """
        scraper = UniversalScraper()
        soup = self._make_soup(html)
        result = scraper._parse_opengraph(soup, "https://pleasuresnow.com/p", "pleasuresnow.com")
        assert result is not None
        assert result.title == "Pleasures Tee"
        assert result.price == Decimal("65.00")
        assert result.extraction_method == "og"
        assert result.confidence >= 0.5

    def test_parse_og_no_title(self):
        html = """<html><head>
        <meta property="og:image" content="img.jpg">
        </head></html>"""
        scraper = UniversalScraper()
        soup = self._make_soup(html)
        result = scraper._parse_opengraph(soup, "https://example.com", "example.com")
        assert result is None


class TestUniversalScraperMicrodata:
    """Microdata 파싱 테스트."""

    def _make_soup(self, html: str):
        from bs4 import BeautifulSoup
        return BeautifulSoup(html, "html.parser")

    def test_parse_microdata_basic(self):
        html = """
        <div itemscope itemtype="http://schema.org/Product">
          <span itemprop="name">Porter Tote</span>
          <span itemprop="description">일본 PORTER 가방</span>
          <span itemprop="price" content="33000">¥33,000</span>
          <span itemprop="priceCurrency" content="JPY">JPY</span>
        </div>
        """
        scraper = UniversalScraper()
        soup = self._make_soup(html)
        result = scraper._parse_microdata(soup, "https://yoshidakaban.com/p", "yoshidakaban.com")
        assert result is not None
        assert result.title == "Porter Tote"
        assert result.extraction_method == "microdata"

    def test_parse_microdata_no_schema(self):
        html = "<div><p>no schema here</p></div>"
        scraper = UniversalScraper()
        soup = self._make_soup(html)
        result = scraper._parse_microdata(soup, "https://example.com", "example.com")
        assert result is None


class TestUniversalScraperHeuristic:
    """Heuristic 파싱 테스트."""

    def _make_soup(self, html: str):
        from bs4 import BeautifulSoup
        return BeautifulSoup(html, "html.parser")

    def test_heuristic_basic(self):
        html = """
        <html><head><title>상품 이름 - 브랜드</title>
        <meta name="description" content="상품 설명">
        </head><body>
        <h1>상품 이름</h1>
        <p class="price">$45.00</p>
        <img src="https://example.com/img.jpg">
        </body></html>
        """
        scraper = UniversalScraper()
        soup = self._make_soup(html)
        result = scraper._heuristic(soup, "https://example.com/p", "example.com")
        assert result is not None
        assert "상품" in result.title
        assert result.extraction_method == "heuristic"
        assert result.price == Decimal("45.00")

    def test_heuristic_empty_page(self):
        html = "<html><head></head><body></body></html>"
        scraper = UniversalScraper()
        soup = self._make_soup(html)
        result = scraper._heuristic(soup, "https://example.com", "example.com")
        assert result is not None
        assert result.extraction_method == "heuristic"
        assert result.confidence < 0.5


class TestUniversalScraperFetch:
    """fetch() 메서드 통합 테스트 (DRY_RUN=1 환경)."""

    def test_fetch_dry_run_returns_empty(self):
        """DRY_RUN=1: HTTP 없이 빈 ScrapedProduct 반환."""
        scraper = UniversalScraper()
        with patch("src.collectors.universal_scraper._fetch_html", return_value=None):
            result = scraper.fetch("https://aloyoga.com/products/legging")
        assert result.domain == "aloyoga.com"
        assert result.confidence == 0.0

    def test_fetch_with_html_uses_jsonld(self):
        """HTML이 있으면 JSON-LD 파싱 우선."""
        html = """
        <html><head>
        <script type="application/ld+json">
        {"@type":"Product","name":"Test Item","offers":{"price":"100","priceCurrency":"USD"}}
        </script>
        </head></html>
        """
        scraper = UniversalScraper()
        with patch("src.collectors.universal_scraper._fetch_html", return_value=html):
            result = scraper.fetch("https://example.com/p")
        assert result.title == "Test Item"
        assert result.extraction_method == "json-ld"
