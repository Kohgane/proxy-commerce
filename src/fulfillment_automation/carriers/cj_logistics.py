"""src/fulfillment_automation/carriers/cj_logistics.py — CJ대한통운 mock 구현 (Phase 84)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Dict

from .base import CarrierBase


class CJLogisticsCarrier(CarrierBase):
    """CJ대한통운 택배사 mock 구현."""

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
            'carrier_name': self.name,
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
