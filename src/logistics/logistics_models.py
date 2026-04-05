"""src/logistics/logistics_models.py — 물류 최적화 데이터 모델 (Phase 99)."""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum


class DeliveryStatus(Enum):
    assigned = "assigned"
    picked_up = "picked_up"
    in_transit = "in_transit"
    near_destination = "near_destination"
    delivered = "delivered"
    failed = "failed"


@dataclass
class Coordinate:
    lat: float
    lon: float


@dataclass
class DeliveryStop:
    stop_id: str
    address: str
    coordinate: Coordinate
    order_id: str
    weight_kg: float = 1.0
    volume_m3: float = 0.01
    time_window_start: int = 9
    time_window_end: int = 22
    priority: int = 1
    delivered: bool = False


@dataclass
class RouteResult:
    route_id: str
    stops: list = field(default_factory=list)
    total_distance_km: float = 0.0
    estimated_duration_min: float = 0.0
    strategy_used: str = ""
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "route_id": self.route_id,
            "stops": [
                {
                    "stop_id": s.stop_id,
                    "address": s.address,
                    "order_id": s.order_id,
                    "weight_kg": s.weight_kg,
                    "priority": s.priority,
                    "delivered": s.delivered,
                }
                for s in self.stops
            ],
            "total_distance_km": self.total_distance_km,
            "estimated_duration_min": self.estimated_duration_min,
            "strategy_used": self.strategy_used,
            "created_at": self.created_at,
        }


@dataclass
class DeliveryAgent:
    agent_id: str
    name: str
    phone: str
    current_location: Coordinate
    status: str = "available"
    capacity_kg: float = 50.0
    capacity_volume_m3: float = 0.5
    assigned_deliveries: list = field(default_factory=list)
    vehicle_type: str = "motorcycle"

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "phone": self.phone,
            "current_location": {"lat": self.current_location.lat, "lon": self.current_location.lon},
            "status": self.status,
            "capacity_kg": self.capacity_kg,
            "capacity_volume_m3": self.capacity_volume_m3,
            "assigned_deliveries": self.assigned_deliveries,
            "vehicle_type": self.vehicle_type,
        }


@dataclass
class DeliveryRecord:
    delivery_id: str
    agent_id: str
    order_id: str
    pickup_address: str
    delivery_address: str
    pickup_coordinate: Coordinate
    delivery_coordinate: Coordinate
    status: DeliveryStatus = DeliveryStatus.assigned
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    eta_minutes: float = 0.0
    distance_km: float = 0.0
    proof_of_delivery: dict = None

    def to_dict(self) -> dict:
        return {
            "delivery_id": self.delivery_id,
            "agent_id": self.agent_id,
            "order_id": self.order_id,
            "pickup_address": self.pickup_address,
            "delivery_address": self.delivery_address,
            "pickup_coordinate": {"lat": self.pickup_coordinate.lat, "lon": self.pickup_coordinate.lon},
            "delivery_coordinate": {"lat": self.delivery_coordinate.lat, "lon": self.delivery_coordinate.lon},
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "eta_minutes": self.eta_minutes,
            "distance_km": self.distance_km,
            "proof_of_delivery": self.proof_of_delivery,
        }


@dataclass
class ProofOfDelivery:
    delivery_id: str
    recipient_name: str
    signature_data: str = "mock_signature"
    photo_url: str = "mock_photo.jpg"
    gps_coordinate: Coordinate = None
    delivered_at: float = field(default_factory=time.time)
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "delivery_id": self.delivery_id,
            "recipient_name": self.recipient_name,
            "signature_data": self.signature_data,
            "photo_url": self.photo_url,
            "gps_coordinate": (
                {"lat": self.gps_coordinate.lat, "lon": self.gps_coordinate.lon}
                if self.gps_coordinate
                else None
            ),
            "delivered_at": self.delivered_at,
            "notes": self.notes,
        }


@dataclass
class DeliveryTimeWindow:
    window_id: str
    name: str
    start_hour: int
    end_hour: int
    surcharge_rate: float = 0.0

    def to_dict(self) -> dict:
        return {
            "window_id": self.window_id,
            "name": self.name,
            "start_hour": self.start_hour,
            "end_hour": self.end_hour,
            "surcharge_rate": self.surcharge_rate,
        }


@dataclass
class CarrierInfo:
    carrier_id: str
    name: str
    base_rate: float
    per_kg_rate: float
    coverage_regions: list = field(default_factory=list)
    avg_delivery_days: int = 2
    reliability_score: float = 0.9

    def to_dict(self) -> dict:
        return {
            "carrier_id": self.carrier_id,
            "name": self.name,
            "base_rate": self.base_rate,
            "per_kg_rate": self.per_kg_rate,
            "coverage_regions": self.coverage_regions,
            "avg_delivery_days": self.avg_delivery_days,
            "reliability_score": self.reliability_score,
        }


@dataclass
class ConsolidationGroup:
    group_id: str
    order_ids: list = field(default_factory=list)
    region: str = ""
    estimated_saving: float = 0.0
    original_cost: float = 0.0
    consolidated_cost: float = 0.0

    def to_dict(self) -> dict:
        return {
            "group_id": self.group_id,
            "order_ids": self.order_ids,
            "region": self.region,
            "estimated_saving": self.estimated_saving,
            "original_cost": self.original_cost,
            "consolidated_cost": self.consolidated_cost,
        }


@dataclass
class LogisticsKPIData:
    on_time_rate: float = 0.0
    accident_rate: float = 0.0
    avg_delivery_cost: float = 0.0
    profit_per_delivery: float = 0.0
    total_deliveries: int = 0
    successful_deliveries: int = 0
    failed_deliveries: int = 0

    def to_dict(self) -> dict:
        return {
            "on_time_rate": self.on_time_rate,
            "accident_rate": self.accident_rate,
            "avg_delivery_cost": self.avg_delivery_cost,
            "profit_per_delivery": self.profit_per_delivery,
            "total_deliveries": self.total_deliveries,
            "successful_deliveries": self.successful_deliveries,
            "failed_deliveries": self.failed_deliveries,
        }
