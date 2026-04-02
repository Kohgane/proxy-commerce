"""tests/e2e/test_inventory_flow.py — E2E: 재고 감소 -> 안전재고 경고 -> 자동 발주 -> 공급자 알림."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))


class TestInventoryFlow:
    """재고 관리 E2E 플로우 테스트."""

    def test_safety_stock_calculation(self):
        """안전 재고 계산 테스트."""
        from src.inventory_sync.safety_stock import SafetyStockCalculator

        calc = SafetyStockCalculator()
        safety_stock = calc.calculate(avg_daily_sales=10.0, lead_time_days=7, safety_factor=1.5)
        assert safety_stock == 105  # ceil(10 * 7 * 1.5)

    def test_reorder_check(self):
        """재주문 필요 여부 확인 테스트."""
        from src.inventory_sync.safety_stock import SafetyStockCalculator

        calc = SafetyStockCalculator()
        calc.set_sku_data('test-sku', avg_daily_sales=10.0, lead_time_days=7)

        assert calc.check_reorder_needed('test-sku', current_stock=5) is True
        assert calc.check_reorder_needed('test-sku', current_stock=500) is False

    def test_purchase_order_creation(self):
        """발주서 생성 테스트."""
        from src.suppliers.purchase_order import PurchaseOrderManager, STATUS_DRAFT

        manager = PurchaseOrderManager()
        order = manager.create('supplier-001', 'test-sku', qty=100)

        assert order['po_id'] is not None
        assert order['status'] == STATUS_DRAFT
        assert order['qty'] == 100

    def test_purchase_order_status_flow(self):
        """발주서 상태 변경 플로우 테스트."""
        from src.suppliers.purchase_order import PurchaseOrderManager
        from src.suppliers.purchase_order import STATUS_SENT, STATUS_CONFIRMED, STATUS_RECEIVED

        manager = PurchaseOrderManager()
        order = manager.create('supplier-001', 'test-sku', qty=50)
        po_id = order['po_id']

        updated = manager.update_status(po_id, STATUS_SENT)
        assert updated['status'] == STATUS_SENT

        updated = manager.update_status(po_id, STATUS_CONFIRMED)
        assert updated['status'] == STATUS_CONFIRMED

        updated = manager.update_status(po_id, STATUS_RECEIVED)
        assert updated['status'] == STATUS_RECEIVED

    def test_supplier_notification(self):
        """공급자 알림 발송 테스트."""
        from src.suppliers.communication import SupplierCommunication

        comm = SupplierCommunication()
        ok = comm.send_email(
            'supplier-001',
            'order',
            context={'po_id': 'PO-001', 'sku': 'test-sku', 'qty': 100}
        )
        assert ok is True

        history = comm.get_sent_history()
        assert len(history) == 1
        assert history[0]['supplier_id'] == 'supplier-001'

    def test_conflict_resolution_conservative(self):
        """보수적 충돌 해소 테스트."""
        from src.inventory_sync.conflict_resolver import ConflictResolver, STRATEGY_CONSERVATIVE

        resolver = ConflictResolver(strategy=STRATEGY_CONSERVATIVE)
        result = resolver.resolve('test-sku', {'coupang': 10, 'naver': 20, 'internal': 15})
        assert result == 10  # 최솟값

    def test_conflict_resolution_last_write_wins(self):
        """최종 쓰기 우선 충돌 해소 테스트."""
        from src.inventory_sync.conflict_resolver import ConflictResolver, STRATEGY_LAST_WRITE_WINS

        resolver = ConflictResolver(strategy=STRATEGY_LAST_WRITE_WINS)
        result = resolver.resolve('test-sku', {'coupang': 10, 'naver': 20, 'internal': 15})
        assert result == 15  # 마지막 값

    def test_full_inventory_flow(self):
        """전체 재고 플로우 통합 테스트."""
        from src.inventory_sync.safety_stock import SafetyStockCalculator
        from src.suppliers.purchase_order import PurchaseOrderManager
        from src.suppliers.communication import SupplierCommunication
        from src.notifications.notification_hub import NotificationHub, EVENT_STOCK_LOW

        calc = SafetyStockCalculator()
        calc.set_sku_data('flow-sku', avg_daily_sales=5.0, lead_time_days=7)

        reorder_needed = calc.check_reorder_needed('flow-sku', current_stock=10)
        assert reorder_needed is True

        po_manager = PurchaseOrderManager()
        order = po_manager.create('supplier-001', 'flow-sku', qty=200)
        assert order['po_id'] is not None

        comm = SupplierCommunication()
        sent = comm.send_email('supplier-001', 'order',
                               context={'po_id': order['po_id'], 'sku': 'flow-sku', 'qty': 200})
        assert sent is True

        hub = NotificationHub()
        results = hub.dispatch(EVENT_STOCK_LOW, 'admin', '재고 부족 경고: flow-sku')
        assert isinstance(results, dict)
