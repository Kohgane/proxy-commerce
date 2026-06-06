"""Shopify adapter stub (Phase 180 foundation)."""
from __future__ import annotations

import os

from .base import ListingPayload, ListingResult, MarketAdapter, OrderStatus


class ShopifyAdapter(MarketAdapter):
    market = "shopify"
    country = "US"
    currency = "USD"
    locale = "en-US"
    region = "북미"

    def is_configured(self) -> bool:
        return all((os.getenv("SHOPIFY_SHOP"), os.getenv("SHOPIFY_ACCESS_TOKEN")))

    def validate_listing(self, payload: ListingPayload) -> ListingResult:
        if not self.is_configured():
            return self._mock_result(
                "Shopify credentials are missing. Validation is unavailable in stub mode.",
                ok=False,
                raw={"status": "not_configured", "simulated": True},
            )
        return self._mock_result(
            "Shopify adapter scaffold is ready. TODO: implement Admin GraphQL product validation.",
            ok=False,
            raw={"status": "stub_pending", "simulated": True},
        )

    def upload_product(self, payload: ListingPayload) -> ListingResult:
        return self._mock_result(
            "Shopify upload is not connected yet. TODO: implement Admin API productCreate flow.",
            ok=False,
            raw={"status": "stub_pending", "simulated": True},
        )

    def create_listing(self, payload: ListingPayload) -> ListingResult:
        return self.upload_product(payload)

    def update_inventory(self, sku: str, qty: int) -> bool:
        return False

    def get_order_status(self, external_order_id: str) -> OrderStatus:
        return OrderStatus(external_order_id=external_order_id, status="stub")
