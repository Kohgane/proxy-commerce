"""Shopee adapter stub (Phase 180 foundation)."""
from __future__ import annotations

import os

from .base import ListingPayload, ListingResult, MarketAdapter, OrderStatus


class ShopeeAdapter(MarketAdapter):
    market = "shopee"
    country = "SG"
    currency = "SGD"
    locale = "en-SG"
    region = "동남아"

    def is_configured(self) -> bool:
        return all((os.getenv("SHOPEE_PARTNER_ID"), os.getenv("SHOPEE_PARTNER_KEY"), os.getenv("SHOPEE_SHOP_ID")))

    def validate_listing(self, payload: ListingPayload) -> ListingResult:
        if not self.is_configured():
            return self._mock_result(
                "Shopee credentials are missing. Validation is unavailable in stub mode.",
                ok=False,
                raw={"status": "not_configured", "simulated": True},
            )
        return self._mock_result(
            "Shopee adapter scaffold is ready. TODO: implement OpenAPI item schema validation.",
            ok=False,
            raw={"status": "stub_pending", "simulated": True},
        )

    def upload_product(self, payload: ListingPayload) -> ListingResult:
        return self._mock_result(
            "Shopee upload is not connected yet. TODO: implement Shopee OpenAPI product create flow.",
            ok=False,
            raw={"status": "stub_pending", "simulated": True},
        )

    def create_listing(self, payload: ListingPayload) -> ListingResult:
        return self.upload_product(payload)

    def update_inventory(self, sku: str, qty: int) -> bool:
        return False

    def get_order_status(self, external_order_id: str) -> OrderStatus:
        return OrderStatus(external_order_id=external_order_id, status="stub")
