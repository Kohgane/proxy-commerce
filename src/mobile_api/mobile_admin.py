"""src/mobile_api/mobile_admin.py — 모바일 관리자 서비스."""
from __future__ import annotations

import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class MobileAdminService:
    """모바일 관리자 대시보드 서비스."""

    def __init__(self):
        self._sample_orders = [
            {'order_id': f'ORD{i:04d}', 'user_id': f'user_{i}', 'total': 100.0 * i,
             'status': 'pending', 'created_at': time.time() - i * 3600}
            for i in range(1, 6)
        ]
        self._alerts = [
            {'type': 'inventory', 'message': '상품 P001 재고 부족 (5개 미만)', 'severity': 'warning', 'created_at': time.time() - 1800},
            {'type': 'payment', 'message': '결제 오류 급증 감지', 'severity': 'critical', 'created_at': time.time() - 600},
            {'type': 'system', 'message': '서버 응답시간 증가', 'severity': 'info', 'created_at': time.time() - 300},
        ]

    def get_dashboard_summary(self) -> dict:
        return {
            'order_count': 42,
            'revenue': 12345.67,
            'inventory_alerts': 3,
            'pending_cs': 7,
            'active_users': 128,
            'timestamp': time.time(),
        }

    def get_pending_orders(self, limit: int = 20) -> list[dict]:
        return self._sample_orders[:limit]

    def approve_order(self, order_id: str, admin_id: str) -> dict:
        for order in self._sample_orders:
            if order['order_id'] == order_id:
                order['status'] = 'confirmed'
                return {'success': True, 'order_id': order_id, 'status': 'confirmed'}
        return {'success': False, 'order_id': order_id, 'status': 'not_found'}

    def cancel_order(self, order_id: str, admin_id: str, reason: str) -> dict:
        for order in self._sample_orders:
            if order['order_id'] == order_id:
                order['status'] = 'cancelled'
                return {'success': True, 'order_id': order_id, 'status': 'cancelled', 'reason': reason}
        return {'success': False, 'order_id': order_id, 'status': 'not_found'}

    def get_inventory_status(self, limit: int = 20) -> list[dict]:
        return [
            {'sku': f'P{i:03d}', 'name': f'Product {i}', 'stock': max(0, 50 - i * 5),
             'reorder_point': 10, 'needs_reorder': (50 - i * 5) < 10}
            for i in range(1, min(limit + 1, 11))
        ]

    def get_system_alerts(self, limit: int = 20) -> list[dict]:
        return self._alerts[:limit]

    def get_import_export_status(self) -> dict:
        return {
            'import_orders': {'count': 15, 'pending': 5, 'processing': 7, 'completed': 3},
            'export_orders': {'count': 8, 'pending': 2, 'processing': 3, 'completed': 3},
        }
