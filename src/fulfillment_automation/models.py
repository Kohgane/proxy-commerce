"""src/fulfillment_automation/models.py — 풀필먼트 자동화 데이터 모델 (Phase 84)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional


class FulfillmentStatus(str, Enum):
    """풀필먼트 자동화 상태."""

    pending = 'pending'
    dispatching = 'dispatching'
    dispatched = 'dispatched'
    tracking_registered = 'tracking_registered'
    in_transit = 'in_transit'
    delivered = 'delivered'
    failed = 'failed'


@dataclass
class FulfillmentOrder:
    """풀필먼트 자동화 주문 모델."""

    order_id: str = field(default_factory=lambda: f'fa_{uuid.uuid4().hex[:10]}')
    outbound_request_id: str = ''
    package_ids: List[str] = field(default_factory=list)
    carrier_id: str = ''
    tracking_number: str = ''
    status: FulfillmentStatus = FulfillmentStatus.pending
    recipient_name: str = ''
    recipient_address: str = ''
    items: List[Dict] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Dict = field(default_factory=dict)

    def update_status(self, new_status: FulfillmentStatus) -> None:
        self.status = new_status
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            'order_id': self.order_id,
            'outbound_request_id': self.outbound_request_id,
            'package_ids': self.package_ids,
            'carrier_id': self.carrier_id,
            'tracking_number': self.tracking_number,
            'status': self.status.value,
            'recipient_name': self.recipient_name,
            'recipient_address': self.recipient_address,
            'items': self.items,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'metadata': self.metadata,
        }


@dataclass
class DispatchRequest:
    """자동 발송 요청 모델."""

    dispatch_id: str = field(default_factory=lambda: f'disp_{uuid.uuid4().hex[:10]}')
    outbound_request_id: str = ''
    package_ids: List[str] = field(default_factory=list)
    carrier_id: str = ''
    recipient_name: str = ''
    recipient_address: str = ''
    weight_kg: float = 1.0
    strategy: str = 'balanced'
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            'dispatch_id': self.dispatch_id,
            'outbound_request_id': self.outbound_request_id,
            'package_ids': self.package_ids,
            'carrier_id': self.carrier_id,
            'recipient_name': self.recipient_name,
            'recipient_address': self.recipient_address,
            'weight_kg': self.weight_kg,
            'strategy': self.strategy,
            'created_at': self.created_at,
            'metadata': self.metadata,
        }


@dataclass
class TrackingInfo:
    """운송장 정보 모델."""

    tracking_id: str = field(default_factory=lambda: f'trk_{uuid.uuid4().hex[:10]}')
    order_id: str = ''
    tracking_number: str = ''
    carrier_id: str = ''
    carrier_name: str = ''
    status: str = 'registered'
    events: List[Dict] = field(default_factory=list)
    registered_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_synced_at: Optional[str] = None
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            'tracking_id': self.tracking_id,
            'order_id': self.order_id,
            'tracking_number': self.tracking_number,
            'carrier_id': self.carrier_id,
            'carrier_name': self.carrier_name,
            'status': self.status,
            'events': self.events,
            'registered_at': self.registered_at,
            'last_synced_at': self.last_synced_at,
            'metadata': self.metadata,
        }
