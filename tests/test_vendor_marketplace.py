"""tests/test_vendor_marketplace.py — Phase 98: 멀티벤더 마켓플레이스 테스트."""
from __future__ import annotations

import sys
import os
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest


# ─── VendorModels ──────────────────────────────────────────────────────────

class TestVendorModels:
    def test_vendor_defaults(self):
        from src.vendor_marketplace.vendor_models import Vendor, VendorStatus, VendorTier
        v = Vendor()
        assert v.status == VendorStatus.pending
        assert v.tier == VendorTier.basic
        assert v.vendor_id != ''

    def test_vendor_to_dict(self):
        from src.vendor_marketplace.vendor_models import Vendor
        v = Vendor(name='테스트샵', email='test@example.com')
        d = v.to_dict()
        assert d['name'] == '테스트샵'
        assert d['email'] == 'test@example.com'
        assert 'vendor_id' in d
        assert 'status' in d
        assert 'tier' in d

    def test_vendor_touch(self):
        from src.vendor_marketplace.vendor_models import Vendor
        v = Vendor()
        old_time = v.updated_at
        import time; time.sleep(0.01)
        v.touch()
        assert v.updated_at >= old_time

    def test_vendor_status_values(self):
        from src.vendor_marketplace.vendor_models import VendorStatus
        assert VendorStatus.pending.value == 'pending'
        assert VendorStatus.active.value == 'active'
        assert VendorStatus.suspended.value == 'suspended'
        assert VendorStatus.deactivated.value == 'deactivated'

    def test_vendor_tier_values(self):
        from src.vendor_marketplace.vendor_models import VendorTier
        assert VendorTier.basic.value == 'basic'
        assert VendorTier.enterprise.value == 'enterprise'

    def test_tier_commission_rates(self):
        from src.vendor_marketplace.vendor_models import TIER_COMMISSION_RATES
        assert TIER_COMMISSION_RATES['basic'] == 15.0
        assert TIER_COMMISSION_RATES['standard'] == 12.0
        assert TIER_COMMISSION_RATES['premium'] == 10.0
        assert TIER_COMMISSION_RATES['enterprise'] == 8.0

    def test_tier_product_limits(self):
        from src.vendor_marketplace.vendor_models import TIER_PRODUCT_LIMITS
        assert TIER_PRODUCT_LIMITS['basic'] == 50
        assert TIER_PRODUCT_LIMITS['standard'] == 200
        assert TIER_PRODUCT_LIMITS['premium'] == 1000
        assert TIER_PRODUCT_LIMITS['enterprise'] is None

    def test_vendor_profile_to_dict(self):
        from src.vendor_marketplace.vendor_models import VendorProfile
        p = VendorProfile(vendor_id='V001', brand_name='브랜드A')
        d = p.to_dict()
        assert d['vendor_id'] == 'V001'
        assert d['brand_name'] == '브랜드A'

    def test_vendor_agreement_record_to_dict(self):
        from src.vendor_marketplace.vendor_models import VendorAgreementRecord
        a = VendorAgreementRecord(vendor_id='V001', required_terms_agreed=True)
        d = a.to_dict()
        assert d['required_terms_agreed'] is True
        assert 'agreement_id' in d

    def test_vendor_document_to_dict(self):
        from src.vendor_marketplace.vendor_models import VendorDocument
        doc = VendorDocument(vendor_id='V001', doc_type='business_license', file_name='license.pdf')
        d = doc.to_dict()
        assert d['doc_type'] == 'business_license'
        assert d['status'] == 'pending'


# ─── VendorVerification ────────────────────────────────────────────────────

class TestVendorVerification:
    def setup_method(self):
        from src.vendor_marketplace.vendor_manager import VendorVerification
        self.verif = VendorVerification()

    def test_valid_business_number(self):
        assert self.verif.validate_business_number('123-45-67890') is True

    def test_invalid_business_number_format(self):
        assert self.verif.validate_business_number('1234567890') is False
        assert self.verif.validate_business_number('123-456-7890') is False
        assert self.verif.validate_business_number('') is False

    def test_verify_identity_success(self):
        result = self.verif.verify_identity('V001', '123456')
        assert result['success'] is True
        assert result['vendor_id'] == 'V001'

    def test_verify_identity_fail(self):
        result = self.verif.verify_identity('V001', '123')
        assert result['success'] is False

    def test_simulate_document_upload(self):
        from src.vendor_marketplace.vendor_models import VendorDocument
        doc = self.verif.simulate_document_upload('V001', 'business_license', 'biz.pdf', 1024)
        assert isinstance(doc, VendorDocument)
        assert doc.status == 'pending'
        assert doc.doc_type == 'business_license'


# ─── VendorAgreement ──────────────────────────────────────────────────────

class TestVendorAgreement:
    def setup_method(self):
        from src.vendor_marketplace.vendor_manager import VendorAgreement
        self.agreement = VendorAgreement()

    def test_record_agreement(self):
        rec = self.agreement.record_agreement('V001', required=True, optional=True)
        assert rec.required_terms_agreed is True
        assert rec.optional_terms_agreed is True

    def test_has_valid_agreement_true(self):
        self.agreement.record_agreement('V001', required=True)
        assert self.agreement.has_valid_agreement('V001') is True

    def test_has_valid_agreement_false_no_required(self):
        self.agreement.record_agreement('V001', required=False)
        assert self.agreement.has_valid_agreement('V001') is False

    def test_has_valid_agreement_not_exists(self):
        assert self.agreement.has_valid_agreement('V999') is False

    def test_get_agreement(self):
        self.agreement.record_agreement('V001', required=True)
        rec = self.agreement.get_agreement('V001')
        assert rec is not None
        assert rec.vendor_id == 'V001'


# ─── VendorOnboardingManager ──────────────────────────────────────────────

