from __future__ import annotations


def test_all_phase151_market_adapters_implement_interface():
    from src.markets.adapters.base import ListingPayload, MarketAdapter
    from src.markets.adapters.coupang_wing import CoupangWingAdapter
    from src.markets.adapters.eleven_st import ElevenStAdapter
    from src.markets.adapters.mock import MockMarketAdapter
    from src.markets.adapters.naver_commerce import NaverCommerceAdapter

    adapters = [
        MockMarketAdapter(),
        CoupangWingAdapter(),
        ElevenStAdapter(),
        NaverCommerceAdapter(),
    ]
    payload = ListingPayload(title="t", description="d", price_krw=1000)

    for adapter in adapters:
        assert isinstance(adapter, MarketAdapter)
        assert adapter.create_listing(payload).market == adapter.market
        assert adapter.update_inventory("SKU-1", 1) is True
        assert adapter.get_order_status("ORDER-1").status
