"""재고 채널 어댑터 — ABC + Coupang/Naver/Internal 구현."""

import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class ChannelAdapter(ABC):
    """채널 어댑터 추상 기반 클래스."""

    @abstractmethod
    def get_stock(self, sku: str) -> int:
        """현재 재고 조회."""

    @abstractmethod
    def update_stock(self, sku: str, qty: int) -> bool:
        """재고 업데이트."""

    @abstractmethod
    def list_products(self) -> list:
        """상품 목록 조회."""


class CoupangAdapter(ChannelAdapter):
    """쿠팡 채널 어댑터."""

    def __init__(self):
        self._stock: dict = {}

    def get_stock(self, sku: str) -> int:
        return self._stock.get(sku, 0)

    def update_stock(self, sku: str, qty: int) -> bool:
        self._stock[sku] = qty
        logger.info("쿠팡 재고 업데이트: %s -> %d", sku, qty)
        return True

    def list_products(self) -> list:
        return list(self._stock.keys())


class NaverAdapter(ChannelAdapter):
    """네이버 채널 어댑터."""

    def __init__(self):
        self._stock: dict = {}

    def get_stock(self, sku: str) -> int:
        return self._stock.get(sku, 0)

    def update_stock(self, sku: str, qty: int) -> bool:
        self._stock[sku] = qty
        logger.info("네이버 재고 업데이트: %s -> %d", sku, qty)
        return True

    def list_products(self) -> list:
        return list(self._stock.keys())


class InternalAdapter(ChannelAdapter):
    """내부 채널 어댑터."""

    def __init__(self):
        self._stock: dict = {}

    def get_stock(self, sku: str) -> int:
        return self._stock.get(sku, 0)

    def update_stock(self, sku: str, qty: int) -> bool:
        self._stock[sku] = qty
        logger.info("내부 재고 업데이트: %s -> %d", sku, qty)
        return True

    def list_products(self) -> list:
        return list(self._stock.keys())