class TestVendorOnboardingManager:
    def setup_method(self):
        from src.vendor_marketplace.vendor_manager import VendorOnboardingManager
        self.mgr = VendorOnboardingManager()

    def _apply(self, name='테스트샵', biz_num='123-45-67890'):
        return self.mgr.apply(
            name=name, email='test@test.com', phone='010-1234-5678',
            business_number=biz_num,
        )

    def test_apply_success(self):
        from src.vendor_marketplace.vendor_models import VendorStatus
        vendor = self._apply()
        assert vendor.name == '테스트샵'
        assert vendor.status == VendorStatus.pending

    def test_apply_invalid_biz_num(self):
        with pytest.raises(ValueError):
            self.mgr.apply('샵', 'a@a.com', '010', 'INVALID')

    def test_submit_for_review(self):
        from src.vendor_marketplace.vendor_models import VendorStatus
        v = self._apply()
        v2 = self.mgr.submit_for_review(v.vendor_id)
        assert v2.status == VendorStatus.under_review

    def test_approve_from_under_review(self):
        from src.vendor_marketplace.vendor_models import VendorStatus
        v = self._apply()
        self.mgr.submit_for_review(v.vendor_id)
        v2 = self.mgr.approve(v.vendor_id)
        assert v2.status == VendorStatus.approved

    def test_reject_returns_to_pending(self):
        from src.vendor_marketplace.vendor_models import VendorStatus
        v = self._apply()
        self.mgr.submit_for_review(v.vendor_id)
        v2 = self.mgr.reject(v.vendor_id, '서류 미비')
        assert v2.status == VendorStatus.pending

    def test_activate(self):
        from src.vendor_marketplace.vendor_models import VendorStatus
        v = self._apply()
        self.mgr.submit_for_review(v.vendor_id)
        self.mgr.approve(v.vendor_id)
        v2 = self.mgr.activate(v.vendor_id)
        assert v2.status == VendorStatus.active

    def test_suspend_active_vendor(self):
        from src.vendor_marketplace.vendor_models import VendorStatus
        v = self._apply()
        self.mgr.submit_for_review(v.vendor_id)
        self.mgr.approve(v.vendor_id)
        self.mgr.activate(v.vendor_id)
        v2 = self.mgr.suspend(v.vendor_id, '규정 위반')
        assert v2.status == VendorStatus.suspended

    def test_invalid_transition_raises(self):
        v = self._apply()
        with pytest.raises(ValueError):
            self.mgr.approve(v.vendor_id)  # pending → approved 불가

    def test_deactivate(self):
        from src.vendor_marketplace.vendor_models import VendorStatus
        v = self._apply()
        self.mgr.submit_for_review(v.vendor_id)
        self.mgr.approve(v.vendor_id)
        self.mgr.activate(v.vendor_id)
        v2 = self.mgr.deactivate(v.vendor_id)
        assert v2.status == VendorStatus.deactivated

    def test_upload_document(self):
        v = self._apply()
        doc = self.mgr.upload_document(v.vendor_id, 'business_license', 'biz.pdf', 2048)
        assert doc.vendor_id == v.vendor_id
        assert doc.status == 'pending'

    def test_verify_document(self):
        v = self._apply()
        doc = self.mgr.upload_document(v.vendor_id, 'id_card', 'id.jpg', 512)
        verified = self.mgr.verify_document(v.vendor_id, doc.doc_id)
        assert verified.status == 'verified'

    def test_verify_document_not_found(self):
        v = self._apply()
        with pytest.raises(KeyError):
            self.mgr.verify_document(v.vendor_id, 'nonexistent-id')

    def test_get_documents(self):
        v = self._apply()
        self.mgr.upload_document(v.vendor_id, 'business_license', 'biz.pdf')
        self.mgr.upload_document(v.vendor_id, 'id_card', 'id.jpg')
        docs = self.mgr.get_documents(v.vendor_id)
        assert len(docs) == 2

    def test_record_agreement(self):
        v = self._apply()
        rec = self.mgr.record_agreement(v.vendor_id, required=True)
        assert rec.required_terms_agreed is True
        assert self.mgr.has_valid_agreement(v.vendor_id) is True

    def test_get_vendor(self):
        v = self._apply()
        found = self.mgr.get_vendor(v.vendor_id)
        assert found is not None
        assert found.vendor_id == v.vendor_id

    def test_get_vendor_not_found(self):
        assert self.mgr.get_vendor('nonexistent') is None

    def test_list_vendors_all(self):
        self._apply('샵1')
        self._apply('샵2')
        vendors = self.mgr.list_vendors()
        assert len(vendors) >= 2

    def test_list_vendors_by_status(self):
        from src.vendor_marketplace.vendor_models import VendorStatus
        v = self._apply()
        self.mgr.submit_for_review(v.vendor_id)
        vendors = self.mgr.list_vendors(status='under_review')
        assert all(x.status == VendorStatus.under_review for x in vendors)

    def test_vendor_not_found_raises(self):
        with pytest.raises(KeyError):
            self.mgr.submit_for_review('NONEXISTENT')


# ─── VendorProfileManager ─────────────────────────────────────────────────

class TestVendorProfileManager:
    def setup_method(self):
        from src.vendor_marketplace.vendor_manager import VendorProfileManager
        self.mgr = VendorProfileManager()

    def test_create_profile(self):
        profile = self.mgr.create_or_update('V001', brand_name='브랜드A', description='설명')
        assert profile.brand_name == '브랜드A'
        assert profile.description == '설명'

    def test_update_profile(self):
        self.mgr.create_or_update('V001', brand_name='브랜드A')
        updated = self.mgr.create_or_update('V001', brand_name='브랜드B')
        assert updated.brand_name == '브랜드B'

    def test_get_profile(self):
        self.mgr.create_or_update('V001', brand_name='테스트')
        profile = self.mgr.get('V001')
        assert profile is not None
        assert profile.brand_name == '테스트'

    def test_get_nonexistent(self):
        assert self.mgr.get('NONEXISTENT') is None

    def test_delete_profile(self):
        self.mgr.create_or_update('V001', brand_name='삭제테스트')
        result = self.mgr.delete('V001')
        assert result is True
        assert self.mgr.get('V001') is None

    def test_delete_nonexistent(self):
        assert self.mgr.delete('NONEXISTENT') is False

    def test_list_profiles(self):
        self.mgr.create_or_update('V001', brand_name='A')
        self.mgr.create_or_update('V002', brand_name='B')
        profiles = self.mgr.list_profiles()
        assert len(profiles) >= 2


# ─── ProductApprovalService ───────────────────────────────────────────────

class TestProductApprovalService:
    def setup_method(self):
        from src.vendor_marketplace.vendor_products import ProductApprovalService
        self.svc = ProductApprovalService()

    def _good_product(self, **kwargs):
        base = {
            'name': '멋진 상품',
            'description': '품질 좋은 상품입니다',
            'price': 10000,
            'category': 'electronics',
            'images': ['img1.jpg'],
        }
        base.update(kwargs)
        return base

    def test_good_product_passes(self):
        result = self.svc.check(self._good_product())
        assert result['passed'] is True
        assert result['issues'] == []

    def test_forbidden_word_fails(self):
        result = self.svc.check(self._good_product(name='마약 관련 상품'))
        assert result['passed'] is False
        assert any('금지어' in i for i in result['issues'])

    def test_invalid_category_fails(self):
        result = self.svc.check(self._good_product(category='invalid_cat'))
        assert result['passed'] is False

    def test_price_too_low_fails(self):
        result = self.svc.check(self._good_product(price=10))
        assert result['passed'] is False

    def test_no_images_fails(self):
        result = self.svc.check(self._good_product(images=[]))
        assert result['passed'] is False

    def test_price_too_high_fails(self):
        result = self.svc.check(self._good_product(price=200_000_000))
        assert result['passed'] is False


