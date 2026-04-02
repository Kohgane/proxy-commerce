"""src/shipping/models.py — 배송 추적 데이터 모델."""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional


class ShipmentStatus(str, Enum):
    picked_up = "picked_up"
    in_transit = "in_transit"
    out_for_delivery = "out_for_delivery"
    delivered = "delivered"
    exception = "exception"


@dataclass
class TrackingEvent:
    timestamp: datetime
    status: ShipmentStatus
    location: str
    description: str


@dataclass
class ShipmentRecord:
    tracking_number: str
    carrier: str
    status: ShipmentStatus
    updated_at: datetime
    events: List[TrackingEvent] = field(default_factory=list)
    order_id: Optional[str] = None
