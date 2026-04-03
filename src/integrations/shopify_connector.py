"""src/integrations/shopify_connector.py — Shopify 연동 모의 구현."""
from __future__ import annotations

from typing import List

from .integration_connector import IntegrationConnector


class ShopifyConnector(IntegrationConnector):
    """Shopify API 연동 모의 구현 (실제 API 호출 없음)."""

    name = "shopify"

    def __init__(self, shop: str = "mock.myshopify.com", access_token: str = "mock-token") -> None:
        self.shop = shop
        self.access_token = access_token
        self._connected = False

    def connect(self) -> bool:
        self._connected = True
        return True

    def disconnect(self) -> bool:
        self._connected = False
        return True

    def health_check(self) -> dict:
        return {"name": self.name, "status": "ok" if self._connected else "disconnected",
                "shop": self.shop}

    def get_orders(self) -> List[dict]:
        return [
            {"id": "order-1", "status": "paid", "total": 50000},
            {"id": "order-2", "status": "pending", "total": 30000},
        ]

    def get_products(self) -> List[dict]:
        return [
            {"id": "prod-1", "title": "상품1", "price": "10000"},
            {"id": "prod-2", "title": "상품2", "price": "20000"},
        ]

    def sync(self) -> dict:
        orders = self.get_orders()
        products = self.get_products()
        return {"synced": True, "orders": len(orders), "products": len(products)}