# ─── VendorProductRestriction ─────────────────────────────────────────────

class TestVendorProductRestriction:
    def setup_method(self):
        from src.vendor_marketplace.vendor_products import VendorProductRestriction
        self.restriction = VendorProductRestriction()

    def test_basic_limit(self):
        assert self.restriction.get_limit('basic') == 50

    def test_enterprise_unlimited(self):
        assert self.restriction.get_limit('enterprise') is None
        assert self.restriction.can_add_product('enterprise', 99999) is True

    def test_can_add_within_limit(self):
        assert self.restriction.can_add_product('basic', 49) is True

    def test_cannot_add_at_limit(self):
        assert self.restriction.can_add_product('basic', 50) is False

    def test_standard_limit(self):
        assert self.restriction.get_limit('standard') == 200


# ─── VendorProductManager ─────────────────────────────────────────────────

class TestVendorProductManager:
    def setup_method(self):
        from src.vendor_marketplace.vendor_products import VendorProductManager
        self.mgr = VendorProductManager()

    def _add(self, vendor_id='V001', tier='basic', name='상품A', price=10000):
        return self.mgr.add_product(
            vendor_id=vendor_id,
            vendor_tier=tier,
            name=name,
            price=price,
            category='electronics',
            images=['img.jpg'],
        )

    def test_add_product(self):
        p = self._add()
        assert p['name'] == '상품A'
        assert p['status'] == 'draft'
        assert p['vendor_id'] == 'V001'

    def test_add_product_exceeds_limit(self):
        # basic = 50 limit
        for i in range(50):
            self.mgr.add_product(
                vendor_id='V001', vendor_tier='basic', name=f'상품{i}',
                price=10000, images=['img.jpg'],
            )
        with pytest.raises(PermissionError):
            self._add()

    def test_update_product(self):
        p = self._add()
        updated = self.mgr.update_product('V001', p['product_id'], price=20000)
        assert updated['price'] == 20000

    def test_delete_product(self):
        p = self._add()
        result = self.mgr.delete_product('V001', p['product_id'])
        assert result is True
        assert self.mgr.get_product(p['product_id']) is None

    def test_submit_for_review(self):
        p = self._add()
        submitted = self.mgr.submit_for_review('V001', p['product_id'])
        assert submitted['status'] == 'pending_review'

    def test_approve_product_passes(self):
        p = self._add()
        self.mgr.submit_for_review('V001', p['product_id'])
        approved = self.mgr.approve_product(p['product_id'])
        assert approved['status'] == 'listed'

    def test_approve_product_fails_forbidden_word(self):
        p = self.mgr.add_product(
            vendor_id='V001', vendor_tier='basic', name='불법 상품',
            price=10000, category='electronics', images=['img.jpg'],
        )
        self.mgr.submit_for_review('V001', p['product_id'])
        result = self.mgr.approve_product(p['product_id'])
        assert result['status'] == 'rejected'
        assert len(result['approval_issues']) > 0

    def test_reject_product(self):
        p = self._add()
        self.mgr.submit_for_review('V001', p['product_id'])
        rejected = self.mgr.reject_product(p['product_id'], '가격 부적절')
        assert rejected['status'] == 'rejected'

    def test_list_vendor_products(self):
        self._add(name='상품1')
        self._add(name='상품2')
        products = self.mgr.list_vendor_products('V001')
        assert len(products) >= 2

    def test_list_vendor_products_by_status(self):
        p = self._add()
        self.mgr.submit_for_review('V001', p['product_id'])
        products = self.mgr.list_vendor_products('V001', status='pending_review')
        assert all(x['status'] == 'pending_review' for x in products)

    def test_get_product_wrong_vendor(self):
        p = self._add(vendor_id='V001')
        with pytest.raises(KeyError):
            self.mgr.update_product('V999', p['product_id'], price=1000)

    def test_approve_not_in_review_raises(self):
        p = self._add()
        with pytest.raises(ValueError):
            self.mgr.approve_product(p['product_id'])  # still 'draft'


# ─── VendorInventorySync ──────────────────────────────────────────────────

class TestVendorInventorySync:
    def setup_method(self):
        from src.vendor_marketplace.vendor_products import VendorInventorySync
        self.sync = VendorInventorySync()

    def test_set_and_get_stock(self):
        self.sync.set_stock('P001', 100)
        assert self.sync.get_stock('P001') == 100

    def test_adjust_stock_positive(self):
        self.sync.set_stock('P001', 50)
        new_qty = self.sync.adjust_stock('P001', 10)
        assert new_qty == 60

    def test_adjust_stock_negative(self):
        self.sync.set_stock('P001', 50)
        new_qty = self.sync.adjust_stock('P001', -20)
        assert new_qty == 30

    def test_adjust_stock_below_zero(self):
        self.sync.set_stock('P001', 5)
        new_qty = self.sync.adjust_stock('P001', -100)
        assert new_qty == 0

    def test_get_low_stock_alerts(self):
        self.sync.set_stock('P001', 3)
        self.sync.set_stock('P002', 10)
        alerts = self.sync.get_low_stock_alerts(threshold=5)
        assert len(alerts) == 1
        assert alerts[0]['product_id'] == 'P001'

    def test_bulk_sync(self):
        self.sync.bulk_sync({'P001': 100, 'P002': 50})
        assert self.sync.get_stock('P001') == 100
        assert self.sync.get_stock('P002') == 50


# ─── CommissionRule ───────────────────────────────────────────────────────

class TestCommissionRule:
    def test_effective_rate_no_promo(self):
        from src.vendor_marketplace.commission import CommissionRule
        rule = CommissionRule(vendor_tier='basic', rate=15.0)
        assert rule.effective_rate == 15.0

    def test_effective_rate_with_active_promo(self):
        from src.vendor_marketplace.commission import CommissionRule
        now = datetime.now(timezone.utc)
        rule = CommissionRule(
            vendor_tier='basic',
            rate=15.0,
            promotion_rate=5.0,
            promotion_until=now + timedelta(days=7),
        )
        assert rule.effective_rate == 5.0

    def test_effective_rate_expired_promo(self):
        from src.vendor_marketplace.commission import CommissionRule
        now = datetime.now(timezone.utc)
        rule = CommissionRule(
            vendor_tier='basic',
            rate=15.0,
            promotion_rate=5.0,
            promotion_until=now - timedelta(days=1),
        )
        assert rule.effective_rate == 15.0

    def test_to_dict(self):
        from src.vendor_marketplace.commission import CommissionRule
        rule = CommissionRule(vendor_tier='standard', category='electronics', rate=8.0)
        d = rule.to_dict()
        assert d['vendor_tier'] == 'standard'
        assert d['category'] == 'electronics'
        assert d['rate'] == 8.0


