"""src/order_management/models.py — 주문 관리 모델."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SubOrder:
    """하위 주문."""

    parent_order_id: str
    sub_order_id: str
    items: list[dict[str, object]] = field(default_factory=list)
    status: str = 'pending'
    shipping_info: dict[str, object] = field(default_factory=dict)
