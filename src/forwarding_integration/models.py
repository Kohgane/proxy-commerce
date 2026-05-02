"""src/forwarding_integration/models.py — 배송대행 통합 데이터 모델 (Phase 83)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List


@dataclass
class ForwardingPackage:
    """배송대행 패키지 모델."""

    package_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    purchase_order_id: str = ''
    customer_order_id: str = ''
    product_name: str = ''
    quantity: int = 1
    weight_kg: float = 0.0
    provider: str = ''
    origin_country: str = 'US'
    destination_country: str = 'KR'
    status: str = 'pending'
    tracking_number: str = ''
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            'package_id': self.package_id,
            'purchase_order_id': self.purchase_order_id,
            'customer_order_id': self.customer_order_id,
            'product_name': self.product_name,
            'quantity': self.quantity,
            'weight_kg': self.weight_kg,
            'provider': self.provider,
            'origin_country': self.origin_country,
            'destination_country': self.destination_country,
            'status': self.status,
            'tracking_number': self.tracking_number,
            'created_at': self.created_at,
            'metadata': self.metadata,
        }


@dataclass
class InboundRegistration:
    """입고 등록 모델."""

    registration_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    package_id: str = ''
    provider: str = ''
    purchase_order_id: str = ''
    product_name: str = ''
    quantity: int = 1
    weight_kg: float = 0.0
    warehouse_address: Dict = field(default_factory=dict)
    status: str = 'registered'
    registered_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            'registration_id': self.registration_id,
            'package_id': self.package_id,
            'provider': self.provider,
            'purchase_order_id': self.purchase_order_id,
            'product_name': self.product_name,
            'quantity': self.quantity,
            'weight_kg': self.weight_kg,
            'warehouse_address': self.warehouse_address,
            'status': self.status,
            'registered_at': self.registered_at,
            'metadata': self.metadata,
        }


@dataclass
class ConsolidationRequest:
    """합배송 요청 모델."""

    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    package_ids: List[str] = field(default_factory=list)
    provider: str = ''
    destination_country: str = 'KR'
    status: str = 'pending'
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            'request_id': self.request_id,
            'package_ids': self.package_ids,
            'provider': self.provider,
            'destination_country': self.destination_country,
            'status': self.status,
            'created_at': self.created_at,
            'metadata': self.metadata,
        }


@dataclass
class OutboundRequest:
    """출고 요청 모델."""

    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    package_ids: List[str] = field(default_factory=list)
    provider: str = ''
    destination_country: str = 'KR'
    recipient_name: str = ''
    recipient_address: str = ''
    tracking_number: str = ''
    status: str = 'requested'
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            'request_id': self.request_id,
            'package_ids': self.package_ids,
            'provider': self.provider,
            'destination_country': self.destination_country,
            'recipient_name': self.recipient_name,
            'recipient_address': self.recipient_address,
            'tracking_number': self.tracking_number,
            'status': self.status,
            'created_at': self.created_at,
            'metadata': self.metadata,
        }


@dataclass
class ForwardingStatus:
    """배송대행 상태 모델."""

    package_id: str = ''
    current_status: str = 'unknown'
    provider: str = ''
    tracking_number: str = ''
    last_updated: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    events: List[Dict] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            'package_id': self.package_id,
            'current_status': self.current_status,
            'provider': self.provider,
            'tracking_number': self.tracking_number,
            'last_updated': self.last_updated,
            'events': self.events,
            'metadata': self.metadata,
        }