# ─── CommissionCalculator ─────────────────────────────────────────────────

class TestCommissionCalculator:
    def setup_method(self):
        from src.vendor_marketplace.commission import CommissionCalculator
        self.calc = CommissionCalculator()

    def test_basic_tier_default_rate(self):
        result = self.calc.calculate(100000, 'basic')
        assert result['rate'] == 15.0
        assert result['commission'] == 15000.0
        assert result['net_amount'] == 85000.0

    def test_standard_tier_default_rate(self):
        result = self.calc.calculate(100000, 'standard')
        assert result['rate'] == 12.0

    def test_premium_tier_default_rate(self):
        result = self.calc.calculate(100000, 'premium')
        assert result['rate'] == 10.0

    def test_enterprise_tier_default_rate(self):
        result = self.calc.calculate(100000, 'enterprise')
        assert result['rate'] == 8.0

    def test_category_override(self):
        result = self.calc.calculate(100000, 'basic', 'book')
        assert result['rate'] == 7.0

    def test_custom_rule_overrides(self):
        from src.vendor_marketplace.commission import CommissionRule
        rule = CommissionRule(vendor_tier='basic', category='electronics', rate=5.0)
        self.calc.add_rule(rule)
        result = self.calc.calculate(100000, 'basic', 'electronics')
        assert result['rate'] == 5.0

    def test_remove_rule(self):
        from src.vendor_marketplace.commission import CommissionRule
        rule = CommissionRule(vendor_tier='basic', rate=5.0)
        self.calc.add_rule(rule)
        removed = self.calc.remove_rule(rule.rule_id)
        assert removed is True

    def test_remove_nonexistent_rule(self):
        removed = self.calc.remove_rule('nonexistent')
        assert removed is False

    def test_list_rules(self):
        from src.vendor_marketplace.commission import CommissionRule
        rule = CommissionRule(vendor_tier='basic', rate=10.0)
        self.calc.add_rule(rule)
        rules = self.calc.list_rules()
        assert len(rules) >= 1

    def test_bulk_calculate(self):
        orders = [
            {'order_id': 'O1', 'amount': 10000, 'vendor_tier': 'basic', 'category': ''},
            {'order_id': 'O2', 'amount': 20000, 'vendor_tier': 'standard', 'category': ''},
        ]
        results = self.calc.bulk_calculate(orders)
        assert len(results) == 2
        assert results[0]['order_id'] == 'O1'
        assert results[1]['order_id'] == 'O2'

    def test_net_amount_calculation(self):
        result = self.calc.calculate(50000, 'basic')
        assert result['commission'] + result['net_amount'] == result['amount']


# ─── Settlement ───────────────────────────────────────────────────────────

class TestSettlement:
    def test_to_dict(self):
        from src.vendor_marketplace.settlement import Settlement, SettlementStatus
        s = Settlement(vendor_id='V001', gross_sales=100000, commission=15000, net_amount=85000)
        d = s.to_dict()
        assert d['vendor_id'] == 'V001'
        assert d['gross_sales'] == 100000
        assert d['status'] == 'pending'


# ─── SettlementManager ────────────────────────────────────────────────────

class TestSettlementManager:
    def setup_method(self):
        from src.vendor_marketplace.settlement import SettlementManager
        self.mgr = SettlementManager()

    def _orders(self):
        return [
            {'order_id': 'O1', 'amount': 50000, 'category': 'electronics', 'is_return': False},
            {'order_id': 'O2', 'amount': 30000, 'category': 'fashion', 'is_return': False},
            {'order_id': 'O3', 'amount': 10000, 'category': '', 'is_return': True},
        ]

    def test_generate_settlement(self):
        settlement = self.mgr.generate_settlement('V001', self._orders(), vendor_tier='basic')
        assert settlement.vendor_id == 'V001'
        assert settlement.gross_sales == 80000.0  # 50000 + 30000
        assert settlement.returns_deduction == 10000.0
        assert settlement.order_count == 2

    def test_settlement_net_amount(self):
        settlement = self.mgr.generate_settlement('V001', self._orders(), vendor_tier='basic')
        expected_net = settlement.gross_sales - settlement.commission - settlement.returns_deduction
        assert abs(settlement.net_amount - expected_net) < 0.01

    def test_process_settlement(self):
        from src.vendor_marketplace.settlement import SettlementStatus
        s = self.mgr.generate_settlement('V001', self._orders())
        processed = self.mgr.process_settlement(s.settlement_id)
        assert processed.status == SettlementStatus.processing

    def test_complete_settlement(self):
        from src.vendor_marketplace.settlement import SettlementStatus
        s = self.mgr.generate_settlement('V001', self._orders())
        self.mgr.process_settlement(s.settlement_id)
        completed = self.mgr.complete_settlement(s.settlement_id)
        assert completed.status == SettlementStatus.completed
        assert completed.completed_at is not None

    def test_fail_settlement(self):
        from src.vendor_marketplace.settlement import SettlementStatus
        s = self.mgr.generate_settlement('V001', self._orders())
        failed = self.mgr.fail_settlement(s.settlement_id, '시스템 오류')
        assert failed.status == SettlementStatus.failed
        assert failed.error_message == '시스템 오류'

    def test_list_vendor_settlements(self):
        self.mgr.generate_settlement('V001', self._orders())
        self.mgr.generate_settlement('V001', self._orders())
        settlements = self.mgr.list_vendor_settlements('V001')
        assert len(settlements) == 2

    def test_list_by_status(self):
        s = self.mgr.generate_settlement('V001', self._orders())
        self.mgr.process_settlement(s.settlement_id)
        processing = self.mgr.list_vendor_settlements('V001', status='processing')
        assert all(x.status.value == 'processing' for x in processing)

    def test_get_settlement(self):
        s = self.mgr.generate_settlement('V001', self._orders())
        found = self.mgr.get_settlement(s.settlement_id)
        assert found is not None
        assert found.settlement_id == s.settlement_id

    def test_generate_report(self):
        self.mgr.generate_settlement('V001', self._orders())
        report = self.mgr.generate_report('V001', 'Q1 2024')
        assert report['vendor_id'] == 'V001'
        assert report['settlement_count'] == 1
        assert 'total_gross_sales' in report

    def test_process_invalid_status_raises(self):
        s = self.mgr.generate_settlement('V001', self._orders())
        self.mgr.process_settlement(s.settlement_id)
        with pytest.raises(ValueError):
            self.mgr.process_settlement(s.settlement_id)  # already processing

    def test_settlement_not_found_raises(self):
        with pytest.raises(KeyError):
            self.mgr.process_settlement('nonexistent')


# ─── SettlementReport ─────────────────────────────────────────────────────

