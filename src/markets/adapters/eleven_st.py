"""11st adapter scaffold."""
from __future__ import annotations

from .base import ListingPayload, ListingResult, MarketAdapter, OrderStatus


class ElevenStAdapter(MarketAdapter):
    market = "11st"

    def create_listing(self, payload: ListingPayload) -> ListingResult:
        return self._mock_result("11st mock mode")

    def update_inventory(self, sku: str, qty: int) -> bool:
        return True

    def get_order_status(self, external_order_id: str) -> OrderStatus:
        return OrderStatus(external_order_id=external_order_id, status="mock")
