"""Naver Commerce adapter scaffold."""
from __future__ import annotations

import os

from .base import ListingPayload, ListingResult, MarketAdapter, OrderStatus
from .naver_commerce_auth import get_access_token


class NaverCommerceAdapter(MarketAdapter):
    market = "naver_commerce"

    def _live_enabled(self) -> bool:
        return (
            os.getenv("MARKET_ADAPTER_DEFAULT", "mock") == "live"
            and bool(os.getenv("NAVER_COMMERCE_CLIENT_ID"))
            and bool(os.getenv("NAVER_COMMERCE_CLIENT_SECRET"))
        )

    def create_listing(self, payload: ListingPayload) -> ListingResult:
        if not self._live_enabled():
            return self._mock_result("naver commerce mock mode")
        token = get_access_token()
        return ListingResult(ok=True, market=self.market, external_id="", message="Phase 152 pending", raw={"token_present": bool(token)})

    def update_inventory(self, sku: str, qty: int) -> bool:
        return bool(sku)

    def get_order_status(self, external_order_id: str) -> OrderStatus:
        return OrderStatus(external_order_id=external_order_id, status="mock")