class TestSettlementReport:
    def test_generate_empty(self):
        from src.vendor_marketplace.settlement import SettlementReport
        report = SettlementReport()
        result = report.generate('V001', [], 'Q1')
        assert result['total_gross_sales'] == 0
        assert result['settlement_count'] == 0

    def test_generate_with_data(self):
        from src.vendor_marketplace.settlement import Settlement, SettlementReport
        settlements = [
            Settlement(vendor_id='V001', gross_sales=100000, commission=15000, returns_deduction=5000, net_amount=80000, order_count=5),
            Settlement(vendor_id='V001', gross_sales=200000, commission=30000, returns_deduction=0, net_amount=170000, order_count=10),
        ]
        report = SettlementReport()
        result = report.generate('V001', settlements, 'Q1')
        assert result['total_gross_sales'] == 300000
        assert result['total_net_amount'] == 250000
        assert result['total_order_count'] == 15


# ─── PayoutService ────────────────────────────────────────────────────────

class TestPayoutService:
    def setup_method(self):
        from src.vendor_marketplace.settlement import PayoutService
        self.svc = PayoutService()

    def test_register_bank_account(self):
        info = self.svc.register_bank_account('V001', '국민은행', '123-456-789012', '홍길동')
        assert info['bank_name'] == '국민은행'
        assert info['vendor_id'] == 'V001'

    def test_get_bank_account(self):
        self.svc.register_bank_account('V001', '신한은행', '111-222-333', '김철수')
        account = self.svc.get_bank_account('V001')
        assert account is not None
        assert account['bank_name'] == '신한은행'

    def test_request_payout_success(self):
        from src.vendor_marketplace.settlement import Settlement, SettlementStatus
        self.svc.register_bank_account('V001', '우리은행', '000-111-222', '이영희')
        s = Settlement(
            vendor_id='V001', gross_sales=100000, commission=15000,
            returns_deduction=0, net_amount=85000,
            status=SettlementStatus.completed,
        )
        payout = self.svc.request_payout(s)
        assert payout.status == 'completed'
        assert payout.amount == 85000
        assert payout.tx_id.startswith('TX-')

    def test_request_payout_no_account_raises(self):
        from src.vendor_marketplace.settlement import Settlement, SettlementStatus
        s = Settlement(
            vendor_id='V999', net_amount=1000,
            status=SettlementStatus.completed,
        )
        with pytest.raises(ValueError):
            self.svc.request_payout(s)

    def test_request_payout_not_completed_raises(self):
        from src.vendor_marketplace.settlement import Settlement, SettlementStatus
        self.svc.register_bank_account('V001', '하나은행', '111', '홍')
        s = Settlement(vendor_id='V001', net_amount=1000, status=SettlementStatus.pending)
        with pytest.raises(ValueError):
            self.svc.request_payout(s)

    def test_get_payout_history(self):
        from src.vendor_marketplace.settlement import Settlement, SettlementStatus
        self.svc.register_bank_account('V001', '기업은행', '999', '박')
        s = Settlement(
            vendor_id='V001', net_amount=50000,
            status=SettlementStatus.completed,
        )
        self.svc.request_payout(s)
        history = self.svc.get_payout_history('V001')
        assert len(history) >= 1


# ─── VendorDashboard ──────────────────────────────────────────────────────

class TestVendorDashboard:
    def setup_method(self):
        from src.vendor_marketplace.vendor_analytics import VendorDashboard
        self.dashboard = VendorDashboard()

    def test_get_summary_empty(self):
        summary = self.dashboard.get_summary('V001', [], [], [])
        assert summary['vendor_id'] == 'V001'
        assert summary['sales']['total'] == 0
        assert summary['orders']['total'] == 0

    def test_get_summary_with_orders(self):
        now = datetime.now(timezone.utc).isoformat()
        orders = [
            {'amount': 50000, 'is_return': False, 'status': 'pending', 'created_at': now},
            {'amount': 30000, 'is_return': True, 'status': 'completed', 'created_at': now},
        ]
        summary = self.dashboard.get_summary('V001', orders, [], [])
        assert summary['sales']['total'] == 50000
        assert summary['orders']['total'] == 2

    def test_get_summary_with_settlements(self):
        settlements = [{'status': 'pending', 'net_amount': 85000}]
        summary = self.dashboard.get_summary('V001', [], settlements, [])
        assert summary['settlement']['expected_payout'] == 85000


# ─── VendorAnalytics ──────────────────────────────────────────────────────

class TestVendorAnalytics:
    def setup_method(self):
        from src.vendor_marketplace.vendor_analytics import VendorAnalytics
        self.analytics = VendorAnalytics()

    def _orders(self):
        now = datetime.now(timezone.utc)
        return [
            {'amount': 10000, 'product_id': 'P1', 'is_return': False, 'created_at': now.isoformat()},
            {'amount': 20000, 'product_id': 'P2', 'is_return': False, 'created_at': now.isoformat()},
            {'amount': 5000, 'product_id': 'P1', 'is_return': True, 'created_at': now.isoformat()},
        ]

    def test_daily_trend_returns_list(self):
        trend = self.analytics.daily_trend(self._orders(), days=7)
        assert isinstance(trend, list)
        assert len(trend) == 7

    def test_product_ranking(self):
        ranking = self.analytics.product_ranking(self._orders())
        assert ranking[0]['rank'] == 1
        assert len(ranking) >= 2

    def test_return_rate(self):
        rate = self.analytics.return_rate(self._orders())
        assert abs(rate - 33.33) < 0.01

    def test_return_rate_empty(self):
        assert self.analytics.return_rate([]) == 0.0

    def test_average_rating(self):
        reviews = [{'rating': 4}, {'rating': 5}, {'rating': 3}]
        avg = self.analytics.average_rating(reviews)
        assert avg == pytest.approx(4.0)

    def test_average_rating_empty(self):
        assert self.analytics.average_rating([]) == 0.0


# ─── VendorScoring ────────────────────────────────────────────────────────

class TestVendorScoring:
    def setup_method(self):
        from src.vendor_marketplace.vendor_analytics import VendorScoring
        self.scoring = VendorScoring()

    def test_perfect_score(self):
        result = self.scoring.calculate(
            delivery_delay_rate=0.0,
            return_rate=0.0,
            avg_rating=5.0,
            cs_response_hours=1.0,
        )
        assert result['total_score'] == 100.0
        assert result['grade'] == 'S'

    def test_poor_score(self):
        result = self.scoring.calculate(
            delivery_delay_rate=0.5,
            return_rate=0.5,
            avg_rating=1.0,
            cs_response_hours=48.0,
        )
        assert result['total_score'] < 40

    def test_grade_assignment(self):
        assert self.scoring._grade(92) == 'S'
        assert self.scoring._grade(82) == 'A'
        assert self.scoring._grade(72) == 'B'
        assert self.scoring._grade(62) == 'C'
        assert self.scoring._grade(50) == 'D'

    def test_score_keys(self):
        result = self.scoring.calculate()
        assert 'total_score' in result
        assert 'delivery_score' in result
        assert 'return_score' in result
        assert 'rating_score' in result
        assert 'cs_score' in result
        assert 'grade' in result


