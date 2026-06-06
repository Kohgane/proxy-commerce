from __future__ import annotations


def test_upload_dispatcher_supports_shopify(monkeypatch):
    from src.seller_console import upload_dispatcher as mod

    class _FakeAdapter:
        def validate_listing(self, payload):
            from src.markets.adapters.base import ListingResult

            return ListingResult(ok=True, market="shopify", message="validated", raw={"status": "validated"})

        def upload_product(self, payload):
            from src.markets.adapters.base import ListingResult

            return ListingResult(
                ok=True,
                market="shopify",
                external_id="P-183",
                message="ok",
                raw={"status": "created", "admin_url": "https://shop/admin/products/P-183"},
            )

    monkeypatch.setattr(mod, "SUPPORTED_MARKETS", mod.SUPPORTED_MARKETS)
    monkeypatch.setitem(mod.MARKET_LABELS, "shopify", "Shopify")
    monkeypatch.setattr("src.markets.adapters.shopify.ShopifyAdapter", _FakeAdapter)

    dispatcher = mod.UploadDispatcher()
    result = dispatcher.dispatch(
        {
            "url": "https://example.com/item",
            "title": "test",
            "description": "desc",
            "price_original": 10,
            "currency": "USD",
            "sku": "SKU-1",
        },
        ["shopify"],
    )

    assert result.total == 1
    assert result.succeeded == 1
    assert result.failed == 0
    assert "P-183" in result.results[0].message


def test_upload_dispatcher_shopify_validate_failure(monkeypatch):
    from src.seller_console import upload_dispatcher as mod

    class _FakeAdapter:
        def validate_listing(self, payload):
            from src.markets.adapters.base import ListingResult

            return ListingResult(ok=False, market="shopify", message="validation failed", raw={"status": "invalid_payload"})

    monkeypatch.setattr("src.markets.adapters.shopify.ShopifyAdapter", _FakeAdapter)
    dispatcher = mod.UploadDispatcher()
    result = dispatcher.dispatch({"title": "", "price_original": 10, "currency": "USD"}, ["shopify"])
    assert result.failed == 1
    assert "validation failed" in result.results[0].message
