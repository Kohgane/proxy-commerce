"""tests/test_marketstudio_adapter.py — MarketStudio 어댑터 테스트 (Phase 135)."""
from __future__ import annotations

import json
import os
import sys
from decimal import Decimal

import pytest

os.environ.setdefault("ADAPTER_DRY_RUN", "1")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.collectors.adapters.marketstudio_adapter import MarketStudioAdapter


class TestMarketStudioAdapterDryRun:
    def setup_method(self):
        self.adapter = MarketStudioAdapter()

    def test_name_and_domain(self):
        assert self.adapter.name == "marketstudio"
        assert self.adapter.domain == "marketstudio.com"

    def test_fetch_dry_run(self):
        result = self.adapter.fetch("https://marketstudio.com/products/test-item")
        assert result.title == "MarketStudio DRY_RUN 상품"
        assert result.price == Decimal("79.00")
        assert result.confidence == 1.0


class TestMarketStudioAdapterParseJsonLD:
    def setup_method(self):
        self.adapter = MarketStudioAdapter()

    def _make_soup(self, html: str):
        from bs4 import BeautifulSoup
        return BeautifulSoup(html, "html.parser")

    def test_parse_jsonld_product(self):
        html = """
        <html><head>
        <script type="application/ld+json">
        {"@type":"Product","name":"MarketStudio 재킷",
         "description":"고급 재킷",
         "brand":{"name":"MS Brand"},
         "sku":"MS-001",
         "image":["https://marketstudio.com/img.jpg"],
         "offers":{"price":"79.00","priceCurrency":"USD","availability":"https://schema.org/InStock"}}
        </script>
        </head></html>
        """
        soup = self._make_soup(html)
        result = self.adapter._parse(soup, "https://marketstudio.com/p", "marketstudio.com")
        assert result.title == "MarketStudio 재킷"
        assert result.price == Decimal("79.00")
        assert result.brand == "MS Brand"
        assert result.sku == "MS-001"
        assert "adapter:marketstudio" in result.extraction_method

    def test_parse_css_selector_fallback(self):
        html = """
        <html><body>
        <h1 class="product-title">CSS 폴백 상품</h1>
        <span class="price__current">$55.00</span>
        <div class="product-gallery"><img src="https://marketstudio.com/gallery.jpg"></div>
        </body></html>
        """
        soup = self._make_soup(html)
        result = self.adapter._parse(soup, "https://marketstudio.com/p", "marketstudio.com")
        assert "CSS 폴백 상품" in result.title
        assert result.confidence >= 0.5

    def test_parse_empty_returns_low_confidence(self):
        html = "<html><body></body></html>"
        soup = self._make_soup(html)
        result = self.adapter._parse(soup, "https://marketstudio.com/p", "marketstudio.com")
        assert result.confidence < 0.5