# ─── VendorRanking ────────────────────────────────────────────────────────

class TestVendorRanking:
    def setup_method(self):
        from src.vendor_marketplace.vendor_analytics import VendorRanking
        self.ranking = VendorRanking()

    def _sample_stats(self):
        return [
            {'vendor_id': 'V1', 'name': '샵A', 'total_sales': 1000000, 'total_score': 90.0, 'avg_rating': 4.8},
            {'vendor_id': 'V2', 'name': '샵B', 'total_sales': 500000, 'total_score': 75.0, 'avg_rating': 4.2},
            {'vendor_id': 'V3', 'name': '샵C', 'total_sales': 200000, 'total_score': 60.0, 'avg_rating': 3.5},
        ]

    def test_rank_by_sales(self):
        ranked = self.ranking.rank_by_sales(self._sample_stats())
        assert ranked[0]['vendor_id'] == 'V1'
        assert ranked[0]['sales_rank'] == 1

    def test_rank_by_score(self):
        ranked = self.ranking.rank_by_score(self._sample_stats())
        assert ranked[0]['vendor_id'] == 'V1'
        assert ranked[0]['score_rank'] == 1

    def test_get_badges(self):
        vendor = {'total_sales': 95.0, 'avg_rating': 4.9, 'total_score': 92.0}
        badges = self.ranking.get_badges(vendor)
        assert len(badges) > 0

    def test_get_badges_none(self):
        vendor = {'total_sales': 10, 'avg_rating': 2.0, 'total_score': 30.0}
        badges = self.ranking.get_badges(vendor)
        assert badges == []

    def test_build_leaderboard(self):
        leaderboard = self.ranking.build_leaderboard(self._sample_stats())
        assert len(leaderboard) == 3
        assert 'badges' in leaderboard[0]
        assert 'score_rank' in leaderboard[0]


# ─── VendorAdminManager ───────────────────────────────────────────────────

class TestVendorAdminManager:
    def setup_method(self):
        from src.vendor_marketplace.vendor_manager import VendorOnboardingManager
        from src.vendor_marketplace.vendor_admin import VendorAdminManager
        self.onboarding = VendorOnboardingManager()
        self.admin = VendorAdminManager(onboarding_manager=self.onboarding)

    def _add_vendor(self, name='샵'):
        return self.onboarding.apply(name=name, email='a@b.com', phone='010', business_number='123-45-67890')

    def test_list_vendors_empty(self):
        vendors = self.admin.list_vendors()
        assert isinstance(vendors, list)

    def test_list_vendors_with_keyword(self):
        self._add_vendor('검색테스트')
        vendors = self.admin.list_vendors(keyword='검색')
        assert len(vendors) >= 1

    def test_get_review_queue(self):
        v = self._add_vendor()
        self.onboarding.submit_for_review(v.vendor_id)
        queue = self.admin.get_review_queue()
        assert len(queue) >= 1

    def test_bulk_approve(self):
        from src.vendor_marketplace.vendor_models import VendorStatus
        v1 = self._add_vendor('샵1')
        v2 = self._add_vendor('샵2')
        self.onboarding.submit_for_review(v1.vendor_id)
        self.onboarding.submit_for_review(v2.vendor_id)
        result = self.admin.bulk_approve([v1.vendor_id, v2.vendor_id])
        assert len(result['approved']) == 2
        assert len(result['failed']) == 0

    def test_bulk_reject(self):
        v1 = self._add_vendor('샵3')
        self.onboarding.submit_for_review(v1.vendor_id)
        result = self.admin.bulk_reject([v1.vendor_id], '서류 미비')
        assert len(result['rejected']) == 1

    def test_suspend_vendor(self):
        from src.vendor_marketplace.vendor_models import VendorStatus
        v = self._add_vendor()
        self.onboarding.submit_for_review(v.vendor_id)
        self.onboarding.approve(v.vendor_id)
        self.onboarding.activate(v.vendor_id)
        result = self.admin.suspend_vendor(v.vendor_id, '규정 위반')
        assert result['status'] == VendorStatus.suspended.value

    def test_unsuspend_vendor(self):
        from src.vendor_marketplace.vendor_models import VendorStatus
        v = self._add_vendor()
        self.onboarding.submit_for_review(v.vendor_id)
        self.onboarding.approve(v.vendor_id)
        self.onboarding.activate(v.vendor_id)
        self.onboarding.suspend(v.vendor_id)
        result = self.admin.unsuspend_vendor(v.vendor_id)
        assert result['status'] == VendorStatus.active.value


# ─── PlatformFeeManager ───────────────────────────────────────────────────

class TestPlatformFeeManager:
    def setup_method(self):
        from src.vendor_marketplace.vendor_admin import PlatformFeeManager
        self.fee_mgr = PlatformFeeManager()

    def test_create_rule(self):
        rule = self.fee_mgr.create_rule(vendor_tier='basic', rate=13.0, category='electronics')
        assert rule.vendor_tier == 'basic'
        assert rule.rate == 13.0

    def test_list_rules(self):
        self.fee_mgr.create_rule(vendor_tier='standard', rate=11.0)
        rules = self.fee_mgr.list_rules()
        assert len(rules) >= 1

    def test_deactivate_rule(self):
        rule = self.fee_mgr.create_rule(vendor_tier='premium', rate=9.0)
        result = self.fee_mgr.deactivate_rule(rule.rule_id)
        assert result is True
        rules = self.fee_mgr.list_rules(active_only=True)
        assert all(r['rule_id'] != rule.rule_id for r in rules)


# ─── VendorComplianceChecker ──────────────────────────────────────────────

