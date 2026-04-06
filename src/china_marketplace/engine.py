"""src/china_marketplace/engine.py — 중국 마켓플레이스 엔진 (Phase 104)."""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class ChinaPurchaseStatus(str, Enum):
    created = 'created'
    agent_assigned = 'agent_assigned'
    searching = 'searching'
    seller_verified = 'seller_verified'
    ordering = 'ordering'
    paid = 'paid'
    shipped = 'shipped'
    warehouse_received = 'warehouse_received'
    completed = 'completed'
    cancelled = 'cancelled'
    failed = 'failed'


@dataclass
class ChinaPurchaseOrder:
    order_id: str
    marketplace: str  # 'taobao' | '1688'
    product_url: str
    quantity: int = 1
    status: ChinaPurchaseStatus = ChinaPurchaseStatus.created
    agent: Optional[str] = None
    product_info: Dict = field(default_factory=dict)
    seller_info: Dict = field(default_factory=dict)
    payment_info: Dict = field(default_factory=dict)
    tracking_info: Dict = field(default_factory=dict)
    timestamps: Dict[str, str] = field(default_factory=dict)
    metadata: Dict = field(default_factory=dict)
    notes: str = ''

    def __post_init__(self):
        if 'created_at' not in self.timestamps:
            self.timestamps['created_at'] = datetime.now(timezone.utc).isoformat()

    def update_status(self, new_status: ChinaPurchaseStatus) -> None:
        self.status = new_status
        self.timestamps[new_status.value + '_at'] = datetime.now(timezone.utc).isoformat()
        logger.debug("Order %s → %s", self.order_id, new_status.value)

    def to_dict(self) -> Dict:
        return {
            'order_id': self.order_id,
            'marketplace': self.marketplace,
            'product_url': self.product_url,
            'quantity': self.quantity,
            'status': self.status.value,
            'agent': self.agent,
            'product_info': self.product_info,
            'seller_info': self.seller_info,
            'payment_info': self.payment_info,
            'tracking_info': self.tracking_info,
            'timestamps': self.timestamps,
            'metadata': self.metadata,
            'notes': self.notes,
        }


class ChinaMarketplaceEngine:
    """중국 마켓플레이스 구매 프로세스 오케스트레이터."""

    def __init__(self):
        self._orders: Dict[str, ChinaPurchaseOrder] = {}

    def create_order(
        self,
        marketplace: str,
        product_url: str,
        quantity: int = 1,
        metadata: Optional[Dict] = None,
    ) -> ChinaPurchaseOrder:
        order_id = f'cn_{uuid.uuid4().hex[:10]}'
        order = ChinaPurchaseOrder(
            order_id=order_id,
            marketplace=marketplace,
            product_url=product_url,
            quantity=quantity,
            metadata=metadata or {},
        )
        self._orders[order_id] = order
        logger.info("중국 구매 주문 생성: %s (%s)", order_id, marketplace)
        return order

    def get_order(self, order_id: str) -> Optional[ChinaPurchaseOrder]:
        return self._orders.get(order_id)

    def list_orders(
        self,
        status: Optional[ChinaPurchaseStatus] = None,
        marketplace: Optional[str] = None,
    ) -> List[ChinaPurchaseOrder]:
        orders = list(self._orders.values())
        if status:
            orders = [o for o in orders if o.status == status]
        if marketplace:
            orders = [o for o in orders if o.marketplace == marketplace]
        return orders

    def assign_agent(self, order_id: str, agent_name: str) -> ChinaPurchaseOrder:
        order = self._get_or_raise(order_id)
        order.agent = agent_name
        order.update_status(ChinaPurchaseStatus.agent_assigned)
        return order

    def start_searching(self, order_id: str) -> ChinaPurchaseOrder:
        order = self._get_or_raise(order_id)
        order.update_status(ChinaPurchaseStatus.searching)
        return order

    def mark_seller_verified(self, order_id: str, seller_info: Dict) -> ChinaPurchaseOrder:
        order = self._get_or_raise(order_id)
        order.seller_info = seller_info
        order.update_status(ChinaPurchaseStatus.seller_verified)
        return order

    def start_ordering(self, order_id: str, product_info: Dict) -> ChinaPurchaseOrder:
        order = self._get_or_raise(order_id)
        order.product_info = product_info
        order.update_status(ChinaPurchaseStatus.ordering)
        return order

    def mark_paid(self, order_id: str, payment_info: Dict) -> ChinaPurchaseOrder:
        order = self._get_or_raise(order_id)
        order.payment_info = payment_info
        order.update_status(ChinaPurchaseStatus.paid)
        return order

    def mark_shipped(self, order_id: str, tracking_info: Dict) -> ChinaPurchaseOrder:
        order = self._get_or_raise(order_id)
        order.tracking_info = tracking_info
        order.update_status(ChinaPurchaseStatus.shipped)
        return order

    def mark_warehouse_received(self, order_id: str) -> ChinaPurchaseOrder:
        order = self._get_or_raise(order_id)
        order.update_status(ChinaPurchaseStatus.warehouse_received)
        return order

    def complete_order(self, order_id: str) -> ChinaPurchaseOrder:
        order = self._get_or_raise(order_id)
        order.update_status(ChinaPurchaseStatus.completed)
        return order

    def cancel_order(self, order_id: str, reason: str = '') -> ChinaPurchaseOrder:
        order = self._get_or_raise(order_id)
        order.notes = reason
        order.update_status(ChinaPurchaseStatus.cancelled)
        return order

    def get_stats(self) -> Dict:
        orders = list(self._orders.values())
        by_status: Dict[str, int] = {}
        by_marketplace: Dict[str, int] = {}
        for o in orders:
            by_status[o.status.value] = by_status.get(o.status.value, 0) + 1
            by_marketplace[o.marketplace] = by_marketplace.get(o.marketplace, 0) + 1
        return {
            'total': len(orders),
            'by_status': by_status,
            'by_marketplace': by_marketplace,
        }

    def _get_or_raise(self, order_id: str) -> ChinaPurchaseOrder:
        order = self._orders.get(order_id)
        if order is None:
            raise KeyError(f'주문을 찾을 수 없습니다: {order_id}')
        return order
