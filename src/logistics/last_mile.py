"""src/logistics/last_mile.py — 라스트 마일 배송 추적 (Phase 99)."""
from __future__ import annotations

import time
import uuid

from .logistics_models import (
    Coordinate,
    DeliveryAgent,
    DeliveryRecord,
    DeliveryStatus,
    DeliveryTimeWindow,
    ProofOfDelivery,
)
from .route_optimizer import DistanceCalculator

# 유효한 상태 전이
_VALID_TRANSITIONS: dict = {
    DeliveryStatus.assigned: {DeliveryStatus.picked_up, DeliveryStatus.failed},
    DeliveryStatus.picked_up: {DeliveryStatus.in_transit, DeliveryStatus.failed},
    DeliveryStatus.in_transit: {DeliveryStatus.near_destination, DeliveryStatus.failed},
    DeliveryStatus.near_destination: {DeliveryStatus.delivered, DeliveryStatus.failed},
    DeliveryStatus.delivered: set(),
    DeliveryStatus.failed: {DeliveryStatus.assigned},
}


class LastMileTracker:
    """배송 실시간 추적기."""

    def __init__(self) -> None:
        self._deliveries: dict = {}

    def create_delivery(
        self,
        order_id: str,
        pickup_address: str,
        delivery_address: str,
        pickup_coord: Coordinate,
        delivery_coord: Coordinate,
    ) -> DeliveryRecord:
        delivery_id = str(uuid.uuid4())
        distance = DistanceCalculator.haversine(pickup_coord, delivery_coord)
        avg_speed_kmh = 30.0
        eta = (distance / avg_speed_kmh) * 60

        record = DeliveryRecord(
            delivery_id=delivery_id,
            agent_id="",
            order_id=order_id,
            pickup_address=pickup_address,
            delivery_address=delivery_address,
            pickup_coordinate=pickup_coord,
            delivery_coordinate=delivery_coord,
            status=DeliveryStatus.assigned,
            created_at=time.time(),
            updated_at=time.time(),
            eta_minutes=round(eta, 1),
            distance_km=round(distance, 3),
        )
        self._deliveries[delivery_id] = record
        return record

    def update_location(self, delivery_id: str, new_coord: Coordinate) -> DeliveryRecord:
        record = self._deliveries.get(delivery_id)
        if record is None:
            raise KeyError(f"배송 없음: {delivery_id}")
        remaining = DistanceCalculator.haversine(new_coord, record.delivery_coordinate)
        avg_speed_kmh = 30.0
        record.eta_minutes = round((remaining / avg_speed_kmh) * 60, 1)
        record.updated_at = time.time()
        return record

    def update_status(self, delivery_id: str, new_status: DeliveryStatus) -> DeliveryRecord:
        record = self._deliveries.get(delivery_id)
        if record is None:
            raise KeyError(f"배송 없음: {delivery_id}")
        allowed = _VALID_TRANSITIONS.get(record.status, set())
        if new_status not in allowed:
            raise ValueError(
                f"유효하지 않은 상태 전이: {record.status.value} → {new_status.value}"
            )
        record.status = new_status
        record.updated_at = time.time()
        return record

    def calculate_eta(self, delivery_id: str) -> float:
        record = self._deliveries.get(delivery_id)
        if record is None:
            raise KeyError(f"배송 없음: {delivery_id}")
        return record.eta_minutes

    def get_delivery(self, delivery_id: str) -> DeliveryRecord | None:
        return self._deliveries.get(delivery_id)

    def list_deliveries(self, status: DeliveryStatus | None = None) -> list:
        deliveries = list(self._deliveries.values())
        if status is not None:
            deliveries = [d for d in deliveries if d.status == status]
        return deliveries


class DeliveryAssignment:
    """배달 기사 배정 관리자."""

    def __init__(self) -> None:
        self._agents: dict = {}

    def register_agent(
        self,
        name: str,
        phone: str,
        location_coord: Coordinate,
        capacity_kg: float = 50.0,
    ) -> DeliveryAgent:
        agent_id = str(uuid.uuid4())
        agent = DeliveryAgent(
            agent_id=agent_id,
            name=name,
            phone=phone,
            current_location=location_coord,
            status="available",
            capacity_kg=capacity_kg,
        )
        self._agents[agent_id] = agent
        return agent

    def assign_best_agent(self, delivery: DeliveryRecord) -> DeliveryAgent | None:
        available = [a for a in self._agents.values() if a.status == "available"]
        if not available:
            return None

        def score(agent: DeliveryAgent) -> float:
            dist = DistanceCalculator.haversine(agent.current_location, delivery.pickup_coordinate)
            workload = len(agent.assigned_deliveries)
            return dist + workload * 5.0

        best = min(available, key=score)
        best.assigned_deliveries.append(delivery.delivery_id)
        delivery.agent_id = best.agent_id
        if len(best.assigned_deliveries) >= 5:
            best.status = "busy"
        return best

    def get_agent(self, agent_id: str) -> DeliveryAgent | None:
        return self._agents.get(agent_id)

    def list_agents(self, status: str | None = None) -> list:
        agents = list(self._agents.values())
        if status is not None:
            agents = [a for a in agents if a.status == status]
        return agents


class ProofOfDeliveryService:
    """배송 완료 증빙 서비스."""

    def __init__(self) -> None:
        self._proofs: dict = {}

    def record_proof(
        self,
        delivery_id: str,
        recipient_name: str,
        gps_coord: Coordinate | None = None,
        notes: str = "",
    ) -> ProofOfDelivery:
        proof = ProofOfDelivery(
            delivery_id=delivery_id,
            recipient_name=recipient_name,
            gps_coordinate=gps_coord,
            delivered_at=time.time(),
            notes=notes,
        )
        self._proofs[delivery_id] = proof
        return proof

    def get_proof(self, delivery_id: str) -> ProofOfDelivery | None:
        return self._proofs.get(delivery_id)


class DeliveryTimeWindowManager:
    """배송 시간대 관리자."""

    _WINDOWS = [
        DeliveryTimeWindow("w1", "오전", 9, 12, 0.0),
        DeliveryTimeWindow("w2", "오후", 13, 18, 0.0),
        DeliveryTimeWindow("w3", "저녁", 19, 22, 0.2),
        DeliveryTimeWindow("w4", "야간", 22, 6, 0.5),
    ]

    def get_windows(self) -> list:
        return list(self._WINDOWS)

    def get_surcharge(self, hour: int) -> float:
        hour = hour % 24
        if 9 <= hour < 12:
            return 0.0
        if 13 <= hour < 18:
            return 0.0
        if 19 <= hour < 22:
            return 0.2
        # 야간 (22-6시)
        return 0.5
