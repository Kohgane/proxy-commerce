"""src/virtual_inventory/virtual_inventory_dashboard.py — 가상 재고 대시보드 (Phase 113)."""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class VirtualInventoryDashboard:
    """가상 재고 통합 대시보드."""

    def __init__(self) -> None:
        self._stock_pool = None
        self._alert_service = None
        self._analytics = None
        self._sync_bridge = None
        self._allocator = None

    def set_components(self, stock_pool, alert_service, analytics, sync_bridge, allocator) -> None:
        self._stock_pool = stock_pool
        self._alert_service = alert_service
        self._analytics = analytics
        self._sync_bridge = sync_bridge
        self._allocator = allocator

    def get_dashboard_data(self) -> dict:
        """대시보드 데이터 조합."""
        result: dict = {}

        if self._analytics:
            result['stock_health'] = self._analytics.get_stock_health()
            result['source_distribution'] = self._analytics.get_source_distribution()
            result['single_source_risks'] = self._analytics.get_single_source_products()
        else:
            result['stock_health'] = {}
            result['source_distribution'] = {}
            result['single_source_risks'] = []

        # Top 10 lowest sellable
        if self._stock_pool:
            all_stocks = self._stock_pool.get_all_virtual_stocks()
            sorted_stocks = sorted(all_stocks, key=lambda vs: vs.sellable)
            result['low_stock_products'] = [
                {'product_id': vs.product_id, 'sellable': vs.sellable}
                for vs in sorted_stocks[:10]
            ]
        else:
            result['low_stock_products'] = []

        # Recent reservations (last 10)
        if self._stock_pool:
            reservations = self._stock_pool.get_reservations()
            recent = reservations[-10:]
            result['recent_activity'] = [
                {
                    'reservation_id': r.reservation_id,
                    'product_id': r.product_id,
                    'quantity': r.quantity,
                    'status': r.status.value,
                }
                for r in recent
            ]
            pending = sum(1 for r in reservations if r.status.value == 'pending')
            result['reservations'] = {
                'pending_count': pending,
                'total_count': len(reservations),
            }
        else:
            result['recent_activity'] = []
            result['reservations'] = {'pending_count': 0, 'total_count': 0}

        if self._alert_service:
            result['alerts'] = self._alert_service.get_alert_summary()
        else:
            result['alerts'] = {}

        if self._sync_bridge:
            result['sync_status'] = self._sync_bridge.get_sync_status()
        else:
            result['sync_status'] = {}

        return result
