"""src/virtual_inventory/virtual_stock.py — 가상 재고 풀 (Phase 113)."""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ReservationStatus(str, Enum):
    pending = 'pending'
    confirmed = 'confirmed'
    released = 'released'


@dataclass
class SourceStock:
    source_id: str
    source_name: str
    platform: str
    available_qty: int
    price: float
    currency: str
    lead_time_days: int
    reliability_score: float
    is_active: bool
    last_checked_at: datetime


@dataclass
class VirtualStock:
    product_id: str
    total_available: int
    reserved: int
    sellable: int
    sources: List[SourceStock] = field(default_factory=list)
    aggregation_strategy: str = 'sum_active'
    last_synced_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StockReservation:
    reservation_id: str
    product_id: str
    quantity: int
    source_id: Optional[str]
    status: ReservationStatus
    created_at: datetime
    expires_at: datetime


class VirtualStockPool:
    """복수 소싱처 가상 재고 풀."""

    def __init__(self) -> None:
        # product_id → {source_id: SourceStock}
        self._sources: Dict[str, Dict[str, SourceStock]] = {}
        # reservation_id → StockReservation
        self._reservations: Dict[str, StockReservation] = {}

    # ── 소싱처 재고 관리 ──────────────────────────────────────────────────────

    def add_source_stock(self, product_id: str, source_stock: SourceStock) -> None:
        """소싱처 재고 등록."""
        self._sources.setdefault(product_id, {})
        self._sources[product_id][source_stock.source_id] = source_stock

    def update_source_stock(self, product_id: str, source_id: str, updates: dict) -> bool:
        """소싱처 재고 필드 업데이트."""
        src = self._sources.get(product_id, {}).get(source_id)
        if src is None:
            return False
        for key, value in updates.items():
            if hasattr(src, key):
                setattr(src, key, value)
        return True

    def remove_source_stock(self, product_id: str, source_id: str) -> bool:
        """소싱처 제거."""
        if product_id in self._sources and source_id in self._sources[product_id]:
            del self._sources[product_id][source_id]
            return True
        return False

    def get_source_stocks(self, product_id: str) -> List[SourceStock]:
        """상품의 소싱처 재고 목록."""
        return list(self._sources.get(product_id, {}).values())

    # ── 가상 재고 조회 ────────────────────────────────────────────────────────

    def get_virtual_stock(self, product_id: str) -> Optional[VirtualStock]:
        """상품 가상 재고 반환 (소싱처에서 집계)."""
        if product_id not in self._sources:
            return None
        return self._compute_virtual_stock(product_id)

    def get_all_virtual_stocks(self) -> List[VirtualStock]:
        """전체 상품 가상 재고 목록."""
        return [self._compute_virtual_stock(pid) for pid in self._sources]

    # ── 예약 관리 ─────────────────────────────────────────────────────────────

    def reserve_stock(
        self,
        product_id: str,
        quantity: int,
        source_id: Optional[str] = None,
    ) -> StockReservation:
        """재고 예약. 판매 가능 재고 부족 시 ValueError."""
        vs = self.get_virtual_stock(product_id)
        if vs is None or vs.sellable < quantity:
            available = vs.sellable if vs else 0
            raise ValueError(
                f"재고 부족: product_id={product_id}, 요청={quantity}, 가용={available}"
            )
        now = datetime.now(timezone.utc)
        reservation = StockReservation(
            reservation_id=str(uuid.uuid4()),
            product_id=product_id,
            quantity=quantity,
            source_id=source_id,
            status=ReservationStatus.pending,
            created_at=now,
            expires_at=now.replace(hour=(now.hour + 24) % 24),
        )
        self._reservations[reservation.reservation_id] = reservation
        return reservation

    def release_reservation(self, reservation_id: str) -> bool:
        """예약 해제."""
        res = self._reservations.get(reservation_id)
        if res is None:
            return False
        res.status = ReservationStatus.released
        return True

    def confirm_reservation(self, reservation_id: str) -> bool:
        """예약 확정."""
        res = self._reservations.get(reservation_id)
        if res is None:
            return False
        res.status = ReservationStatus.confirmed
        return True

    def get_reservations(self, product_id: Optional[str] = None) -> List[StockReservation]:
        """예약 목록 반환. product_id 지정 시 필터링."""
        reservations = list(self._reservations.values())
        if product_id is not None:
            reservations = [r for r in reservations if r.product_id == product_id]
        return reservations

    # ── 내부 집계 ─────────────────────────────────────────────────────────────

    def _compute_virtual_stock(self, product_id: str) -> VirtualStock:
        """소싱처에서 VirtualStock 재계산."""
        sources = list(self._sources.get(product_id, {}).values())
        total_available = sum(
            s.available_qty for s in sources if s.is_active
        )
        reserved = sum(
            r.quantity
            for r in self._reservations.values()
            if r.product_id == product_id and r.status == ReservationStatus.pending
        )
        sellable = max(0, total_available - reserved)
        return VirtualStock(
            product_id=product_id,
            total_available=total_available,
            reserved=reserved,
            sellable=sellable,
            sources=sources,
            aggregation_strategy='sum_active',
            last_synced_at=datetime.now(timezone.utc),
        )
