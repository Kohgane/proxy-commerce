"""src/returns_automation/reverse_logistics.py — Phase 118: 회수 운송장 자동 발급 + 픽업 예약.

지원 택배사 (mock): CJ대한통운 / 한진택배 / 우체국택배
Phase 27 ShipmentTracker를 재사용하여 반품 운송 추적.
"""
from __future__ import annotations

import logging
import random
import string
from datetime import datetime, timezone
from typing import Dict, Optional

from .models import AutoReturnRequest

logger = logging.getLogger(__name__)

# 지원 택배사 목록
SUPPORTED_CARRIERS = {
    'cj': 'CJ대한통운',
    'hanjin': '한진택배',
    'epost': '우체국택배',
}


def _generate_waybill() -> str:
    """12자리 운송장 번호 생성 (mock)."""
    return ''.join(random.choices(string.digits, k=12))


class ReverseLogisticsManager:
    """회수 운송장 자동 발급 + 픽업 예약 관리자.

    택배사 API는 mock으로 구현. 실 연동 시 각 택배사 SDK로 교체.
    """

    def __init__(self) -> None:
        # waybill_no → tracking_record 인메모리 저장
        self._waybills: Dict[str, dict] = {}

    def schedule_pickup(
        self,
        request: AutoReturnRequest,
        address: dict,
        carrier: str = 'cj',
    ) -> dict:
        """회수 픽업 예약.

        Args:
            request: 반품 요청 객체
            address: 픽업 주소 dict (name, phone, address, zipcode)
            carrier: 택배사 코드 (cj/hanjin/epost)

        Returns:
            픽업 예약 결과 dict
        """
        carrier = carrier.lower()
        carrier_name = SUPPORTED_CARRIERS.get(carrier, carrier)
        pickup_id = f'PICKUP-{request.request_id}'

        result = {
            'pickup_id': pickup_id,
            'request_id': request.request_id,
            'carrier': carrier,
            'carrier_name': carrier_name,
            'address': address,
            'scheduled_date': datetime.now(timezone.utc).isoformat(),
            'status': 'scheduled',
        }
        logger.info("[회수물류] 픽업 예약 완료: %s (택배사: %s)", pickup_id, carrier_name)
        return result

    def issue_return_waybill(
        self,
        request: AutoReturnRequest,
        carrier: str = 'cj',
    ) -> dict:
        """회수 운송장 발급 (mock).

        Args:
            request: 반품 요청 객체
            carrier: 택배사 코드

        Returns:
            운송장 정보 dict
        """
        carrier = carrier.lower()
        carrier_name = SUPPORTED_CARRIERS.get(carrier, carrier)
        waybill_no = _generate_waybill()

        waybill = {
            'waybill_no': waybill_no,
            'request_id': request.request_id,
            'order_id': request.order_id,
            'carrier': carrier,
            'carrier_name': carrier_name,
            'issued_at': datetime.now(timezone.utc).isoformat(),
            'status': 'issued',
            'tracking_url': f'https://tracking.{carrier}.co.kr/{waybill_no}',
        }
        self._waybills[waybill_no] = waybill
        logger.info("[회수물류] 운송장 발급: %s (운송장: %s)", request.request_id, waybill_no)
        return waybill

    def track_return_shipment(self, waybill_no: str) -> Optional[dict]:
        """반품 운송 상태 조회.

        Phase 27 ShipmentTracker 재사용 시도 후 fallback.
        """
        # Phase 27 ShipmentTracker 재사용 시도
        try:
            from ..shipping.tracker import ShipmentTracker
            tracker = ShipmentTracker()
            result = tracker.get_status(waybill_no)
            if result:
                return result
        except Exception as exc:
            logger.debug("[회수물류] ShipmentTracker 조회 실패 (fallback): %s", exc)

        # Fallback: 인메모리 waybill 기록 반환
        waybill = self._waybills.get(waybill_no)
        if waybill:
            return {
                'waybill_no': waybill_no,
                'carrier': waybill.get('carrier', ''),
                'status': waybill.get('status', 'unknown'),
                'events': [],
            }
        return None

    def get_waybill(self, waybill_no: str) -> Optional[dict]:
        """운송장 정보 조회."""
        return self._waybills.get(waybill_no)

    def list_waybills(self, request_id: str) -> list:
        """요청 ID로 운송장 목록 조회."""
        return [w for w in self._waybills.values() if w.get('request_id') == request_id]
