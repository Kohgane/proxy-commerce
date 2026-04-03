"""src/marketplace_sync/adapter.py — 마켓플레이스 어댑터."""
from __future__ import annotations

from abc import ABC, abstractmethod


class MarketplaceAdapter(ABC):
    """마켓플레이스 동기화 어댑터 추상 클래스."""

    @abstractmethod
    def sync_products(self) -> list: ...

    @abstractmethod
    def sync_orders(self) -> list: ...

    @abstractmethod
    def sync_inventory(self) -> list: ...

    @abstractmethod
    def sync_prices(self) -> list: ...


class CoupangSyncAdapter(MarketplaceAdapter):
    """쿠팡 동기화 어댑터 (모의)."""

    def sync_products(self) -> list:
        return [{"product_id": "cp-001", "name": "상품A", "marketplace": "coupang"}]

    def sync_orders(self) -> list:
        return [{"order_id": "cp-o-001", "status": "pending", "marketplace": "coupang"}]

    def sync_inventory(self) -> list:
        return [{"sku": "cp-sku-001", "quantity": 100, "marketplace": "coupang"}]

    def sync_prices(self) -> list:
        return [{"product_id": "cp-001", "price": 15000, "marketplace": "coupang"}]


class NaverSyncAdapter(MarketplaceAdapter):
    """네이버 동기화 어댑터 (모의)."""

    def sync_products(self) -> list:
        return [{"product_id": "nv-001", "name": "상품B", "marketplace": "naver"}]

    def sync_orders(self) -> list:
        return [{"order_id": "nv-o-001", "status": "paid", "marketplace": "naver"}]

    def sync_inventory(self) -> list:
        return [{"sku": "nv-sku-001", "quantity": 50, "marketplace": "naver"}]

    def sync_prices(self) -> list:
        return [{"product_id": "nv-001", "price": 18000, "marketplace": "naver"}]


class GmarketSyncAdapter(MarketplaceAdapter):
    """지마켓 동기화 어댑터 (모의)."""

    def sync_products(self) -> list:
        return [{"product_id": "gm-001", "name": "상품C", "marketplace": "gmarket"}]

    def sync_orders(self) -> list:
        return [{"order_id": "gm-o-001", "status": "shipped", "marketplace": "gmarket"}]

    def sync_inventory(self) -> list:
        return [{"sku": "gm-sku-001", "quantity": 75, "marketplace": "gmarket"}]

    def sync_prices(self) -> list:
        return [{"product_id": "gm-001", "price": 12000, "marketplace": "gmarket"}]
