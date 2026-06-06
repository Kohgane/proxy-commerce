"""Mock market adapter."""
from __future__ import annotations

from .base import ListingPayload, ListingResult, MarketAdapter, OrderStatus


class MockMarketAdapter(MarketAdapter):
    market = "mock"
    country = "KR"
    currency = "KRW"
    locale = "ko-KR"
    region = "동아시아"

    def is_configured(self) -> bool:
        return True

    def create_listing(self, payload: ListingPayload) -> ListingResult:
        return self._mock_result(f"mock listing created: {payload.title}")

    def update_inventory(self, sku: str, qty: int) -> bool:
        return True

    def get_order_status(self, external_order_id: str) -> OrderStatus:
        return OrderStatus(external_order_id=external_order_id, status="mock")
