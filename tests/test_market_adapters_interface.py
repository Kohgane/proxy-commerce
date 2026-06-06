from __future__ import annotations


def test_all_phase151_market_adapters_implement_interface(monkeypatch):
    from src.markets.adapters.base import ListingPayload, MarketAdapter
    from src.markets.adapters.amazon import AmazonAdapter
    from src.markets.adapters.coupang_wing import CoupangWingAdapter
    from src.markets.adapters.ebay import EbayAdapter
    from src.markets.adapters.eleven_st import ElevenStAdapter
    from src.markets.adapters.mock import MockMarketAdapter
    from src.markets.adapters.naver_commerce import NaverCommerceAdapter
    from src.markets.adapters.shopify import ShopifyAdapter
    from src.markets.adapters.shopee import ShopeeAdapter

    for env_name in [
        "AMAZON_SP_CLIENT_ID",
        "AMAZON_SP_CLIENT_SECRET",
        "AMAZON_SP_REFRESH_TOKEN",
        "AMAZON_SP_SELLER_ID",
        "EBAY_CLIENT_ID",
        "EBAY_CLIENT_SECRET",
        "EBAY_REFRESH_TOKEN",
        "SHOPIFY_SHOP",
        "SHOPIFY_ACCESS_TOKEN",
        "SHOPEE_PARTNER_ID",
        "SHOPEE_PARTNER_KEY",
        "SHOPEE_SHOP_ID",
    ]:
        monkeypatch.delenv(env_name, raising=False)

    adapters = [
        MockMarketAdapter(),
        CoupangWingAdapter(),
        ElevenStAdapter(),
        NaverCommerceAdapter(),
    ]
    payload = ListingPayload(title="t", description="d", price=1000, currency="KRW")

    for adapter in adapters:
        assert isinstance(adapter, MarketAdapter)
        meta = adapter.marketplace_meta()
        assert meta["country"] == "KR"
        assert meta["currency"] == "KRW"
        assert meta["locale"] == "ko-KR"
        assert adapter.create_listing(payload).market == adapter.market
        assert adapter.update_inventory("SKU-1", 1) is True
        assert adapter.get_order_status("ORDER-1").status

    global_adapters = [AmazonAdapter(), EbayAdapter(), ShopifyAdapter(), ShopeeAdapter()]
    global_payload = ListingPayload(title="global", description="listing", price=10, currency="USD")
    for adapter in global_adapters:
        assert isinstance(adapter, MarketAdapter)
        assert adapter.is_configured() is False
        meta = adapter.marketplace_meta()
        assert meta["country"]
        assert meta["currency"]
        assert meta["locale"]
        assert adapter.validate_listing(global_payload).ok is False
        upload_result = adapter.upload_product(global_payload)
        assert upload_result.ok is False
        assert upload_result.raw.get("status") in {"not_configured", "stub_pending"}
