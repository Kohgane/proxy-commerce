"""tests/test_shopify_adapter.py — Shopify 어댑터 테스트 (Phase 130)."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_import():
    """모듈 임포트 성공."""
    from src.seller_console.market_adapters.shopify_adapter import ShopifyAdapter
    assert ShopifyAdapter is not None


def test_marketplace_name():
    """marketplace 속성 확인."""
    from src.seller_console.market_adapters.shopify_adapter import ShopifyAdapter
    adapter = ShopifyAdapter()
    assert adapter.marketplace == "shopify"


def test_health_check_missing(monkeypatch):
    """API 키 미설정 시 health_check missing."""
    monkeypatch.delenv("SHOPIFY_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("SHOPIFY_SHOP", raising=False)
    from src.seller_console.market_adapters.shopify_adapter import ShopifyAdapter
    adapter = ShopifyAdapter()
    result = adapter.health_check()
    assert result["status"] == "missing"


def test_health_check_dry_run(monkeypatch):
    """ADAPTER_DRY_RUN=1 시 dry_run 반환."""
    monkeypatch.setenv("SHOPIFY_ACCESS_TOKEN", "shpat_test_token_value")
    monkeypatch.setenv("SHOPIFY_SHOP", "testshop.myshopify.com")
    monkeypatch.setenv("ADAPTER_DRY_RUN", "1")
    from src.seller_console.market_adapters.shopify_adapter import ShopifyAdapter
    adapter = ShopifyAdapter()
    result = adapter.health_check()
    assert result["status"] == "dry_run"


def test_fetch_inventory_stub(monkeypatch):
    """API 키 미설정 시 빈 목록 반환."""
    monkeypatch.delenv("SHOPIFY_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("SHOPIFY_SHOP", raising=False)
    from src.seller_console.market_adapters.shopify_adapter import ShopifyAdapter
    adapter = ShopifyAdapter()
    result = adapter.fetch_inventory()
    assert result == []


def test_upload_product_stub(monkeypatch):
    """API 키 미설정 시 stub 반환."""
    monkeypatch.delenv("SHOPIFY_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("SHOPIFY_SHOP", raising=False)
    from src.seller_console.market_adapters.shopify_adapter import ShopifyAdapter
    adapter = ShopifyAdapter()
    result = adapter.upload_product({"title": "Test Product"})
    assert result["status"] == "stub"


def test_upload_product_dry_run(monkeypatch):
    """ADAPTER_DRY_RUN=1 시 dry_run 반환."""
    monkeypatch.setenv("SHOPIFY_ACCESS_TOKEN", "shpat_test_token_value")
    monkeypatch.setenv("SHOPIFY_SHOP", "testshop.myshopify.com")
    monkeypatch.setenv("ADAPTER_DRY_RUN", "1")
    from src.seller_console.market_adapters.shopify_adapter import ShopifyAdapter
    adapter = ShopifyAdapter()
    result = adapter.upload_product({"title": "Test Product"})
    assert result["status"] == "dry_run"