class TestVendorComplianceChecker:
    def setup_method(self):
        from src.vendor_marketplace.vendor_admin import VendorComplianceChecker
        self.checker = VendorComplianceChecker()

    def test_all_pass(self):
        result = self.checker.check('V001', {
            'return_rate': 0.05,
            'response_rate': 0.95,
            'delivery_delay_rate': 0.05,
            'total_score': 85.0,
        })
        assert result['passed'] is True
        assert result['warnings'] == []

    def test_high_return_rate_warning(self):
        result = self.checker.check('V001', {
            'return_rate': 0.25,
            'response_rate': 0.90,
            'delivery_delay_rate': 0.05,
            'total_score': 80.0,
        })
        assert result['passed'] is False
        assert any('반품률' in w for w in result['warnings'])

    def test_low_response_rate_warning(self):
        result = self.checker.check('V001', {
            'return_rate': 0.05,
            'response_rate': 0.50,
            'delivery_delay_rate': 0.05,
            'total_score': 80.0,
        })
        assert result['passed'] is False
        assert any('응답률' in w for w in result['warnings'])

    def test_auto_suspend_on_low_score(self):
        from src.vendor_marketplace.vendor_manager import VendorOnboardingManager
        from src.vendor_marketplace.vendor_admin import VendorComplianceChecker
        onboarding = VendorOnboardingManager()
        v = onboarding.apply('테스트샵', 'a@b.com', '010', '123-45-67890')
        onboarding.submit_for_review(v.vendor_id)
        onboarding.approve(v.vendor_id)
        onboarding.activate(v.vendor_id)
        checker = VendorComplianceChecker(onboarding_manager=onboarding)
        result = checker.check(v.vendor_id, {
            'return_rate': 0.05,
            'response_rate': 0.90,
            'delivery_delay_rate': 0.05,
            'total_score': 30.0,
        })
        assert result['auto_suspended'] is True


# ─── VendorNotificationService ────────────────────────────────────────────

class TestVendorNotificationService:
    def setup_method(self):
        from src.vendor_marketplace.vendor_notifications import VendorNotificationService
        self.svc = VendorNotificationService()

    def test_notify_approval(self):
        rec = self.svc.notify_approval('V001', '베스트샵')
        assert rec['event'] == 'onboarding_approved'
        assert rec['vendor_id'] == 'V001'

    def test_notify_rejection(self):
        rec = self.svc.notify_rejection('V001', '베스트샵', '서류 미비')
        assert rec['event'] == 'onboarding_rejected'

    def test_notify_settlement_completed(self):
        rec = self.svc.notify_settlement_completed('V001', '베스트샵', 85000)
        assert rec['event'] == 'settlement_completed'
        assert '85,000' in rec['message']

    def test_notify_settlement_failed(self):
        rec = self.svc.notify_settlement_failed('V001', '베스트샵', '시스템 오류')
        assert rec['event'] == 'settlement_failed'

    def test_notify_product_approved(self):
        rec = self.svc.notify_product_approved('V001', '베스트샵', '노트북')
        assert rec['event'] == 'product_approved'

    def test_notify_product_rejected(self):
        rec = self.svc.notify_product_rejected('V001', '베스트샵', '불법상품', '금지어')
        assert rec['event'] == 'product_rejected'

    def test_notify_low_stock(self):
        rec = self.svc.notify_low_stock('V001', '베스트샵', '마우스', 3)
        assert rec['event'] == 'low_stock'
        assert '3' in rec['message']

    def test_notify_suspension(self):
        rec = self.svc.notify_suspension('V001', '베스트샵', '규정 위반')
        assert rec['event'] == 'suspension'

    def test_notify_policy_change(self):
        rec = self.svc.notify_policy_change('V001', '베스트샵', '수수료율 변경')
        assert rec['event'] == 'policy_change'

    def test_notify_violation_warning(self):
        rec = self.svc.notify_violation_warning('V001', '베스트샵', '배송 지연율 초과')
        assert rec['event'] == 'violation_warning'

    def test_get_history_by_vendor(self):
        self.svc.notify_approval('V001', '샵A')
        self.svc.notify_approval('V002', '샵B')
        history = self.svc.get_history(vendor_id='V001')
        assert all(h['vendor_id'] == 'V001' for h in history)

    def test_get_history_by_event(self):
        self.svc.notify_approval('V001', '샵A')
        self.svc.notify_settlement_completed('V001', '샵A', 10000)
        history = self.svc.get_history(event='settlement_completed')
        assert all(h['event'] == 'settlement_completed' for h in history)


# ─── API Blueprint ────────────────────────────────────────────────────────

