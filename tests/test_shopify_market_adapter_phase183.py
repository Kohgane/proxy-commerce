from __future__ import annotations

from unittest.mock import Mock

import pytest


def _mock_response(status_code: int, body: dict, headers: dict | None = None):
    response = Mock()
    response.status_code = status_code
    response.json.return_value = body
    response.headers = headers or {}
    response.reason = "mock"
    return response


@pytest.fixture
def shopify_env(monkeypatch):
    monkeypatch.setenv("SHOPIFY_SHOP", "phase183-test.myshopify.com")
    monkeypatch.setenv("SHOPIFY_ACCESS_TOKEN", "shpat_test_token")
    monkeypatch.setenv("SHOPIFY_ADMIN_API_VERSION", "2024-10")
    monkeypatch.setenv("SHOPIFY_SHOP_CURRENCY", "USD")
    monkeypatch.setenv("SHOPIFY_SHOP_LOCALE", "en-US")


@pytest.fixture(autouse=True)
def _clear_idempotency_cache():
    from src.markets.adapters.shopify import ShopifyAdapter

    ShopifyAdapter._idempotency_map.clear()


def test_is_configured(monkeypatch):
    from src.markets.adapters.shopify import ShopifyAdapter

    monkeypatch.delenv("SHOPIFY_SHOP", raising=False)
    monkeypatch.delenv("SHOPIFY_ACCESS_TOKEN", raising=False)
    assert ShopifyAdapter().is_configured() is False

    monkeypatch.setenv("SHOPIFY_SHOP", "test.myshopify.com")
    monkeypatch.setenv("SHOPIFY_ACCESS_TOKEN", "shpat_token")
    assert ShopifyAdapter().is_configured() is True


def test_validate_listing_errors(shopify_env):
    from src.markets.adapters.base import ListingPayload
    from src.markets.adapters.shopify import ShopifyAdapter

    payload = ListingPayload(title="", description="", price=-1, currency="USD", qty=-1)
    result = ShopifyAdapter().validate_listing(payload)
    assert result.ok is False
    assert result.raw["status"] == "invalid_payload"
    assert len(result.raw["errors"]) >= 2


def test_validate_listing_currency_warning(shopify_env):
    from src.markets.adapters.base import ListingPayload
    from src.markets.adapters.shopify import ShopifyAdapter

    payload = ListingPayload(title="상품", description="desc", price=10000, currency="KRW")
    result = ShopifyAdapter().validate_listing(payload)
    assert result.ok is True
    assert result.raw["status"] == "validated"
    assert result.raw["warnings"]


def test_upload_product_success_create(shopify_env):
    from src.markets.adapters.base import ListingPayload
    from src.markets.adapters.shopify import ShopifyAdapter

    session = Mock()
    session.request.side_effect = [
        _mock_response(200, {"shop": {"currency": "USD", "primary_locale": "en-US", "country_code": "US"}}),
        _mock_response(201, {"product": {"id": 1234, "handle": "phase183"}}),
    ]
    adapter = ShopifyAdapter(session=session, sleep_fn=lambda _: None)

    payload = ListingPayload(
        title="원문 제목",
        description="원문 설명",
        price=25,
        currency="USD",
        sku="SKU-183",
        qty=3,
        options={"images": ["https://example.com/p.jpg"]},
    )
    result = adapter.upload_product(payload)
    assert result.ok is True
    assert result.external_id == "1234"
    assert result.raw["admin_url"].endswith("/1234")


def test_upload_product_retries_on_429(shopify_env):
    from src.markets.adapters.base import ListingPayload
    from src.markets.adapters.shopify import ShopifyAdapter

    session = Mock()
    session.request.side_effect = [
        _mock_response(200, {"shop": {"currency": "USD", "primary_locale": "en-US", "country_code": "US"}}),
        _mock_response(429, {"errors": "Too Many Requests"}, headers={"Retry-After": "0"}),
        _mock_response(201, {"product": {"id": 999, "handle": "rate-limit-ok"}}),
    ]
    adapter = ShopifyAdapter(session=session, sleep_fn=lambda _: None)
    payload = ListingPayload(title="Retry", description="desc", price=10, currency="USD")
    result = adapter.upload_product(payload)
    assert result.ok is True
    assert result.external_id == "999"


def test_upload_product_idempotent_update(shopify_env):
    from src.markets.adapters.base import ListingPayload
    from src.markets.adapters.shopify import ShopifyAdapter

    session = Mock()
    session.request.side_effect = [
        _mock_response(200, {"shop": {"currency": "USD", "primary_locale": "en-US", "country_code": "US"}}),
        _mock_response(201, {"product": {"id": 555, "handle": "first"}}),
        _mock_response(200, {"shop": {"currency": "USD", "primary_locale": "en-US", "country_code": "US"}}),
        _mock_response(200, {"product": {"id": 555, "handle": "first"}}),
    ]
    adapter = ShopifyAdapter(session=session, sleep_fn=lambda _: None)
    payload = ListingPayload(
        title="Idempotent Product",
        description="desc",
        price=30,
        currency="USD",
        sku="SKU-IDEMPOTENT",
    )

    first = adapter.upload_product(payload)
    second = adapter.upload_product(payload)
    assert first.ok and second.ok
    assert second.raw["status"] == "updated"
