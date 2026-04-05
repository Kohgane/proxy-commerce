"""src/fulfillment/shipping.py — 국내 배송 관리 (Phase 103)."""
from __future__ import annotations

import abc
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class CarrierAdapter(abc.ABC):
    """택배사 어댑터 추상 기반 클래스."""

    @property
    @abc.abstractmethod
    def carrier_id(self) -> str:
        """택배사 ID."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """택배사 이름."""

    @property
    @abc.abstractmethod
    def base_cost_krw(self) -> int:
        """기본 배송비 (원)."""

    @property
    @abc.abstractmethod
    def avg_delivery_days(self) -> float:
        """평균 배송 일수."""

    @abc.abstractmethod
    def create_waybill(self, order_id: str, recipient: Dict, package_info: Dict) -> Dict:
        """운송장을 생성한다."""

    @abc.abstractmethod
    def request_pickup(self, tracking_number: str) -> Dict:
        """집하를 요청한다."""

    @abc.abstractmethod
    def get_tracking(self, tracking_number: str) -> Dict:
        """배송 추적 정보를 조회한다."""


class CJLogisticsAdapter(CarrierAdapter):
    """CJ대한통운 택배사 어댑터 (mock)."""

    @property
    def carrier_id(self) -> str:
        return 'cj_logistics'

    @property
    def name(self) -> str:
        return 'CJ대한통운'

    @property
    def base_cost_krw(self) -> int:
        return 3500

    @property
    def avg_delivery_days(self) -> float:
        return 1.5

    def create_waybill(self, order_id: str, recipient: Dict, package_info: Dict) -> Dict:
        tracking_number = f'CJ{uuid.uuid4().hex[:12].upper()}'
        return {
            'tracking_number': tracking_number,
            'carrier_id': self.carrier_id,
            'carrier_name': self.name,
            'order_id': order_id,
            'recipient': recipient,
            'package_info': package_info,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'label_url': f'https://label.cjlogistics.com/{tracking_number}.pdf',
        }

    def request_pickup(self, tracking_number: str) -> Dict:
        return {
            'tracking_number': tracking_number,
            'carrier_id': self.carrier_id,
            'pickup_status': 'requested',
            'pickup_scheduled_at': datetime.now(timezone.utc).isoformat(),
        }

    def get_tracking(self, tracking_number: str) -> Dict:
        return {
            'tracking_number': tracking_number,
            'carrier_id': self.carrier_id,
            'status': 'in_transit',
            'events': [
                {
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'status': 'picked_up',
                    'location': '서울 CJ대한통운 집하장',
                    'description': '상품이 집하되었습니다.',
                }
            ],
            'eta': None,
        }


class HanjinAdapter(CarrierAdapter):
    """한진택배 어댑터 (mock)."""

    @property
    def carrier_id(self) -> str:
        return 'hanjin'

    @property
    def name(self) -> str:
        return '한진택배'

    @property
    def base_cost_krw(self) -> int:
        return 3300

    @property
    def avg_delivery_days(self) -> float:
        return 1.8

    def create_waybill(self, order_id: str, recipient: Dict, package_info: Dict) -> Dict:
        tracking_number = f'HJ{uuid.uuid4().hex[:12].upper()}'
        return {
            'tracking_number': tracking_number,
            'carrier_id': self.carrier_id,
            'carrier_name': self.name,
            'order_id': order_id,
            'recipient': recipient,
            'package_info': package_info,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'label_url': f'https://www.hanjin.com/label/{tracking_number}.pdf',
        }

    def request_pickup(self, tracking_number: str) -> Dict:
        return {
            'tracking_number': tracking_number,
            'carrier_id': self.carrier_id,
            'pickup_status': 'requested',
            'pickup_scheduled_at': datetime.now(timezone.utc).isoformat(),
        }

    def get_tracking(self, tracking_number: str) -> Dict:
        return {
            'tracking_number': tracking_number,
            'carrier_id': self.carrier_id,
            'status': 'in_transit',
            'events': [
                {
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'status': 'picked_up',
                    'location': '서울 한진택배 터미널',
                    'description': '상품이 집하되었습니다.',
                }
            ],
            'eta': None,
        }


class LotteAdapter(CarrierAdapter):
    """롯데택배 어댑터 (mock)."""

    @property
    def carrier_id(self) -> str:
        return 'lotte'

    @property
    def name(self) -> str:
        return '롯데택배'

    @property
    def base_cost_krw(self) -> int:
        return 3200

    @property
    def avg_delivery_days(self) -> float:
        return 2.0

    def create_waybill(self, order_id: str, recipient: Dict, package_info: Dict) -> Dict:
        tracking_number = f'LT{uuid.uuid4().hex[:12].upper()}'
        return {
            'tracking_number': tracking_number,
            'carrier_id': self.carrier_id,
            'carrier_name': self.name,
            'order_id': order_id,
            'recipient': recipient,
            'package_info': package_info,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'label_url': f'https://www.lotteglogis.com/label/{tracking_number}.pdf',
        }

    def request_pickup(self, tracking_number: str) -> Dict:
        return {
            'tracking_number': tracking_number,
            'carrier_id': self.carrier_id,
            'pickup_status': 'requested',
            'pickup_scheduled_at': datetime.now(timezone.utc).isoformat(),
        }

    def get_tracking(self, tracking_number: str) -> Dict:
        return {
            'tracking_number': tracking_number,
            'carrier_id': self.carrier_id,
            'status': 'in_transit',
            'events': [
                {
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'status': 'picked_up',
                    'location': '서울 롯데택배 허브',
                    'description': '상품이 집하되었습니다.',
                }
            ],
            'eta': None,
        }


class CarrierSelector:
    """최적 택배사 선택기."""

    def __init__(self, carriers: Optional[List[CarrierAdapter]] = None):
        self._carriers: List[CarrierAdapter] = carriers or [
            CJLogisticsAdapter(), HanjinAdapter(), LotteAdapter()
        ]

    def recommend(
        self,
        weight_kg: float = 1.0,
        region: str = '',
        strategy: str = 'balanced',
    ) -> CarrierAdapter:
        """최적 택배사를 추천한다."""
        if strategy == 'cheapest':
            return min(self._carriers, key=lambda c: c.base_cost_krw)
        elif strategy == 'fastest':
            return min(self._carriers, key=lambda c: c.avg_delivery_days)
        else:  # balanced
            def score(c: CarrierAdapter) -> float:
                cost_norm = c.base_cost_krw / 10000.0
                speed_norm = c.avg_delivery_days / 5.0
                return 0.5 * cost_norm + 0.5 * speed_norm
            return min(self._carriers, key=score)

    def list_carriers(self) -> List[Dict]:
        return [
            {
                'carrier_id': c.carrier_id,
                'name': c.name,
                'base_cost_krw': c.base_cost_krw,
                'avg_delivery_days': c.avg_delivery_days,
            }
            for c in self._carriers
        ]

    def get_carrier(self, carrier_id: str) -> Optional[CarrierAdapter]:
        for c in self._carriers:
            if c.carrier_id == carrier_id:
                return c
        return None


class DomesticShippingManager:
    """국내 배송 관리자."""

    def __init__(self, selector: Optional[CarrierSelector] = None):
        self._selector = selector or CarrierSelector()
        self._shipments: Dict[str, Dict] = {}

    def ship(
        self,
        order_id: str,
        recipient: Dict,
        package_info: Dict,
        carrier_id: Optional[str] = None,
        strategy: str = 'balanced',
    ) -> Dict:
        """발송을 요청하고 운송장 정보를 반환한다."""
        if carrier_id:
            carrier = self._selector.get_carrier(carrier_id)
            if not carrier:
                raise ValueError(f'알 수 없는 택배사: {carrier_id}')
        else:
            carrier = self._selector.recommend(
                weight_kg=package_info.get('weight_kg', 1.0),
                strategy=strategy,
            )
        waybill = carrier.create_waybill(order_id, recipient, package_info)
        pickup = carrier.request_pickup(waybill['tracking_number'])
        shipment = {**waybill, 'pickup': pickup, 'status': 'shipped'}
        self._shipments[waybill['tracking_number']] = shipment
        logger.info("발송 완료: %s → %s", order_id, waybill['tracking_number'])
        return shipment

    def get_tracking(self, tracking_number: str) -> Dict:
        carrier_id = self._get_carrier_id_from_tracking(tracking_number)
        carrier = self._selector.get_carrier(carrier_id) if carrier_id else None
        if carrier:
            return carrier.get_tracking(tracking_number)
        return {'tracking_number': tracking_number, 'status': 'unknown', 'events': []}

    def list_shipments(self) -> List[Dict]:
        return list(self._shipments.values())

    def get_stats(self) -> Dict:
        carriers: Dict[str, int] = {}
        for s in self._shipments.values():
            cid = s.get('carrier_id', 'unknown')
            carriers[cid] = carriers.get(cid, 0) + 1
        return {'total': len(self._shipments), 'by_carrier': carriers}

    def _get_carrier_id_from_tracking(self, tracking_number: str) -> Optional[str]:
        if tracking_number.startswith('CJ'):
            return 'cj_logistics'
        if tracking_number.startswith('HJ'):
            return 'hanjin'
        if tracking_number.startswith('LT'):
            return 'lotte'
        return None
