"""src/forwarding/tracker.py — 배송 추적 서비스 (Phase 102)."""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class ShipmentStatus(Enum):
    PENDING = 'pending'
    SHIPPED_FROM_WAREHOUSE = 'shipped_from_warehouse'
    CUSTOMS_CLEARANCE = 'customs_clearance'
    DOMESTIC_TRANSIT = 'domestic_transit'
    DELIVERED = 'delivered'


@dataclass
class TrackingEvent:
    """배송 추적 이벤트."""

    timestamp: datetime
    status: ShipmentStatus
    location: str
    description: str


@dataclass
class ShipmentRecord:
    """배송 기록."""

    shipment_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    tracking_number: str = ''
    agent_id: str = ''
    status: ShipmentStatus = ShipmentStatus.PENDING
    origin_country: str = 'US'
    destination_country: str = 'KR'
    estimated_delivery: Optional[datetime] = None
    events: List[TrackingEvent] = field(default_factory=list)
    customs_status: str = ''
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    delivered_at: Optional[datetime] = None
    metadata: Dict = field(default_factory=dict)


class ShipmentTracker:
    """배송 추적 서비스."""

    _avg_days: Dict[str, int] = {
        'moltail_US': 7,
        'moltail_JP': 5,
        'ihanex_US': 9,
        'ihanex_JP': 6,
    }

    def __init__(self) -> None:
        self._shipments: Dict[str, ShipmentRecord] = {}

    def create_shipment(
        self,
        tracking_number: str,
        agent_id: str,
        origin_country: str = 'US',
    ) -> ShipmentRecord:
        """배송 기록을 생성한다."""
        record = ShipmentRecord(
            tracking_number=tracking_number,
            agent_id=agent_id,
            origin_country=origin_country.upper(),
            estimated_delivery=self.calculate_eta(agent_id, origin_country),
        )
        self._shipments[record.shipment_id] = record
        logger.info("배송 기록 생성: %s (%s)", record.shipment_id, tracking_number)
        return record

    def get_shipment(self, shipment_id: str) -> ShipmentRecord:
        """배송 기록을 조회한다."""
        if shipment_id not in self._shipments:
            raise KeyError(f"배송 기록 없음: {shipment_id}")
        return self._shipments[shipment_id]

    def update_tracking(self, shipment_id: str) -> ShipmentRecord:
        """에이전트에서 최신 추적 정보를 조회해 갱신한다."""
        record = self.get_shipment(shipment_id)
        try:
            from .agent import ForwardingAgentManager
            mgr = ForwardingAgentManager()
            agent = mgr.get_agent(record.agent_id)
            data = agent.get_tracking(shipment_id)

            status_map = {
                'pending': ShipmentStatus.PENDING,
                'shipped_from_warehouse': ShipmentStatus.SHIPPED_FROM_WAREHOUSE,
                'customs_clearance': ShipmentStatus.CUSTOMS_CLEARANCE,
                'domestic_transit': ShipmentStatus.DOMESTIC_TRANSIT,
                'delivered': ShipmentStatus.DELIVERED,
            }
            raw_status = data.get('status', 'pending')
            record.status = status_map.get(raw_status, ShipmentStatus.PENDING)
            record.customs_status = data.get('customs_status', record.customs_status)

            new_events: List[TrackingEvent] = []
            for ev in data.get('events', []):
                try:
                    ts = datetime.fromisoformat(ev['timestamp'])
                except (ValueError, KeyError):
                    logger.warning("추적 이벤트 타임스탬프 파싱 실패, 현재 시각으로 대체")
                    ts = datetime.now(timezone.utc)
                ev_status = status_map.get(ev.get('status', 'pending'), ShipmentStatus.PENDING)
                new_events.append(
                    TrackingEvent(
                        timestamp=ts,
                        status=ev_status,
                        location=ev.get('location', ''),
                        description=ev.get('description', ''),
                    )
                )
            if new_events:
                record.events = new_events

            if record.status == ShipmentStatus.DELIVERED and record.delivered_at is None:
                record.delivered_at = datetime.now(timezone.utc)

        except Exception as exc:
            logger.warning("배송 추적 갱신 실패 (%s): %s", shipment_id, exc)
        return record

    def list_shipments(
        self, status: Optional[ShipmentStatus] = None
    ) -> List[ShipmentRecord]:
        """배송 기록 목록을 반환한다."""
        shipments = list(self._shipments.values())
        if status is not None:
            shipments = [s for s in shipments if s.status == status]
        return shipments

    def calculate_eta(self, agent_id: str, origin_country: str) -> datetime:
        """평균 배송일을 기준으로 예상 도착일을 계산한다."""
        key = f'{agent_id}_{origin_country.upper()}'
        days = self._avg_days.get(key, 10)
        return datetime.now(timezone.utc) + timedelta(days=days)

    def get_stats(self) -> Dict:
        """상태별 통계 및 평균 배송일을 반환한다."""
        stats: Dict[str, int] = {s.value: 0 for s in ShipmentStatus}
        delivered_days: List[float] = []
        for record in self._shipments.values():
            stats[record.status.value] += 1
            if record.delivered_at and record.created_at:
                delta = record.delivered_at - record.created_at
                delivered_days.append(delta.total_seconds() / 86400)

        avg_days = (sum(delivered_days) / len(delivered_days)) if delivered_days else 0.0
        return {
            'by_status': stats,
            'total': len(self._shipments),
            'avg_delivery_days': round(avg_days, 1),
        }
