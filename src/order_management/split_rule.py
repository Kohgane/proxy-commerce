"""src/order_management/split_rule.py — 주문 분할 규칙."""
from __future__ import annotations

from abc import ABC, abstractmethod


class SplitRule(ABC):
    """분할 규칙 추상 기본 클래스."""

    @abstractmethod
    def split(self, items: list) -> list[list]:
        """Items를 그룹으로 분할."""


class SupplierSplitRule(SplitRule):
    """공급자 기반 분할 규칙."""

    def split(self, items: list) -> list[list]:
        """공급자별로 그룹화한다."""
        groups: dict[str, list] = {}
        for item in items:
            key = item.get('supplier_id', 'default')
            groups.setdefault(key, []).append(item)
        return list(groups.values())


class WarehouseSplitRule(SplitRule):
    """창고 기반 분할 규칙."""

    def split(self, items: list) -> list[list]:
        """창고별로 그룹화한다."""
        groups: dict[str, list] = {}
        for item in items:
            key = item.get('warehouse_id', 'default')
            groups.setdefault(key, []).append(item)
        return list(groups.values())


class ShippingMethodSplitRule(SplitRule):
    """배송 방법 기반 분할 규칙."""

    def split(self, items: list) -> list[list]:
        """배송 방법별로 그룹화한다."""
        groups: dict[str, list] = {}
        for item in items:
            key = item.get('shipping_method', 'standard')
            groups.setdefault(key, []).append(item)
        return list(groups.values())
