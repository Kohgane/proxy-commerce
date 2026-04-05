"""src/fulfillment/engine.py — 풀필먼트 오케스트레이터 (Phase 103)."""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class FulfillmentStatus(str, Enum):
    received = 'received'
    inspecting = 'inspecting'
    packing = 'packing'
    ready_to_ship = 'ready_to_ship'
    shipped = 'shipped'
    in_transit = 'in_transit'
    delivered = 'delivered'


@dataclass
class FulfillmentOrder:
    order_id: str
    status: FulfillmentStatus = FulfillmentStatus.received
    items: List[Dict] = field(default_factory=list)
    tracking_number: Optional[str] = None
    carrier: Optional[str] = None
    recipient: Dict = field(default_factory=dict)
    inspection_result: Optional[Dict] = None
    packing_result: Optional[Dict] = None
    timestamps: Dict[str, str] = field(default_factory=dict)
    metadata: Dict = field(default_factory=dict)

    def __post_init__(self):
        if 'created_at' not in self.timestamps:
            self.timestamps['created_at'] = datetime.now(timezone.utc).isoformat()

    def update_status(self, new_status: FulfillmentStatus) -> None:
        self.status = new_status
        self.timestamps[new_status.value + '_at'] = datetime.now(timezone.utc).isoformat()


class FulfillmentEngine:
    """풀필먼트 프로세스 오케스트레이터."""

    def __init__(self):
        self._orders: Dict[str, FulfillmentOrder] = {}

    def create_order(self, items: List[Dict], recipient: Dict, metadata: Optional[Dict] = None) -> FulfillmentOrder:
        order_id = f'fulfillment_{uuid.uuid4().hex[:10]}'
        order = FulfillmentOrder(
            order_id=order_id,
            items=items,
            recipient=recipient,
            metadata=metadata or {},
        )
        self._orders[order_id] = order
        logger.info("풀필먼트 주문 생성: %s", order_id)
        return order

    def get_order(self, order_id: str) -> Optional[FulfillmentOrder]:
        return self._orders.get(order_id)

    def list_orders(self, status: Optional[FulfillmentStatus] = None) -> List[FulfillmentOrder]:
        orders = list(self._orders.values())
        if status:
            orders = [o for o in orders if o.status == status]
        return orders

    def advance_to_inspecting(self, order_id: str) -> FulfillmentOrder:
        order = self._get_order_or_raise(order_id)
        order.update_status(FulfillmentStatus.inspecting)
        return order

    def advance_to_packing(self, order_id: str, inspection_result: Dict) -> FulfillmentOrder:
        order = self._get_order_or_raise(order_id)
        order.inspection_result = inspection_result
        order.update_status(FulfillmentStatus.packing)
        return order

    def advance_to_ready(self, order_id: str, packing_result: Dict) -> FulfillmentOrder:
        order = self._get_order_or_raise(order_id)
        order.packing_result = packing_result
        order.update_status(FulfillmentStatus.ready_to_ship)
        return order

    def advance_to_shipped(self, order_id: str, tracking_number: str, carrier: str) -> FulfillmentOrder:
        order = self._get_order_or_raise(order_id)
        order.tracking_number = tracking_number
        order.carrier = carrier
        order.update_status(FulfillmentStatus.shipped)
        return order

    def advance_to_in_transit(self, order_id: str) -> FulfillmentOrder:
        order = self._get_order_or_raise(order_id)
        order.update_status(FulfillmentStatus.in_transit)
        return order

    def advance_to_delivered(self, order_id: str) -> FulfillmentOrder:
        order = self._get_order_or_raise(order_id)
        order.update_status(FulfillmentStatus.delivered)
        return order

    def get_stats(self) -> Dict:
        orders = list(self._orders.values())
        stats: Dict[str, int] = {s.value: 0 for s in FulfillmentStatus}
        for o in orders:
            stats[o.status.value] += 1
        return {'total': len(orders), 'by_status': stats}

    def _get_order_or_raise(self, order_id: str) -> FulfillmentOrder:
        order = self._orders.get(order_id)
        if not order:
            raise KeyError(f'주문을 찾을 수 없습니다: {order_id}')
        return order
