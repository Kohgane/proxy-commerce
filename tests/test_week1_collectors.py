"""tests/test_week1_collectors.py — Tests for ALO/lululemon collector MVPs."""
from __future__ import annotations

import json
from typing import Any, Dict
from unittest.mock import patch

import pytest

from collectors.alo import AloPipeline
from collectors.lululemon import LululemonPipeline
from schemas.product import Product

# ---------------------------------------------------------------------------
# Helpers — sample HTML pages
# ---------------------------------------------------------------------------

_ALO_JSON_LD_HTML = """
<html><head>
<title>High-Waist Airlift Legging | ALO Yoga</title>
<script type="application/ld+json">
{
  "@type": "Product",
  "name": "High-Waist Airlift Legging",
  "image": ["https://cdn.aloyoga.com/img/legging1.jpg", "https://cdn.aloyoga.com/img/legging2.jpg"],
  "description": "Ultimate performance legging.",
  "offers": {"@type": "Offer", "price": "128.00", "priceCurrency": "USD", "availability": "https://schema.org/InStock"},
  "hasVariant": [
    {"color": "Black", "size": "XS"},
    {"color": "Black", "size": "S"},
    {"color": "Ivory", "size": "XS"}
  ]
}
</script>
</head><body></body></html>
"""

_LULULEMON_JSON_LD_HTML = """
<html><head>
<title>Align Pant 28" | lululemon</title>
<script type="application/ld+json">
{
  "@type": "Product",
  "name": "Align Pant 28\\"",
  "image": ["https://images.lululemon.com/is/image/lululemon/LW5CQAS_0001_1.jpg"],
  "description": "Super-soft yoga pant.",
  "offers": {"@type": "Offer", "price": "98.00", "priceCurrency": "USD", "availability": "https://schema.org/InStock"}
}
</script>
</head><body></body></html>
"""

_FALLBACK_HTML = """
<html><head>
<title>Fallback Product | ALO</title>
<meta property="og:image" content="https://cdn.aloyoga.com/img/fallback.jpg" />
</head><body>
<script>var price = "79.00";</script>
</body></html>
"""


# ---------------------------------------------------------------------------
# ALO Pipeline tests
# ---------------------------------------------------------------------------

class TestAloPipeline:
    def setup_method(self):
        self.pipeline = AloPipeline()

    def test_parse_json_ld(self):
        parsed = self.pipeline.parse(_ALO_JSON_LD_HTML)
        assert parsed["title"] == "High-Waist Airlift Legging"
        assert float(parsed["price"]) == 128.0
        assert parsed["currency"] == "USD"
        assert len(parsed["images"]) >= 1
        assert parsed["in_stock"] is True
        assert "color" in parsed["options"]
        assert "Black" in parsed["options"]["color"]

    def test_parse_fallback_regex(self):
        parsed = self.pipeline.parse(_FALLBACK_HTML)
        assert "Fallback Product" in parsed["title"]
        assert len(parsed["images"]) >= 1

    def test_normalize_produces_product_fields(self):
        parsed = self.pipeline.parse(_ALO_JSON_LD_HTML)
        parsed["source_id"] = "high-waist-airlift-legging"
        parsed["source_url"] = "https://www.aloyoga.com/products/high-waist-airlift-legging"
        normalized = self.pipeline.normalize(parsed)

        assert normalized["source"] == "alo"
        assert normalized["brand"] == "ALO Yoga"
        assert normalized["title"] == "High-Waist Airlift Legging"
        assert normalized["cost_price"] == 128.0
        assert normalized["currency"] == "USD"
        assert len(normalized["images"]) >= 1
        assert isinstance(normalized["options"], list)

    def test_validate_returns_product(self):
        parsed = self.pipeline.parse(_ALO_JSON_LD_HTML)
        parsed["source_id"] = "high-waist-airlift-legging"
        parsed["source_url"] = "https://www.aloyoga.com/products/high-waist-airlift-legging"
        normalized = self.pipeline.normalize(parsed)
        product = self.pipeline.validate(normalized)
        assert isinstance(product, Product)
        assert product.source == "alo"
        assert product.cost_price == 128.0

    def test_run_one_returns_product_via_mock(self):
        url = "https://www.aloyoga.com/products/high-waist-airlift-legging"
        with patch.object(AloPipeline, "fetch", return_value=_ALO_JSON_LD_HTML):
            product = self.pipeline.run_one(url)
        assert isinstance(product, Product)
        assert product.source == "alo"

    def test_run_one_returns_none_on_fetch_error(self):
        url = "https://www.aloyoga.com/products/bad"
        with patch.object(AloPipeline, "fetch", side_effect=RuntimeError("timeout")):
            product = self.pipeline.run_one(url)
        assert product is None

    def test_normalize_no_images_uses_placeholder(self):
        parsed = {
            "title": "Test",
            "price": "50",
            "currency": "USD",
            "images": [],
            "options": {},
            "in_stock": True,
            "description": None,
            "source_id": "test-product",
            "source_url": "https://www.aloyoga.com/products/test",
        }
        normalized = self.pipeline.normalize(parsed)
        assert len(normalized["images"]) >= 1


# ---------------------------------------------------------------------------
# lululemon Pipeline tests
# ---------------------------------------------------------------------------

class TestLululemonPipeline:
    def setup_method(self):
        self.pipeline = LululemonPipeline()

    def test_parse_json_ld(self):
        parsed = self.pipeline.parse(_LULULEMON_JSON_LD_HTML)
        assert "Align Pant" in parsed["title"]
        assert float(parsed["price"]) == 98.0
        assert parsed["currency"] == "USD"
        assert len(parsed["images"]) >= 1
        assert parsed["in_stock"] is True

    def test_normalize_produces_product_fields(self):
        parsed = self.pipeline.parse(_LULULEMON_JSON_LD_HTML)
        parsed["source_id"] = "LW5CQAS"
        parsed["source_url"] = "https://www.lululemon.com/en-us/p/align-pant-28/LW5CQAS.html"
        normalized = self.pipeline.normalize(parsed)

        assert normalized["source"] == "lululemon"
        assert normalized["brand"] == "lululemon"
        assert "Align Pant" in normalized["title"]
        assert normalized["cost_price"] == 98.0

    def test_run_one_returns_product_via_mock(self):
        url = "https://www.lululemon.com/en-us/p/align-pant-28/LW5CQAS.html"
        with patch.object(LululemonPipeline, "fetch", return_value=_LULULEMON_JSON_LD_HTML):
            product = self.pipeline.run_one(url)
        assert isinstance(product, Product)
        assert product.source == "lululemon"

    def test_run_one_returns_none_on_fetch_error(self):
        url = "https://www.lululemon.com/en-us/p/bad/BADSKU.html"
        with patch.object(LululemonPipeline, "fetch", side_effect=RuntimeError("timeout")):
            product = self.pipeline.run_one(url)
        assert product is None
