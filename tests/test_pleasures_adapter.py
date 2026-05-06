"""tests/test_pleasures_adapter.py — Pleasures Now 어댑터 테스트 (Phase 135).

Shopify /products/<slug>.json 응답 mock 테스트.
"""
from __future__ import annotations

import os
import sys
from decimal import Decimal
from unittest.mock import patch, MagicMock

import pytest

os.environ.setdefault("ADAPTER_DRY_RUN", "1")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.collectors.adapters.pleasures_adapter import (
    PleasuresAdapter,
    _shopify_product_json_url,
    _fetch_shopify_json,
)


class TestShopifyUtils:
    def test_json_url_basic(self):
        url = "https://pleasuresnow.com/products/some-tee"
        json_url = _shopify_product_json_url(url)
        assert json_url == "https://pleasuresnow.com/products/some-tee.json"

    def test_json_url_with_query(self):
        url = "https://pleasuresnow.com/products/hoodie?color=black"
        json_url = _shopify_product_json_url(url)
        assert json_url == "https://pleasuresnow.com/products/hoodie.json"

    def test_json_url_non_product(self):
        url = "https://pleasuresnow.com/collections/sale"
        json_url = _shopify_product_json_url(url)
        assert json_url is None


class TestPleasuresAdapterDryRun:
    def setup_method(self):
        self.adapter = PleasuresAdapter()

    def test_name_and_domain(self):
        assert self.adapter.name == "pleasures"
        assert self.adapter.domain == "pleasuresnow.com"

    def test_fetch_dry_run(self):
        result = self.adapter.fetch("https://pleasuresnow.com/products/tee")
        assert result.title == "Pleasures DRY_RUN 상품"
        assert result.price == Decimal("65.00")
        assert "Size" in [o["name"] for o in result.options]


class TestPleasuresAdapterShopifyJson:
    def setup_method(self):
        self.adapter = PleasuresAdapter()

    def test_parse_shopify_json_full(self):
        product = {
            "title": "Pleasures Tee Shirt",
            "body_html": "<p>최고의 티셔츠입니다.</p>",
            "vendor": "Pleasures",
            "images": [{"src": "https://cdn.pleasuresnow.com/img1.jpg"}],
            "variants": [
                {"price": "65.00", "sku": "PLU-001", "available": True}
            ],
            "options": [
                {"name": "Size", "values": ["S", "M", "L", "XL"]},
                {"name": "Color", "values": ["Black", "White"]},
            ],
        }
        result = self.adapter._parse_shopify_json(product, "https://pleasuresnow.com/products/tee", "pleasuresnow.com")
        assert result.title == "Pleasures Tee Shirt"
        assert result.price == Decimal("65.00")
        assert result.sku == "PLU-001"
        assert result.in_stock is True
        assert len(result.options) == 2
        assert result.options[0]["name"] == "Size"
        assert "S" in result.options[0]["values"]
        assert "adapter:pleasures:shopify-json" in result.extraction_method
        assert result.confidence >= 0.9

    def test_parse_shopify_json_no_images(self):
        product = {
            "title": "No Images",
            "body_html": "",
            "vendor": "Pleasures",
            "images": [],
            "variants": [{"price": "50.00", "sku": "X", "available": False}],
            "options": [],
        }
        result = self.adapter._parse_shopify_json(product, "https://pleasuresnow.com/products/x", "pleasuresnow.com")
        assert result.title == "No Images"
        assert result.in_stock is False

    def test_parse_shopify_json_strips_html(self):
        product = {
            "title": "Clean Desc",
            "body_html": "<p>Paragraph</p><br><strong>Bold</strong>",
            "vendor": "Pleasures",
            "images": [],
            "variants": [{"price": "30.00", "available": True}],
            "options": [],
        }
        result = self.adapter._parse_shopify_json(product, "https://pleasuresnow.com/products/p", "pleasuresnow.com")
        assert "<p>" not in result.description
        assert "Paragraph" in result.description
