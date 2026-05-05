"""tests/test_woocommerce_adapter.py — WooCommerce 어댑터 테스트 (Phase 130)."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_import():
    """모듈 임포트 성공."""
    from src.seller_console.market_adapters.woocommerce_adapter import WooCommerceAdapter
    assert WooCommerceAdapter is not None


def test_marketplace_name():
    """marketplace 속성 확인."""
    from src.seller_console.market_adapters.woocommerce_adapter import WooCommerceAdapter
    adapter = WooCommerceAdapter()
    assert adapter.marketplace == "woocommerce"


def test_health_check_missing(monkeypatch):
    """API 키 미설정 시 health_check missing."""
    for k in ["WC_KEY", "WC_SECRET", "WC_URL", "WOO_CK", "WOO_CS", "WOO_BASE_URL"]:
        monkeypatch.delenv(k, raising=False)
    from src.seller_console.market_adapters.woocommerce_adapter import WooCommerceAdapter
    adapter = WooCommerceAdapter()
    result = adapter.health_check()
    assert result["status"] == "missing"


def test_health_check_dry_run(monkeypatch):
    """ADAPTER_DRY_RUN=1 시 dry_run 반환."""
    monkeypatch.setenv("WC_KEY", "ck_test_key_value_0000000000000000")
    monkeypatch.setenv("WC_SECRET", "cs_test_secret_000000000000000000")
    monkeypatch.setenv("WC_URL", "https://myshop.com")
    monkeypatch.setenv("ADAPTER_DRY_RUN", "1")
    from src.seller_console.market_adapters.woocommerce_adapter import WooCommerceAdapter
    adapter = WooCommerceAdapter()
    result = adapter.health_check()
    assert result["status"] == "dry_run"


def test_fetch_inventory_stub(monkeypatch):
    """API 키 미설정 시 빈 목록 반환."""
    for k in ["WC_KEY", "WC_SECRET", "WC_URL", "WOO_CK", "WOO_CS", "WOO_BASE_URL"]:
        monkeypatch.delenv(k, raising=False)
    from src.seller_console.market_adapters.woocommerce_adapter import WooCommerceAdapter
    adapter = WooCommerceAdapter()
    result = adapter.fetch_inventory()
    assert result == []


def test_upload_product_stub(monkeypatch):
    """API 키 미설정 시 stub 반환."""
    for k in ["WC_KEY", "WC_SECRET", "WC_URL", "WOO_CK", "WOO_CS", "WOO_BASE_URL"]:
        monkeypatch.delenv(k, raising=False)
    from src.seller_console.market_adapters.woocommerce_adapter import WooCommerceAdapter
    adapter = WooCommerceAdapter()
    result = adapter.upload_product({"name": "Test Product"})
    assert result["status"] == "stub"


def test_upload_product_dry_run(monkeypatch):
    """ADAPTER_DRY_RUN=1 시 dry_run 반환."""
    monkeypatch.setenv("WC_KEY", "ck_test_key_value_0000000000000000")
    monkeypatch.setenv("WC_SECRET", "cs_test_secret_000000000000000000")
    monkeypatch.setenv("WC_URL", "https://myshop.com")
    monkeypatch.setenv("ADAPTER_DRY_RUN", "1")
    from src.seller_console.market_adapters.woocommerce_adapter import WooCommerceAdapter
    adapter = WooCommerceAdapter()
    result = adapter.upload_product({"name": "Test Product"})
    assert result["status"] == "dry_run"


def test_alias_woo_ck_woo_cs(monkeypatch):
    """WOO_CK/WOO_CS/WOO_BASE_URL 별칭으로 api_active."""
    for k in ["WC_KEY", "WC_SECRET", "WC_URL"]:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("WOO_CK", "ck_alias_test_key_000000000000000000")
    monkeypatch.setenv("WOO_CS", "cs_alias_secret_00000000000000000000")
    monkeypatch.setenv("WOO_BASE_URL", "https://myshop.com")
    from src.seller_console.market_adapters import woocommerce_adapter as wc_mod
    import importlib
    importlib.reload(wc_mod)
    assert wc_mod._api_active() is True
