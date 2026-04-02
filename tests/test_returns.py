"""tests/test_returns.py — Phase 37: 반품/교환 관리 테스트."""
import pytest
from decimal import Decimal


class TestReturnManager:
    def setup_method(self):
        from src.returns.return_manager import ReturnManager
        self.manager = ReturnManager()

    def test_create_return(self):
        record = self.manager.create({'order_id': 'ORD-001', 'reason': '불량', 'type': 'return'})
        assert record['order_id'] == 'ORD-001'
        assert record['status'] == 'requested'
        assert 'id' in record

    def test_get_return(self):
        record = self.manager.create({'order_id': 'ORD-001'})
        fetched = self.manager.get(record['id'])
        assert fetched is not None
        assert fetched['id'] == record['id']

    def test_get_nonexistent(self):
        assert self.manager.get('nonexistent') is None

    def test_list_all(self):
        self.manager.create({'order_id': 'ORD-001'})
        self.manager.create({'order_id': 'ORD-002'})
        items = self.manager.list_all()
        assert len(items) == 2

    def test_list_by_status(self):
        self.manager.create({'order_id': 'ORD-001'})
        items = self.manager.list_all(status='requested')
        assert len(items) == 1

    def test_list_by_order_id(self):
        self.manager.create({'order_id': 'ORD-001'})
        self.manager.create({'order_id': 'ORD-002'})
        items = self.manager.list_all(order_id='ORD-001')
        assert len(items) == 1

    def test_update_status_valid(self):
        record = self.manager.create({})
        updated = self.manager.update_status(record['id'], 'approved')
        assert updated['status'] == 'approved'

    def test_update_status_invalid_transition(self):
        record = self.manager.create({})
        with pytest.raises(ValueError):
            self.manager.update_status(record['id'], 'refunded')

    def test_update_status_not_found(self):
        result = self.manager.update_status('invalid', 'approved')
        assert result is None

    def test_set_inspection(self):
        record = self.manager.create({})
        updated = self.manager.set_inspection(record['id'], 'A', Decimal('50000'))
        assert updated['inspection_grade'] == 'A'
        assert updated['refund_amount'] == '50000'

    def test_delete(self):
        record = self.manager.create({})
        ok = self.manager.delete(record['id'])
        assert ok is True
        assert self.manager.get(record['id']) is None

    def test_delete_nonexistent(self):
        assert self.manager.delete('nonexistent') is False

    def test_full_status_flow(self):
        record = self.manager.create({'type': 'return'})
        self.manager.update_status(record['id'], 'approved')
        self.manager.update_status(record['id'], 'received')
        self.manager.update_status(record['id'], 'inspected')
        final = self.manager.update_status(record['id'], 'refunded')
        assert final['status'] == 'refunded'


class TestRefundCalculator:
    def setup_method(self):
        from src.returns.refund_calculator import RefundCalculator
        self.calc = RefundCalculator(shipping_deduction=Decimal('3000'))

    def test_grade_a_full_refund(self):
        result = self.calc.calculate(Decimal('50000'), grade='A')
        assert result['refund_amount'] == '47000'  # 50000 - 3000

    def test_grade_b_90_percent(self):
        result = self.calc.calculate(Decimal('50000'), grade='B')
        # (50000 - 3000) * 0.9 = 42300
        assert result['refund_amount'] == '42300'

    def test_grade_c_70_percent(self):
        result = self.calc.calculate(Decimal('50000'), grade='C')
        # (50000 - 3000) * 0.7 = 32900
        assert result['refund_amount'] == '32900'

    def test_grade_d_no_refund(self):
        result = self.calc.calculate(Decimal('50000'), grade='D')
        assert result['refund_amount'] == '0'

    def test_no_shipping_deduction(self):
        result = self.calc.calculate(Decimal('50000'), grade='A', deduct_shipping=False)
        assert result['refund_amount'] == '50000'

    def test_coupon_discount(self):
        result = self.calc.calculate(Decimal('50000'), grade='A', coupon_discount=Decimal('5000'))
        # (50000 - 5000 - 3000) * 1.0 = 42000
        assert result['refund_amount'] == '42000'

    def test_partial_ratio(self):
        result = self.calc.calculate(Decimal('50000'), partial_ratio=Decimal('0.5'))
        # (50000 - 3000) * 0.5 = 23500
        assert result['refund_amount'] == '23500'

    def test_calculate_partial(self):
        refund = self.calc.calculate_partial(Decimal('60000'), items_returned=2, total_items=4)
        assert refund == Decimal('30000')