class TestVendorAPI:
    def setup_method(self):
        from flask import Flask
        from src.api.vendor_api import vendor_bp, _get_services
        # Reset globals by reimporting
        import src.api.vendor_api as va
        va._onboarding = None
        va._profile_mgr = None
        va._product_mgr = None
        va._settlement_mgr = None
        va._payout_svc = None
        va._commission_calc = None
        va._fee_mgr = None
        va._admin_mgr = None
        va._compliance = None
        va._notification_svc = None
        va._dashboard = None
        va._analytics = None
        va._scoring = None
        va._ranking = None

        app = Flask(__name__)
        app.register_blueprint(vendor_bp)
        self.client = app.test_client()
        self.app = app

    def test_apply_vendor_success(self):
        resp = self.client.post('/api/v1/vendors/apply', json={
            'name': '테스트샵',
            'email': 'test@test.com',
            'phone': '010-1234-5678',
            'business_number': '123-45-67890',
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['name'] == '테스트샵'

    def test_apply_vendor_missing_fields(self):
        resp = self.client.post('/api/v1/vendors/apply', json={'name': '샵'})
        assert resp.status_code == 400

    def test_apply_vendor_invalid_biz_num(self):
        resp = self.client.post('/api/v1/vendors/apply', json={
            'name': '샵', 'email': 'a@b.com', 'phone': '010',
            'business_number': 'INVALID',
        })
        assert resp.status_code == 422

    def test_list_vendors(self):
        resp = self.client.get('/api/v1/vendors/')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'vendors' in data

    def test_get_vendor_not_found(self):
        resp = self.client.get('/api/v1/vendors/NONEXISTENT')
        assert resp.status_code == 404

    def test_get_vendor_success(self):
        r = self.client.post('/api/v1/vendors/apply', json={
            'name': '조회테스트', 'email': 'a@b.com', 'phone': '010',
            'business_number': '123-45-67890',
        })
        vendor_id = r.get_json()['vendor_id']
        resp = self.client.get(f'/api/v1/vendors/{vendor_id}')
        assert resp.status_code == 200

    def test_approve_vendor_invalid_transition(self):
        r = self.client.post('/api/v1/vendors/apply', json={
            'name': '승인테스트', 'email': 'a@b.com', 'phone': '010',
            'business_number': '123-45-67890',
        })
        vendor_id = r.get_json()['vendor_id']
        # pending → approved 불가
        resp = self.client.post(f'/api/v1/vendors/{vendor_id}/approve')
        assert resp.status_code == 422

    def test_list_commission_rules(self):
        resp = self.client.get('/api/v1/vendors/commission-rules')
        assert resp.status_code == 200

    def test_create_commission_rule(self):
        resp = self.client.post('/api/v1/vendors/commission-rules', json={
            'vendor_tier': 'basic',
            'rate': 13.0,
            'category': 'fashion',
        })
        assert resp.status_code == 201

    def test_add_product_vendor_not_found(self):
        resp = self.client.post('/api/v1/vendors/NONEXISTENT/products', json={
            'name': '상품', 'price': 10000,
        })
        assert resp.status_code == 404

    def test_list_vendor_settlements(self):
        r = self.client.post('/api/v1/vendors/apply', json={
            'name': '정산테스트', 'email': 'a@b.com', 'phone': '010',
            'business_number': '123-45-67890',
        })
        vendor_id = r.get_json()['vendor_id']
        resp = self.client.get(f'/api/v1/vendors/{vendor_id}/settlements')
        assert resp.status_code == 200
        assert 'settlements' in resp.get_json()

    def test_generate_settlement(self):
        r = self.client.post('/api/v1/vendors/apply', json={
            'name': '정산생성', 'email': 'a@b.com', 'phone': '010',
            'business_number': '123-45-67890',
        })
        vendor_id = r.get_json()['vendor_id']
        resp = self.client.post(f'/api/v1/vendors/{vendor_id}/settlements/generate', json={
            'orders': [
                {'order_id': 'O1', 'amount': 50000, 'category': 'electronics', 'is_return': False}
            ],
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['vendor_id'] == vendor_id

    def test_vendor_dashboard(self):
        r = self.client.post('/api/v1/vendors/apply', json={
            'name': '대시보드테스트', 'email': 'a@b.com', 'phone': '010',
            'business_number': '123-45-67890',
        })
        vendor_id = r.get_json()['vendor_id']
        resp = self.client.get(f'/api/v1/vendors/{vendor_id}/dashboard')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'sales' in data

    def test_vendor_analytics(self):
        r = self.client.post('/api/v1/vendors/apply', json={
            'name': '분석테스트', 'email': 'a@b.com', 'phone': '010',
            'business_number': '123-45-67890',
        })
        vendor_id = r.get_json()['vendor_id']
        resp = self.client.get(f'/api/v1/vendors/{vendor_id}/analytics')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'daily_trend' in data
        assert 'score' in data

    def test_vendor_ranking(self):
        resp = self.client.get('/api/v1/vendors/ranking')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'ranking' in data


# ─── Bot Commands ─────────────────────────────────────────────────────────

class TestBotCommands:
    def test_cmd_vendors_empty(self):
        from src.bot.commands import cmd_vendors
        result = cmd_vendors()
        assert isinstance(result, str)

    def test_cmd_vendor_approve_no_id(self):
        from src.bot.commands import cmd_vendor_approve
        result = cmd_vendor_approve()
        assert '사용법' in result

    def test_cmd_vendor_approve_error(self):
        from src.bot.commands import cmd_vendor_approve
        result = cmd_vendor_approve('NONEXISTENT')
        assert isinstance(result, str)

    def test_cmd_vendor_score_no_id(self):
        from src.bot.commands import cmd_vendor_score
        result = cmd_vendor_score()
        assert '사용법' in result

    def test_cmd_vendor_score_with_id(self):
        from src.bot.commands import cmd_vendor_score
        result = cmd_vendor_score('V001')
        assert '종합 점수' in result

    def test_cmd_vendor_settlement_no_id(self):
        from src.bot.commands import cmd_vendor_settlement
        result = cmd_vendor_settlement()
        assert '사용법' in result

    def test_cmd_vendor_settlement_with_id(self):
        from src.bot.commands import cmd_vendor_settlement
        result = cmd_vendor_settlement('V999')
        assert isinstance(result, str)

    def test_cmd_vendor_ranking(self):
        from src.bot.commands import cmd_vendor_ranking
        result = cmd_vendor_ranking()
        assert '랭킹' in result


# ─── Integration: 전체 온보딩 플로우 ─────────────────────────────────────

class TestFullOnboardingFlow:
    def test_full_flow_apply_to_active(self):
        from src.vendor_marketplace.vendor_manager import VendorOnboardingManager
        from src.vendor_marketplace.vendor_models import VendorStatus
        from src.vendor_marketplace.vendor_notifications import VendorNotificationService

        mgr = VendorOnboardingManager()
        notif = VendorNotificationService()

        # 1. 신청
        vendor = mgr.apply(
            name='신규샵', email='new@shop.com', phone='010-9999-0000',
            business_number='987-65-43210',
        )
        assert vendor.status == VendorStatus.pending

        # 2. 약관 동의
        mgr.record_agreement(vendor.vendor_id, required=True, optional=True)
        assert mgr.has_valid_agreement(vendor.vendor_id)

        # 3. 서류 업로드
        doc = mgr.upload_document(vendor.vendor_id, 'business_license', 'license.pdf', 2048)
        assert doc.status == 'pending'

        # 4. 서류 검증
        mgr.verify_document(vendor.vendor_id, doc.doc_id)

        # 5. 심사 제출
        mgr.submit_for_review(vendor.vendor_id)
        assert vendor.status == VendorStatus.under_review

        # 6. 승인
        mgr.approve(vendor.vendor_id)
        assert vendor.status == VendorStatus.approved

        # 7. 알림
        rec = notif.notify_approval(vendor.vendor_id, vendor.name)
        assert rec['event'] == 'onboarding_approved'

        # 8. 활성화
        mgr.activate(vendor.vendor_id)
        assert vendor.status == VendorStatus.active


class TestFullSettlementFlow:
    def test_full_settlement_flow(self):
        from src.vendor_marketplace.commission import CommissionCalculator
        from src.vendor_marketplace.settlement import SettlementManager, PayoutService, SettlementStatus
        from src.vendor_marketplace.vendor_notifications import VendorNotificationService

        calc = CommissionCalculator()
        mgr = SettlementManager(calculator=calc)
        payout_svc = PayoutService()
        notif = VendorNotificationService()

        # 계좌 등록
        payout_svc.register_bank_account('V001', '국민은행', '123-456-789', '홍길동')

        # 정산 생성
        orders = [
            {'order_id': 'O1', 'amount': 100000, 'category': 'electronics', 'is_return': False},
            {'order_id': 'O2', 'amount': 50000, 'category': 'fashion', 'is_return': False},
            {'order_id': 'O3', 'amount': 10000, 'category': '', 'is_return': True},
        ]
        settlement = mgr.generate_settlement('V001', orders, vendor_tier='basic')
        assert settlement.gross_sales == 150000
        assert settlement.returns_deduction == 10000
        assert settlement.status == SettlementStatus.pending

        # 처리
        mgr.process_settlement(settlement.settlement_id)
        mgr.complete_settlement(settlement.settlement_id)
        assert settlement.status == SettlementStatus.completed

        # 지급
        payout = payout_svc.request_payout(settlement)
        assert payout.status == 'completed'

        # 알림
        notif.notify_settlement_completed('V001', '테스트샵', settlement.net_amount)
        history = notif.get_history(vendor_id='V001')
        assert len(history) == 1
