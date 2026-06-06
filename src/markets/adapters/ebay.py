"""eBay adapter stub (Phase 180 foundation)."""
from __future__ import annotations

import os

from .base import ListingPayload, ListingResult, MarketAdapter, OrderStatus


class EbayAdapter(MarketAdapter):
    market = "ebay"
    country = "GB"
    currency = "GBP"
    locale = "en-GB"
    region = "유럽"

    def is_configured(self) -> bool:
        return all((os.getenv("EBAY_CLIENT_ID"), os.getenv("EBAY_CLIENT_SECRET"), os.getenv("EBAY_REFRESH_TOKEN")))

    def validate_listing(self, payload: ListingPayload) -> ListingResult:
        if not self.is_configured():
            return self._mock_result(
                "eBay credentials are missing. Validation is unavailable in stub mode.",
                ok=False,
                raw={"status": "not_configured", "simulated": True},
            )
        return self._mock_result(
            "eBay adapter scaffold is ready. TODO: implement Inventory API validation.",
            ok=False,
            raw={"status": "stub_pending", "simulated": True},
        )

    def upload_product(self, payload: ListingPayload) -> ListingResult:
        return self._mock_result(
            "eBay upload is not connected yet. TODO: implement eBay Inventory/Offer API flow.",
            ok=False,
            raw={"status": "stub_pending", "simulated": True},
        )

    def create_listing(self, payload: ListingPayload) -> ListingResult:
        return self.upload_product(payload)

    def update_inventory(self, sku: str, qty: int) -> bool:
        return False

    def get_order_status(self, external_order_id: str) -> OrderStatus:
        return OrderStatus(external_order_id=external_order_id, status="stub")
