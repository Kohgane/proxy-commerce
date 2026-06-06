"""Coupang Wing adapter scaffold."""
from __future__ import annotations

from .base import ListingPayload, ListingResult, MarketAdapter, OrderStatus


class CoupangWingAdapter(MarketAdapter):
    market = "coupang"
    country = "KR"
    currency = "KRW"
    locale = "ko-KR"
    region = "동아시아"

    def is_configured(self) -> bool:
        import os

        return all(
            (
                os.getenv("COUPANG_VENDOR_ID"),
                os.getenv("COUPANG_ACCESS_KEY"),
                os.getenv("COUPANG_SECRET_KEY"),
            )
        )

    def create_listing(self, payload: ListingPayload) -> ListingResult:
        return self._mock_result("coupang mock mode")

    def update_inventory(self, sku: str, qty: int) -> bool:
        return True

    def get_order_status(self, external_order_id: str) -> OrderStatus:
        return OrderStatus(external_order_id=external_order_id, status="mock")
