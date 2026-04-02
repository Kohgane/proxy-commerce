"""tests/test_coupons.py — Phase 38: 쿠폰/프로모션 코드 시스템 테스트."""
import pytest
from decimal import Decimal


class TestCouponManager:
    def setup_method(self):
        from src.coupons.coupon_manager import CouponManager
        self.manager = CouponManager()

    def test_create_percentage_coupon(self):
        coupon = self.manager.create({'code': 'SAVE10', 'type': 'percentage', 'value': 10})
        assert coupon['code'] == 'SAVE10'
        assert coupon['type'] == 'percentage'

    def test_create_fixed_coupon(self):
        coupon = self.manager.create({'code': 'FLAT5K', 'type': 'fixed_amount', 'value': 5000})
        assert coupon['type'] == 'fixed_amount'

    def test_create_free_shipping(self):
        coupon = self.manager.create({'code': 'FREESHIP', 'type': 'free_shipping', 'value': 0})
        assert coupon['type'] == 'free_shipping'

    def test_create_invalid_type(self):
        with pytest.raises(ValueError):
            self.manager.create({'code': 'BAD', 'type': 'invalid_type'})

    def test_get_by_code(self):
        coupon = self.manager.create({'code': 'FIND01', 'type': 'percentage', 'value': 5})
        found = self.manager.get_by_code('FIND01')
        assert found is not None
        assert found['id'] == coupon['id']

    def test_get_by_code_case_insensitive(self):
        self.manager.create({'code': 'UPPER', 'type': 'percentage', 'value': 5})
        found = self.manager.get_by_code('upper')
        assert found is not None

    def test_list_all(self):
        self.manager.create({'code': 'C1', 'type': 'percentage', 'value': 5})
        self.manager.create({'code': 'C2', 'type': 'fixed_amount', 'value': 1000})
        assert len(self.manager.list_all()) == 2

    def test_list_active_only(self):
        self.manager.create({'code': 'ACTIVE', 'type': 'percentage', 'value': 5, 'active': True})
        self.manager.create({'code': 'INACTIVE', 'type': 'percentage', 'value': 5, 'active': False})
        active = self.manager.list_all(active_only=True)
        assert len(active) == 1

    def test_deactivate(self):
        coupon = self.manager.create({'code': 'DEACT', 'type': 'percentage', 'value': 5})
        ok = self.manager.deactivate(coupon['id'])
        assert ok is True
        assert not self.manager.get(coupon['id'])['active']

    def test_validate_valid_coupon(self):
        self.manager.create({'code': 'VALID10', 'type': 'percentage', 'value': 10})
        result = self.manager.validate('VALID10', Decimal('20000'))
        assert result['valid'] is True

    def test_validate_nonexistent(self):
        result = self.manager.validate('NONEXIST')
        assert result['valid'] is False

    def test_validate_inactive(self):
        coupon = self.manager.create({'code': 'GONE', 'type': 'percentage', 'value': 5})
        self.manager.deactivate(coupon['id'])
        result = self.manager.validate('GONE')
        assert result['valid'] is False

    def test_validate_min_amount(self):
        self.manager.create({'code': 'MINAMT', 'type': 'percentage', 'value': 10, 'min_order_amount': 50000})
        result = self.manager.validate('MINAMT', Decimal('30000'))
        assert result['valid'] is False

    def test_increment_usage(self):
        coupon = self.manager.create({'code': 'USE01', 'type': 'percentage', 'value': 5})
        self.manager.increment_usage(coupon['id'])
        assert self.manager.get(coupon['id'])['used_count'] == 1

    def test_usage_limit_exceeded(self):
        coupon = self.manager.create({'code': 'LIMIT1', 'type': 'percentage', 'value': 5, 'usage_limit': 1})
        self.manager.increment_usage(coupon['id'])
        result = self.manager.validate('LIMIT1')
        assert result['valid'] is False


class TestCodeGenerator:
    def setup_method(self):
        from src.coupons.code_generator import CodeGenerator
        self.gen = CodeGenerator(length=8)

    def test_generate_code(self):
        code = self.gen.generate()
        assert len(code) == 8

    def test_generate_with_prefix(self):
        code = self.gen.generate(prefix='SUMMER')
        assert code.startswith('SUMMER-')
        assert len(code) == 15  # SUMMER-(8)

    def test_generate_batch(self):
        codes = self.gen.generate_batch(10)
        assert len(codes) == 10
        assert len(set(codes)) == 10  # 중복 없음

    def test_generate_batch_with_prefix(self):
        codes = self.gen.generate_batch(5, prefix='TEST')
        assert all(c.startswith('TEST-') for c in codes)

    def test_generate_seasonal(self):
        codes = self.gen.generate_seasonal('SUMMER', 2024, count=3)
        assert len(codes) == 3
        assert all('SUMMER2024' in c for c in codes)


