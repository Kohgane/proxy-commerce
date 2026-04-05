"""src/fulfillment/tracking.py — 운송장 관리 및 배송 추적 (Phase 103)."""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class DeliveryStatus(str, Enum):
    picked_up = 'picked_up'
    in_transit = 'in_transit'
    out_for_delivery = 'out_for_delivery'
    delivered = 'delivered'
    failed = 'failed'


@dataclass
class TrackingRecord:
    tracking_id: str
    order_id: str
    tracking_number: str
    carrier_id: str
    platform: str
    registered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    retry_count: int = 0
    registration_success: bool = True
    metadata: Dict = field(default_factory=dict)


class TrackingNumberManager:
    """운송장번호 자동 생성/등록/관리."""

    _PLATFORM_REGISTER_FNS = {
        'coupang': '_register_coupang',
        'naver': '_register_naver',
        'internal': '_register_internal',
    }

    def __init__(self):
        self._records: List[TrackingRecord] = []

    def register(
        self,
        order_id: str,
        tracking_number: str,
        carrier_id: str,
        platform: str = 'internal',
        retry: bool = True,
    ) -> TrackingRecord:
        """운송장을 플랫폼에 등록한다."""
        tracking_id = f'trk_{uuid.uuid4().hex[:8]}'
        success = self._register_to_platform(order_id, tracking_number, carrier_id, platform)
        retry_count = 0
        if not success and retry:
            success = self._register_to_platform(order_id, tracking_number, carrier_id, platform)
            retry_count = 1
            if not success:
                logger.warning("운송장 등록 재시도 실패: %s %s", order_id, tracking_number)
        record = TrackingRecord(
            tracking_id=tracking_id,
            order_id=order_id,
            tracking_number=tracking_number,
            carrier_id=carrier_id,
            platform=platform,
            retry_count=retry_count,
            registration_success=success,
        )
        self._records.append(record)
        logger.info("운송장 등록 완료: %s → %s (%s)", order_id, tracking_number, platform)
        return record

    def get_history(self, order_id: Optional[str] = None) -> List[TrackingRecord]:
        if order_id:
            return [r for r in self._records if r.order_id == order_id]
        return list(self._records)

    def get_record(self, tracking_number: str) -> Optional[TrackingRecord]:
        for r in reversed(self._records):
            if r.tracking_number == tracking_number:
                return r
        return None

    def get_stats(self) -> Dict:
        total = len(self._records)
        success = sum(1 for r in self._records if r.registration_success)
        return {
            'total': total,
            'success': success,
            'failed': total - success,
            'retry_count': sum(r.retry_count for r in self._records),
        }

    def _register_to_platform(
        self, order_id: str, tracking_number: str, carrier_id: str, platform: str
    ) -> bool:
        """플랫폼별 운송장 등록 (mock)."""
        # All mock implementations succeed
        return True


@dataclass
class DeliveryEvent:
    timestamp: datetime
    status: DeliveryStatus
    location: str
    description: str


class DeliveryTracker:
    """국내 택배 배송 상태 추적."""

    _ETA_BY_CARRIER: Dict[str, float] = {
        'cj_logistics': 1.5,
        'hanjin': 1.8,
        'lotte': 2.0,
    }

    def __init__(self):
        self._tracking_data: Dict[str, List[DeliveryEvent]] = {}
        self._delivery_status: Dict[str, DeliveryStatus] = {}

    def start_tracking(self, tracking_number: str, carrier_id: str) -> None:
        """배송 추적을 시작한다."""
        self._tracking_data[tracking_number] = [
            DeliveryEvent(
                timestamp=datetime.now(timezone.utc),
                status=DeliveryStatus.picked_up,
                location='집하장',
                description='상품이 집하되었습니다.',
            )
        ]
        self._delivery_status[tracking_number] = DeliveryStatus.picked_up
        logger.info("배송 추적 시작: %s", tracking_number)

    def update_status(self, tracking_number: str, status: DeliveryStatus, location: str = '', description: str = '') -> None:
        """배송 상태를 업데이트한다."""
        if tracking_number not in self._tracking_data:
            self._tracking_data[tracking_number] = []
        self._tracking_data[tracking_number].append(
            DeliveryEvent(
                timestamp=datetime.now(timezone.utc),
                status=status,
                location=location or '알 수 없음',
                description=description or status.value,
            )
        )
        self._delivery_status[tracking_number] = status

        if status == DeliveryStatus.delivered:
            self._on_delivered(tracking_number)
        elif status == DeliveryStatus.failed:
            self._on_failed(tracking_number)

    def get_status(self, tracking_number: str) -> Dict:
        """현재 배송 상태를 반환한다."""
        status = self._delivery_status.get(tracking_number, DeliveryStatus.in_transit)
        events = self._tracking_data.get(tracking_number, [])
        return {
            'tracking_number': tracking_number,
            'status': status.value,
            'events': [
                {
                    'timestamp': e.timestamp.isoformat(),
                    'status': e.status.value,
                    'location': e.location,
                    'description': e.description,
                }
                for e in events
            ],
        }

    def estimate_eta(self, tracking_number: str, carrier_id: str = '') -> Optional[float]:
        """ETA를 예측한다 (일 단위)."""
        status = self._delivery_status.get(tracking_number)
        if status == DeliveryStatus.delivered:
            return 0.0
        return self._ETA_BY_CARRIER.get(carrier_id, 2.0)

    def get_all_active(self) -> List[Dict]:
        result = []
        for tn, status in self._delivery_status.items():
            if status not in (DeliveryStatus.delivered, DeliveryStatus.failed):
                result.append({'tracking_number': tn, 'status': status.value})
        return result

    def get_stats(self) -> Dict:
        by_status: Dict[str, int] = {s.value: 0 for s in DeliveryStatus}
        for status in self._delivery_status.values():
            by_status[status.value] += 1
        return {
            'total': len(self._delivery_status),
            'by_status': by_status,
            'active': len(self.get_all_active()),
        }

    def _on_delivered(self, tracking_number: str) -> None:
        logger.info("배송 완료 감지: %s", tracking_number)

    def _on_failed(self, tracking_number: str) -> None:
        logger.warning("배송 실패 감지: %s", tracking_number)
