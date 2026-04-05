"""src/fulfillment/dashboard.py — 풀필먼트 대시보드 (Phase 103)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class FulfillmentDashboard:
    """풀필먼트 대시보드 — 통합 현황 및 통계."""

    def __init__(
        self,
        engine=None,
        inspection_service=None,
        packing_service=None,
        shipping_manager=None,
        tracking_manager=None,
        delivery_tracker=None,
    ):
        self._engine = engine
        self._inspection = inspection_service
        self._packing = packing_service
        self._shipping = shipping_manager
        self._tracking = tracking_manager
        self._delivery = delivery_tracker

    def get_summary(self) -> Dict:
        """전체 현황 요약을 반환한다."""
        engine_stats = self._engine.get_stats() if self._engine else {}
        inspection_stats = self._inspection.get_stats() if self._inspection else {}
        packing_stats = self._packing.get_stats() if self._packing else {}
        shipping_stats = self._shipping.get_stats() if self._shipping else {}
        tracking_stats = self._tracking.get_stats() if self._tracking else {}
        delivery_stats = self._delivery.get_stats() if self._delivery else {}
        return {
            'fulfillment_orders': engine_stats,
            'inspection': inspection_stats,
            'packing': packing_stats,
            'shipping': shipping_stats,
            'tracking': tracking_stats,
            'delivery': delivery_stats,
            'generated_at': datetime.now(timezone.utc).isoformat(),
        }

    def get_processing_stats(self) -> Dict:
        """단계별 처리 현황을 반환한다."""
        engine_stats = self._engine.get_stats() if self._engine else {'by_status': {}}
        by_status = engine_stats.get('by_status', {})
        return {
            'received': by_status.get('received', 0),
            'inspecting': by_status.get('inspecting', 0),
            'packing': by_status.get('packing', 0),
            'ready_to_ship': by_status.get('ready_to_ship', 0),
            'shipped': by_status.get('shipped', 0),
            'in_transit': by_status.get('in_transit', 0),
            'delivered': by_status.get('delivered', 0),
        }

    def get_carrier_performance(self) -> List[Dict]:
        """택배사별 배송 성과를 반환한다."""
        shipping_stats = self._shipping.get_stats() if self._shipping else {}
        by_carrier = shipping_stats.get('by_carrier', {})
        return [
            {'carrier_id': cid, 'shipment_count': count}
            for cid, count in by_carrier.items()
        ]
