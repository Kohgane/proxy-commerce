"""src/shipping/tracker.py — 배송 추적 관리."""
import logging
from datetime import datetime
from typing import Dict, List, Optional

from .carriers import CarrierFactory
from .models import ShipmentRecord

logger = logging.getLogger(__name__)


class ShipmentTracker:
    """인메모리 배송 추적 관리자."""

    def __init__(self) -> None:
        self._records: Dict[str, ShipmentRecord] = {}

    def register(
        self,
        tracking_number: str,
        carrier_name: str,
        order_id: Optional[str] = None,
    ) -> ShipmentRecord:
        """운송장 번호를 등록하고 초기 조회 결과를 반환."""
        carrier = CarrierFactory.get_carrier(carrier_name)
        record = carrier.track(tracking_number)
        record.order_id = order_id
        self._records[tracking_number] = record
        logger.info("배송 등록: %s (%s)", tracking_number, carrier_name)
        return record

    def get_status(self, tracking_number: str) -> Optional[ShipmentRecord]:
        """등록된 배송 현황 조회."""
        return self._records.get(tracking_number)

    def update_status(self, tracking_number: str) -> Optional[ShipmentRecord]:
        """택배사에 재조회하여 현황 갱신."""
        existing = self._records.get(tracking_number)
        if existing is None:
            return None
        carrier = CarrierFactory.get_carrier(existing.carrier)
        updated = carrier.track(tracking_number)
        updated.order_id = existing.order_id
        updated.updated_at = datetime.utcnow()
        self._records[tracking_number] = updated
        return updated

    def get_all(self) -> List[ShipmentRecord]:
        """등록된 모든 배송 목록 반환."""
        return list(self._records.values())