class TestInspectionService:
    def setup_method(self):
        from src.returns.inspection import InspectionService
        self.service = InspectionService()

    def test_grade_a(self):
        assert self.service.grade(98, packaging_intact=True, functional=True) == 'A'

    def test_grade_b(self):
        assert self.service.grade(85, packaging_intact=False, functional=True) == 'B'

    def test_grade_c(self):
        assert self.service.grade(60, functional=True) == 'C'

    def test_grade_d_nonfunctional(self):
        assert self.service.grade(90, functional=False) == 'D'

    def test_grade_d_low_score(self):
        assert self.service.grade(30, functional=True) == 'D'

    def test_get_refund_ratio(self):
        assert self.service.get_refund_ratio('A') == Decimal('1.0')
        assert self.service.get_refund_ratio('B') == Decimal('0.9')
        assert self.service.get_refund_ratio('C') == Decimal('0.7')
        assert self.service.get_refund_ratio('D') == Decimal('0.0')

    def test_inspect(self):
        result = self.service.inspect('RET-001', 90, packaging_intact=True, functional=True)
        assert result['return_id'] == 'RET-001'
        assert result['grade'] in ('A', 'B', 'C', 'D')
        assert 'refund_pct' in result

    def test_get_grade_info(self):
        info = self.service.get_grade_info('A')
        assert info is not None
        assert info['refund_pct'] == 100


class TestExchangeHandler:
    def setup_method(self):
        from src.returns.exchange_handler import ExchangeHandler
        self.handler = ExchangeHandler()

    def test_create_exchange_same_product(self):
        exchange = self.handler.create_exchange('RET-001', 'PROD-001', same_product=True)
        assert exchange['same_product'] is True
        assert exchange['status'] == 'pending'

    def test_create_exchange_option_change(self):
        exchange = self.handler.create_exchange(
            'RET-001', 'PROD-001',
            original_option='빨간색 M',
            new_option='파란색 L',
            same_product=False,
        )
        assert exchange['option_changed'] is True

    def test_ship(self):
        exchange = self.handler.create_exchange('RET-001', 'PROD-001')
        shipped = self.handler.ship(exchange['id'], 'TRACK-123')
        assert shipped['status'] == 'shipped'
        assert shipped['tracking_number'] == 'TRACK-123'

    def test_complete(self):
        exchange = self.handler.create_exchange('RET-001', 'PROD-001')
        completed = self.handler.complete(exchange['id'])
        assert completed['status'] == 'completed'

    def test_list_by_return(self):
        self.handler.create_exchange('RET-001', 'PROD-001')
        self.handler.create_exchange('RET-001', 'PROD-002')
        self.handler.create_exchange('RET-002', 'PROD-001')
        items = self.handler.list_by_return('RET-001')
        assert len(items) == 2


class TestReturnsAPI:
    def setup_method(self):
        import sys
        import os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
        from flask import Flask
        from src.api.returns_api import returns_bp
        app = Flask(__name__)
        app.register_blueprint(returns_bp)
        self.client = app.test_client()

    def test_status(self):
        resp = self.client.get('/api/v1/returns/status')
        assert resp.status_code == 200

    def test_create_and_list(self):
        resp = self.client.post('/api/v1/returns/', json={'order_id': 'ORD-001', 'reason': '불량'})
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['order_id'] == 'ORD-001'

    def test_calculate_refund(self):
        resp = self.client.post('/api/v1/returns/refund/calculate',
                                json={'original_amount': 50000, 'grade': 'A'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'refund_amount' in data