class TestRedemptionService:
    def setup_method(self):
        from src.coupons.redemption import RedemptionService
        self.service = RedemptionService()

    def test_redeem(self):
        record = self.service.redeem('COUP-001', 'ORD-001', 'USER-001', Decimal('5000'))
        assert record['coupon_id'] == 'COUP-001'
        assert record['order_id'] == 'ORD-001'

    def test_prevent_duplicate(self):
        self.service.redeem('COUP-001', 'ORD-001', 'USER-001', Decimal('5000'))
        with pytest.raises(ValueError):
            self.service.redeem('COUP-001', 'ORD-001', 'USER-001', Decimal('5000'))

    def test_different_orders_allowed(self):
        self.service.redeem('COUP-001', 'ORD-001', 'USER-001', Decimal('5000'))
        record = self.service.redeem('COUP-001', 'ORD-002', 'USER-002', Decimal('5000'))
        assert record['order_id'] == 'ORD-002'

    def test_get_history(self):
        self.service.redeem('COUP-001', 'ORD-001', 'USER-001', Decimal('5000'))
        history = self.service.get_history(coupon_id='COUP-001')
        assert len(history) == 1

    def test_is_used(self):
        self.service.redeem('COUP-001', 'ORD-001', 'USER-001', Decimal('5000'))
        assert self.service.is_used('COUP-001', 'ORD-001') is True
        assert self.service.is_used('COUP-001', 'ORD-999') is False

    def test_usage_count(self):
        self.service.redeem('COUP-001', 'ORD-001', 'USER-001', Decimal('5000'))
        self.service.redeem('COUP-001', 'ORD-002', 'USER-002', Decimal('5000'))
        assert self.service.usage_count('COUP-001') == 2


class TestCouponRules:
    def test_min_order_amount_rule_pass(self):
        from src.coupons.rules import MinOrderAmountRule
        rule = MinOrderAmountRule()
        order = {'total_amount': 50000}
        coupon = {'type': 'percentage', 'value': '10', 'min_order_amount': '30000', 'max_discount': '0'}
        assert rule.is_applicable(order, coupon) is True

    def test_min_order_amount_rule_fail(self):
        from src.coupons.rules import MinOrderAmountRule
        rule = MinOrderAmountRule()
        order = {'total_amount': 20000}
        coupon = {'type': 'percentage', 'value': '10', 'min_order_amount': '30000', 'max_discount': '0'}
        assert rule.is_applicable(order, coupon) is False

    def test_date_range_rule_valid(self):
        from src.coupons.rules import DateRangeRule
        rule = DateRangeRule()
        coupon = {'valid_from': '', 'valid_until': ''}
        assert rule.is_applicable({}, coupon) is True

    def test_first_purchase_rule_new_user(self):
        from src.coupons.rules import FirstPurchaseRule
        rule = FirstPurchaseRule(purchase_history=[])
        coupon = {'first_purchase_only': True}
        order = {'user_id': 'NEW-USER'}
        assert rule.is_applicable(order, coupon) is True

    def test_first_purchase_rule_existing_user(self):
        from src.coupons.rules import FirstPurchaseRule
        rule = FirstPurchaseRule(purchase_history=['EXISTING-USER'])
        coupon = {'first_purchase_only': True}
        order = {'user_id': 'EXISTING-USER'}
        assert rule.is_applicable(order, coupon) is False

    def test_product_category_rule_matching(self):
        from src.coupons.rules import ProductCategoryRule
        rule = ProductCategoryRule()
        order = {'total_amount': 50000, 'items': [{'category': '전자제품', 'price': 50000, 'qty': 1}]}
        coupon = {'type': 'percentage', 'value': '10', 'max_discount': '0', 'applicable_categories': ['전자제품']}
        assert rule.is_applicable(order, coupon) is True

    def test_percentage_discount_calculation(self):
        from src.coupons.rules import MinOrderAmountRule
        rule = MinOrderAmountRule()
        order = {'total_amount': 100000}
        coupon = {'type': 'percentage', 'value': '10', 'min_order_amount': '0', 'max_discount': '0'}
        discount = rule.calculate_discount(order, coupon)
        assert discount == Decimal('10000')

    def test_fixed_discount_calculation(self):
        from src.coupons.rules import MinOrderAmountRule
        rule = MinOrderAmountRule()
        order = {'total_amount': 100000}
        coupon = {'type': 'fixed_amount', 'value': '5000', 'min_order_amount': '0', 'max_discount': '0'}
        discount = rule.calculate_discount(order, coupon)
        assert discount == Decimal('5000')


class TestCouponsAPI:
    def setup_method(self):
        from flask import Flask
        from src.api.coupons_api import coupons_bp
        app = Flask(__name__)
        app.register_blueprint(coupons_bp)
        self.client = app.test_client()

    def test_status(self):
        resp = self.client.get('/api/v1/coupons/status')
        assert resp.status_code == 200

    def test_create_coupon(self):
        resp = self.client.post('/api/v1/coupons/', json={
            'code': 'API10', 'type': 'percentage', 'value': 10
        })
        assert resp.status_code == 201

    def test_validate_nonexistent(self):
        resp = self.client.post('/api/v1/coupons/validate', json={'code': 'NOEXIST'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['valid'] is False

    def test_generate_codes(self):
        resp = self.client.post('/api/v1/coupons/generate', json={'count': 3, 'prefix': 'TEST'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['count'] == 3
        assert len(data['codes']) == 3
