"""Market adapter interface for listing workflows."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class ListingPayload:
    title: str
    description: str
    price_krw: int
    sku: str = ""
    qty: int = 0
    options: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ListingResult:
    ok: bool
    market: str
    external_id: str = ""
    message: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OrderStatus:
    external_order_id: str
    status: str
    raw: Dict[str, Any] = field(default_factory=dict)


class MarketAdapter(ABC):
    market: str = ""

    @abstractmethod
    def create_listing(self, payload: ListingPayload) -> ListingResult:
        ...

    @abstractmethod
    def update_inventory(self, sku: str, qty: int) -> bool:
        ...

    @abstractmethod
    def get_order_status(self, external_order_id: str) -> OrderStatus:
        ...

    def _mock_result(self, message: str, external_id: Optional[str] = None) -> ListingResult:
        return ListingResult(
            ok=True,
            market=self.market,
            external_id=external_id or f"MOCK-{self.market.upper()}",
            message=message,
        )
