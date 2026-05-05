"""src/seller_console/orders/models.py — 통합 주문 도메인 모델 (Phase 129).

4개 마켓 주문을 통합한 도메인 모델.
- 마켓별 응답 → UnifiedOrder로 정규화
- Google Sheets `orders` 워크시트가 source of truth
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Literal, Optional

Marketplace = Literal["coupang", "smartstore", "11st", "kohganemultishop"]


class OrderStatus(str, Enum):
    NEW = "new"
    PAID = "paid"
    PREPARING = "preparing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELED = "canceled"
    RETURNED = "returned"
    EXCHANGED = "exchanged"
    REFUND_REQUESTED = "refund_requested"


@dataclass
class OrderLineItem:
    sku: str
    title: str
    qty: int
    unit_price_krw: Decimal
    options: dict = field(default_factory=dict)


@dataclass
class UnifiedOrder:
    """통합 주문 단위."""

    order_id: str
    marketplace: Marketplace  # type: ignore[valid-type]
    status: OrderStatus
    placed_at: datetime
    paid_at: Optional[datetime] = None
    buyer_name_masked: Optional[str] = None
    buyer_phone_masked: Optional[str] = None
    buyer_address_masked: Optional[str] = None
    total_krw: Decimal = field(default_factory=lambda: Decimal(0))
    shipping_fee_krw: Decimal = field(default_factory=lambda: Decimal(0))
    items: list = field(default_factory=list)  # list[OrderLineItem]
    courier: Optional[str] = None
    tracking_no: Optional[str] = None
    shipped_at: Optional[datetime] = None
    landed_cost_krw: Optional[Decimal] = None
    margin_krw: Optional[Decimal] = None
    margin_pct: Optional[Decimal] = None
    last_synced_at: Optional[datetime] = None
    raw: dict = field(default_factory=dict)
    notes: str = ""

    def to_dict(self) -> dict:
        """직렬화 (JSON 호환)."""
        return {
            "order_id": self.order_id,
            "marketplace": self.marketplace,
            "status": self.status.value if isinstance(self.status, OrderStatus) else self.status,
            "placed_at": self.placed_at.isoformat() if self.placed_at else None,
            "paid_at": self.paid_at.isoformat() if self.paid_at else None,
            "buyer_name_masked": self.buyer_name_masked,
            "buyer_phone_masked": self.buyer_phone_masked,
            "buyer_address_masked": self.buyer_address_masked,
            "total_krw": str(self.total_krw),
            "shipping_fee_krw": str(self.shipping_fee_krw),
            "items": [
                {
                    "sku": it.sku,
                    "title": it.title,
                    "qty": it.qty,
                    "unit_price_krw": str(it.unit_price_krw),
                    "options": it.options,
                }
                for it in self.items
            ],
            "courier": self.courier,
            "tracking_no": self.tracking_no,
            "shipped_at": self.shipped_at.isoformat() if self.shipped_at else None,
            "landed_cost_krw": str(self.landed_cost_krw) if self.landed_cost_krw is not None else None,
            "margin_krw": str(self.margin_krw) if self.margin_krw is not None else None,
            "margin_pct": str(self.margin_pct) if self.margin_pct is not None else None,
            "last_synced_at": self.last_synced_at.isoformat() if self.last_synced_at else None,
            "notes": self.notes,
        }


# ---------------------------------------------------------------------------
# 개인정보 마스킹 헬퍼
# ---------------------------------------------------------------------------

def mask_name(name: str) -> str:
    """이름 마스킹: 홍길동 → 홍*동"""
    if not name or len(name) < 2:
        return name or ""
    if len(name) == 2:
        return name[0] + "*"
    return name[0] + "*" * (len(name) - 2) + name[-1]


def mask_phone(phone: str) -> str:
    """전화번호 마스킹: 010-1234-5678 → 010-****-5678"""
    return re.sub(r"(\d{3})-(\d{3,4})-(\d{4})", r"\1-****-\3", phone)


def mask_address(address: str) -> str:
    """주소 마스킹: 상세주소 ***"""
    if not address:
        return ""
    parts = address.split(" ")
    if len(parts) <= 2:
        return address
    return " ".join(parts[:2]) + " ***"
