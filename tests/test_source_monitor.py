"""tests/test_source_monitor.py — Phase 108: 소싱처 실시간 모니터링 테스트."""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest


# ─── SourceType ───────────────────────────────────────────────────────────────

class TestSourceType:
    def test_values(self):
        from src.source_monitor.engine import SourceType
        assert SourceType.amazon_us == 'amazon_us'
        assert SourceType.amazon_jp == 'amazon_jp'
        assert SourceType.taobao == 'taobao'
        assert SourceType.alibaba_1688 == 'alibaba_1688'
        assert SourceType.coupang == 'coupang'
        assert SourceType.naver == 'naver'
        assert SourceType.custom == 'custom'

    def test_is_str(self):
        from src.source_monitor.engine import SourceType
        assert isinstance(SourceType.amazon_us, str)


# ─── SourceStatus ─────────────────────────────────────────────────────────────

class TestSourceStatus:
    def test_values(self):
        from src.source_monitor.engine import SourceStatus
        assert SourceStatus.active == 'active'
        assert SourceStatus.price_changed == 'price_changed'
        assert SourceStatus.out_of_stock == 'out_of_stock'
        assert SourceStatus.listing_removed == 'listing_removed'
        assert SourceStatus.seller_inactive == 'seller_inactive'
        assert SourceStatus.restricted == 'restricted'
        assert SourceStatus.unknown == 'unknown'


# ─── StockStatus ──────────────────────────────────────────────────────────────

class TestStockStatus:
    def test_values(self):
        from src.source_monitor.engine import StockStatus
        assert StockStatus.in_stock == 'in_stock'
        assert StockStatus.low_stock == 'low_stock'
        assert StockStatus.out_of_stock == 'out_of_stock'
        assert StockStatus.preorder == 'preorder'
        assert StockStatus.discontinued == 'discontinued'


# ─── SourceProduct ────────────────────────────────────────────────────────────

class TestSourceProduct:
    def _make(self, **kwargs):
        from src.source_monitor.engine import SourceProduct, SourceType
        defaults = dict(
            source_product_id='sp-001',
            source_type=SourceType.coupang,
            source_url='https://example.com/product/1',
            seller_id='seller-1',
            seller_name='테스트 판매자',
            my_product_id='my-001',
            title='테스트 상품',
            current_price=10000.0,
            original_price=12000.0,
        )
        defaults.update(kwargs)
        return SourceProduct(**defaults)

    def test_creation(self):
        product = self._make()
        assert product.source_product_id == 'sp-001'
        assert product.title == '테스트 상품'
        assert product.is_alive is True
        assert product.consecutive_failures == 0

    def test_registered_at_auto(self):
        product = self._make()
        assert product.registered_at != ''

    def test_to_dict(self):
        product = self._make()
        d = product.to_dict()
        assert d['source_product_id'] == 'sp-001'
        assert d['is_alive'] is True
        assert d['stock_status'] == 'in_stock'

    def test_to_dict_source_type_is_str(self):
        product = self._make()
        d = product.to_dict()
        assert isinstance(d['source_type'], str)


# ─── SourceMonitorEngine ──────────────────────────────────────────────────────

class TestSourceMonitorEngine:
    def _engine(self):
        from src.source_monitor.engine import SourceMonitorEngine
        return SourceMonitorEngine()

    def _product_data(self, **kwargs):
        data = dict(
            source_product_id='sp-test',
            source_type='coupang',
            source_url='https://coupang.com/vp/1',
            seller_id='s1',
            seller_name='판매자',
            my_product_id='my-1',
            title='상품 A',
            current_price=20000.0,
            original_price=25000.0,
        )
        data.update(kwargs)
        return data

    def test_register_product(self):
        engine = self._engine()
        product = engine.register_product(self._product_data())
        assert product.source_product_id == 'sp-test'

    def test_register_auto_id(self):
        engine = self._engine()
        data = self._product_data()
        del data['source_product_id']
        product = engine.register_product(data)
        assert product.source_product_id != ''

    def test_get_product(self):
        engine = self._engine()
        engine.register_product(self._product_data())
        product = engine.get_product('sp-test')
        assert product is not None
        assert product.title == '상품 A'

    def test_get_product_missing(self):
        engine = self._engine()
        assert engine.get_product('missing') is None

    def test_update_product(self):
        engine = self._engine()
        engine.register_product(self._product_data())
        updated = engine.update_product('sp-test', {'title': '수정된 상품'})
        assert updated.title == '수정된 상품'

    def test_update_product_missing(self):
        engine = self._engine()
        result = engine.update_product('missing', {'title': 'x'})
        assert result is None

    def test_delete_product(self):
        engine = self._engine()
        engine.register_product(self._product_data())
        ok = engine.delete_product('sp-test')
        assert ok is True
        assert engine.get_product('sp-test') is None

    def test_delete_product_missing(self):
        engine = self._engine()
        assert engine.delete_product('missing') is False

    def test_list_products(self):
        engine = self._engine()
        engine.register_product(self._product_data())
        products = engine.list_products()
        assert len(products) >= 1

    def test_list_products_filter_status(self):
        engine = self._engine()
        engine.register_product(self._product_data())
        products = engine.list_products(status='active')
        assert all(p.status.value == 'active' for p in products)

    def test_run_check(self):
        engine = self._engine()
        engine.register_product(self._product_data())
        result = engine.run_check('sp-test')
        assert 'check_result' in result
        assert 'events' in result

    def test_run_check_missing(self):
        engine = self._engine()
        result = engine.run_check('missing')
        assert 'error' in result

    def test_get_summary(self):
        engine = self._engine()
        engine.register_product(self._product_data())
        summary = engine.get_summary()
        assert summary['total'] >= 1
        assert 'active' in summary
        assert 'by_source_type' in summary


# ─── CheckResult ─────────────────────────────────────────────────────────────

class TestCheckResult:
    def test_creation(self):
        from src.source_monitor.checkers import CheckResult
        from src.source_monitor.engine import StockStatus
        cr = CheckResult(
            source_product_id='sp-1',
            checked_at='',
            is_alive=True,
            price=10000.0,
            stock_status=StockStatus.in_stock,
            seller_active=True,
            changes_detected=False,
        )
        assert cr.is_alive is True
        assert cr.checked_at != ''

    def test_to_dict(self):
        from src.source_monitor.checkers import CheckResult
        from src.source_monitor.engine import StockStatus
        cr = CheckResult(
            source_product_id='sp-1',
            checked_at='',
            is_alive=True,
            price=10000.0,
            stock_status=StockStatus.in_stock,
            seller_active=True,
            changes_detected=False,
        )
        d = cr.to_dict()
        assert d['source_product_id'] == 'sp-1'
        assert isinstance(d['stock_status'], str)


# ─── SourceChecker implementations ───────────────────────────────────────────

class TestAmazonSourceChecker:
    def _product(self):
        from src.source_monitor.engine import SourceProduct, SourceType
        return SourceProduct(
            source_product_id='amz-1', source_type=SourceType.amazon_us,
            source_url='https://amazon.com/dp/B001',
            seller_id='amz-s1', seller_name='Amazon Seller',
            my_product_id='my-amz-1', title='Amazon Product',
            current_price=5000.0, original_price=5500.0,
        )

    def test_check_returns_result(self):
        from src.source_monitor.checkers import AmazonSourceChecker
        checker = AmazonSourceChecker()
        result = checker.check(self._product())
        assert result.source_product_id == 'amz-1'
        assert result.is_alive is True
        assert result.seller_active is True

    def test_check_raw_data_marketplace(self):
        from src.source_monitor.checkers import AmazonSourceChecker
        checker = AmazonSourceChecker()
        result = checker.check(self._product())
        assert result.raw_data.get('marketplace') == 'amazon'


class TestTaobaoSourceChecker:
    def _product(self):
        from src.source_monitor.engine import SourceProduct, SourceType
        return SourceProduct(
            source_product_id='tb-1', source_type=SourceType.taobao,
            source_url='https://taobao.com/item/1',
            seller_id='tb-s1', seller_name='Taobao Seller',
            my_product_id='my-tb-1', title='Taobao Product',
            current_price=1500.0, original_price=1800.0,
        )

    def test_check(self):
        from src.source_monitor.checkers import TaobaoSourceChecker
        checker = TaobaoSourceChecker()
        result = checker.check(self._product())
        assert result.source_product_id == 'tb-1'
        assert result.raw_data.get('marketplace') == 'taobao'


class TestAlibaba1688SourceChecker:
    def _product(self):
        from src.source_monitor.engine import SourceProduct, SourceType
        return SourceProduct(
            source_product_id='ali-1', source_type=SourceType.alibaba_1688,
            source_url='https://1688.com/offer/1.html',
            seller_id='ali-s1', seller_name='1688 Seller',
            my_product_id='my-ali-1', title='1688 Product',
            current_price=800.0, original_price=1000.0,
        )

    def test_check(self):
        from src.source_monitor.checkers import Alibaba1688SourceChecker
        checker = Alibaba1688SourceChecker()
        result = checker.check(self._product())
        assert result.source_product_id == 'ali-1'
        assert result.raw_data.get('marketplace') == '1688'


class TestCoupangSourceChecker:
    def _product(self):
        from src.source_monitor.engine import SourceProduct, SourceType
        return SourceProduct(
            source_product_id='cp-1', source_type=SourceType.coupang,
            source_url='https://coupang.com/vp/1',
            seller_id='cp-s1', seller_name='Coupang Seller',
            my_product_id='my-cp-1', title='Coupang Product',
            current_price=15000.0, original_price=16000.0,
        )

    def test_check(self):
        from src.source_monitor.checkers import CoupangSourceChecker
        checker = CoupangSourceChecker()
        result = checker.check(self._product())
        assert result.source_product_id == 'cp-1'
        assert result.raw_data.get('marketplace') == 'coupang'


class TestNaverSourceChecker:
    def _product(self):
        from src.source_monitor.engine import SourceProduct, SourceType
        return SourceProduct(
            source_product_id='nv-1', source_type=SourceType.naver,
            source_url='https://smartstore.naver.com/store/product/1',
            seller_id='nv-s1', seller_name='Naver Seller',
            my_product_id='my-nv-1', title='Naver Product',
            current_price=12000.0, original_price=13000.0,
        )

    def test_check(self):
        from src.source_monitor.checkers import NaverSourceChecker
        checker = NaverSourceChecker()
        result = checker.check(self._product())
        assert result.source_product_id == 'nv-1'
        assert result.raw_data.get('marketplace') == 'naver'


class TestGetChecker:
    def test_amazon_us(self):
        from src.source_monitor.checkers import get_checker, AmazonSourceChecker
        from src.source_monitor.engine import SourceType
        checker = get_checker(SourceType.amazon_us)
        assert isinstance(checker, AmazonSourceChecker)

    def test_amazon_jp(self):
        from src.source_monitor.checkers import get_checker, AmazonSourceChecker
        from src.source_monitor.engine import SourceType
        checker = get_checker(SourceType.amazon_jp)
        assert isinstance(checker, AmazonSourceChecker)

    def test_taobao(self):
        from src.source_monitor.checkers import get_checker, TaobaoSourceChecker
        from src.source_monitor.engine import SourceType
        checker = get_checker(SourceType.taobao)
        assert isinstance(checker, TaobaoSourceChecker)

    def test_1688(self):
        from src.source_monitor.checkers import get_checker, Alibaba1688SourceChecker
        from src.source_monitor.engine import SourceType
        checker = get_checker(SourceType.alibaba_1688)
        assert isinstance(checker, Alibaba1688SourceChecker)

    def test_coupang(self):
        from src.source_monitor.checkers import get_checker, CoupangSourceChecker
        from src.source_monitor.engine import SourceType
        checker = get_checker(SourceType.coupang)
        assert isinstance(checker, CoupangSourceChecker)

    def test_naver(self):
        from src.source_monitor.checkers import get_checker, NaverSourceChecker
        from src.source_monitor.engine import SourceType
        checker = get_checker(SourceType.naver)
        assert isinstance(checker, NaverSourceChecker)

    def test_custom(self):
        from src.source_monitor.checkers import get_checker, CustomSourceChecker
        from src.source_monitor.engine import SourceType
        checker = get_checker(SourceType.custom)
        assert isinstance(checker, CustomSourceChecker)


# ─── ChangeType & Severity ───────────────────────────────────────────────────

class TestChangeType:
    def test_values(self):
        from src.source_monitor.change_detector import ChangeType
        assert ChangeType.listing_removed == 'listing_removed'
        assert ChangeType.price_increase == 'price_increase'
        assert ChangeType.price_decrease == 'price_decrease'
        assert ChangeType.out_of_stock == 'out_of_stock'
        assert ChangeType.back_in_stock == 'back_in_stock'
        assert ChangeType.seller_deactivated == 'seller_deactivated'


class TestSeverity:
    def test_values(self):
        from src.source_monitor.change_detector import Severity
        assert Severity.critical == 'critical'
        assert Severity.high == 'high'
        assert Severity.medium == 'medium'
        assert Severity.low == 'low'


# ─── ChangeEvent ─────────────────────────────────────────────────────────────

class TestChangeEvent:
    def test_creation(self):
        from src.source_monitor.change_detector import ChangeEvent, ChangeType, Severity
        event = ChangeEvent(
            event_id='ev-1',
            source_product_id='sp-1',
            change_type=ChangeType.listing_removed,
            old_value='alive',
            new_value='removed',
            severity=Severity.critical,
        )
        assert event.event_id == 'ev-1'
        assert event.detected_at != ''

    def test_to_dict(self):
        from src.source_monitor.change_detector import ChangeEvent, ChangeType, Severity
        event = ChangeEvent(
            event_id='ev-2',
            source_product_id='sp-2',
            change_type=ChangeType.price_increase,
            old_value='10000',
            new_value='13000',
            severity=Severity.high,
        )
        d = event.to_dict()
        assert d['change_type'] == 'price_increase'
        assert d['severity'] == 'high'
        assert isinstance(d['change_type'], str)


# ─── ChangeDetector ───────────────────────────────────────────────────────────

class TestChangeDetector:
    def _product(self, price=10000.0, stock='in_stock', alive=True):
        from src.source_monitor.engine import SourceProduct, SourceType, StockStatus
        ss = StockStatus(stock)
        return SourceProduct(
            source_product_id='sp-d', source_type=SourceType.coupang,
            source_url='https://example.com', seller_id='s1',
            seller_name='Seller', my_product_id='my-d', title='Product',
            current_price=price, original_price=price,
            stock_status=ss, is_alive=alive,
        )

    def _check_result(self, product, price=None, stock='in_stock', alive=True, seller_active=True):
        from src.source_monitor.checkers import CheckResult
        from src.source_monitor.engine import StockStatus
        return CheckResult(
            source_product_id=product.source_product_id,
            checked_at='',
            is_alive=alive,
            price=price if price is not None else product.current_price,
            stock_status=StockStatus(stock),
            seller_active=seller_active,
            changes_detected=False,
        )

    def test_no_changes(self):
        from src.source_monitor.change_detector import ChangeDetector
        detector = ChangeDetector()
        product = self._product()
        result = self._check_result(product)
        events = detector.detect(product, result)
        assert events == []

    def test_listing_removed(self):
        from src.source_monitor.change_detector import ChangeDetector, ChangeType, Severity
        detector = ChangeDetector()
        product = self._product()
        result = self._check_result(product, alive=False)
        events = detector.detect(product, result)
        assert any(e.change_type == ChangeType.listing_removed for e in events)
        assert any(e.severity == Severity.critical for e in events)

    def test_price_increase_high(self):
        from src.source_monitor.change_detector import ChangeDetector, ChangeType, Severity
        detector = ChangeDetector()
        product = self._product(price=10000.0)
        result = self._check_result(product, price=12500.0)  # 25% increase
        events = detector.detect(product, result)
        inc_events = [e for e in events if e.change_type == ChangeType.price_increase]
        assert len(inc_events) >= 1
        assert any(e.severity == Severity.high for e in inc_events)

    def test_price_increase_medium(self):
        from src.source_monitor.change_detector import ChangeDetector, ChangeType, Severity
        detector = ChangeDetector()
        product = self._product(price=10000.0)
        result = self._check_result(product, price=11500.0)  # 15% increase
        events = detector.detect(product, result)
        inc_events = [e for e in events if e.change_type == ChangeType.price_increase]
        assert len(inc_events) >= 1
        assert any(e.severity == Severity.medium for e in inc_events)

    def test_price_decrease(self):
        from src.source_monitor.change_detector import ChangeDetector, ChangeType
        detector = ChangeDetector()
        product = self._product(price=10000.0)
        result = self._check_result(product, price=7000.0)  # 30% decrease
        events = detector.detect(product, result)
        dec_events = [e for e in events if e.change_type == ChangeType.price_decrease]
        assert len(dec_events) >= 1

    def test_out_of_stock(self):
        from src.source_monitor.change_detector import ChangeDetector, ChangeType, Severity
        detector = ChangeDetector()
        product = self._product(stock='in_stock')
        result = self._check_result(product, stock='out_of_stock')
        events = detector.detect(product, result)
        oos_events = [e for e in events if e.change_type == ChangeType.out_of_stock]
        assert len(oos_events) >= 1
        assert any(e.severity == Severity.high for e in oos_events)

    def test_back_in_stock(self):
        from src.source_monitor.change_detector import ChangeDetector, ChangeType
        detector = ChangeDetector()
        product = self._product(stock='out_of_stock')
        result = self._check_result(product, stock='in_stock')
        events = detector.detect(product, result)
        bis_events = [e for e in events if e.change_type == ChangeType.back_in_stock]
        assert len(bis_events) >= 1

    def test_seller_deactivated(self):
        from src.source_monitor.change_detector import ChangeDetector, ChangeType, Severity
        detector = ChangeDetector()
        product = self._product()
        result = self._check_result(product, seller_active=False)
        events = detector.detect(product, result)
        sd_events = [e for e in events if e.change_type == ChangeType.seller_deactivated]
        assert len(sd_events) >= 1
        assert any(e.severity == Severity.critical for e in sd_events)

    def test_get_events(self):
        from src.source_monitor.change_detector import ChangeDetector
        detector = ChangeDetector()
        product = self._product()
        result = self._check_result(product, alive=False)
        detector.detect(product, result)
        events = detector.get_events()
        assert len(events) >= 1

    def test_get_events_filter_by_product(self):
        from src.source_monitor.change_detector import ChangeDetector
        detector = ChangeDetector()
        product = self._product()
        result = self._check_result(product, alive=False)
        detector.detect(product, result)
        events = detector.get_events(source_product_id='sp-d')
        assert all(e.source_product_id == 'sp-d' for e in events)

    def test_get_critical_events(self):
        from src.source_monitor.change_detector import ChangeDetector, Severity
        detector = ChangeDetector()
        product = self._product()
        result = self._check_result(product, alive=False)
        detector.detect(product, result)
        critical = detector.get_critical_events()
        assert all(e.severity == Severity.critical for e in critical)

    def test_get_stats(self):
        from src.source_monitor.change_detector import ChangeDetector
        detector = ChangeDetector()
        stats = detector.get_stats()
        assert 'total' in stats
        assert 'by_type' in stats
        assert 'by_severity' in stats


# ─── AutoDeactivationService ─────────────────────────────────────────────────

class TestAutoDeactivationService:
    def _service(self):
        from src.source_monitor.auto_deactivation import AutoDeactivationService
        return AutoDeactivationService()

    def _product(self):
        from src.source_monitor.engine import SourceProduct, SourceType
        return SourceProduct(
            source_product_id='sp-a', source_type=SourceType.coupang,
            source_url='https://example.com', seller_id='s1',
            seller_name='Seller', my_product_id='my-a',
            title='Product A', current_price=10000.0, original_price=10000.0,
        )

    def _event(self, change_type='listing_removed', severity='critical'):
        from src.source_monitor.change_detector import ChangeEvent, ChangeType, Severity
        return ChangeEvent(
            event_id='ev-a',
            source_product_id='sp-a',
            change_type=ChangeType(change_type),
            old_value='old',
            new_value='new',
            severity=Severity(severity),
        )

    def test_list_rules_default(self):
        svc = self._service()
        rules = svc.list_rules()
        assert len(rules) >= 5

    def test_process_event_listing_removed(self):
        svc = self._service()
        product = self._product()
        event = self._event('listing_removed', 'critical')
        action = svc.process_event(event, product)
        assert action == 'immediate_deactivate'

    def test_process_event_seller_deactivated(self):
        svc = self._service()
        product = self._product()
        event = self._event('seller_deactivated', 'critical')
        action = svc.process_event(event, product)
        assert action == 'immediate_deactivate'

    def test_process_event_out_of_stock(self):
        svc = self._service()
        product = self._product()
        event = self._event('out_of_stock', 'high')
        action = svc.process_event(event, product)
        assert action == 'immediate_deactivate'

    def test_add_rule(self):
        svc = self._service()
        rule = svc.add_rule({
            'trigger_type': 'custom_trigger',
            'action': 'notify_only',
            'delay_minutes': 10,
            'notify': True,
            'description': 'Test rule',
        })
        assert rule.trigger_type == 'custom_trigger'

    def test_list_deactivated(self):
        svc = self._service()
        product = self._product()
        event = self._event('listing_removed', 'critical')
        svc.process_event(event, product)
        deactivated = svc.list_deactivated()
        assert len(deactivated) >= 1

    def test_reactivate(self):
        svc = self._service()
        product = self._product()
        event = self._event('listing_removed', 'critical')
        svc.process_event(event, product)
        records = svc.list_deactivated()
        assert len(records) >= 1
        ok = svc.reactivate(records[0].record_id)
        assert ok is True

    def test_reactivate_missing(self):
        svc = self._service()
        ok = svc.reactivate('missing-id')
        assert ok is False

    def test_get_history(self):
        svc = self._service()
        product = self._product()
        event = self._event('listing_removed', 'critical')
        svc.process_event(event, product)
        history = svc.get_history()
        assert len(history) >= 1

    def test_get_history_filter(self):
        svc = self._service()
        product = self._product()
        event = self._event('listing_removed', 'critical')
        svc.process_event(event, product)
        history = svc.get_history(source_product_id='sp-a')
        assert all(r.source_product_id == 'sp-a' for r in history)


# ─── AlternativeSourceFinder ─────────────────────────────────────────────────

class TestAlternativeSourceFinder:
    def _finder(self):
        from src.source_monitor.alternative_finder import AlternativeSourceFinder
        return AlternativeSourceFinder()

    def _product(self):
        from src.source_monitor.engine import SourceProduct, SourceType
        return SourceProduct(
            source_product_id='sp-f', source_type=SourceType.amazon_us,
            source_url='https://amazon.com/dp/B001',
            seller_id='amz-s1', seller_name='Amazon Seller',
            my_product_id='my-f', title='Found Product',
            current_price=30000.0, original_price=35000.0,
        )

    def test_find_alternatives_returns_list(self):
        finder = self._finder()
        product = self._product()
        alts = finder.find_alternatives(product)
        assert isinstance(alts, list)
        assert len(alts) >= 1

    def test_find_alternatives_sorted_by_score(self):
        finder = self._finder()
        product = self._product()
        alts = finder.find_alternatives(product)
        scores = [a.match_score for a in alts]
        assert scores == sorted(scores, reverse=True)

    def test_alternative_has_required_fields(self):
        finder = self._finder()
        product = self._product()
        alts = finder.find_alternatives(product)
        for a in alts:
            assert a.alternative_id != ''
            assert a.price > 0
            assert 0 <= a.match_score <= 100
            assert a.estimated_delivery_days > 0

    def test_get_alternatives_after_find(self):
        finder = self._finder()
        product = self._product()
        finder.find_alternatives(product)
        alts = finder.get_alternatives('sp-f')
        assert len(alts) >= 1

    def test_get_alternatives_empty(self):
        finder = self._finder()
        alts = finder.get_alternatives('unknown')
        assert alts == []

    def test_approve_alternative(self):
        finder = self._finder()
        product = self._product()
        alts = finder.find_alternatives(product)
        assert len(alts) >= 1
        ok = finder.approve_alternative(alts[0].alternative_id, 'sp-f')
        assert ok is True
        assert alts[0].approved is True

    def test_approve_missing(self):
        finder = self._finder()
        ok = finder.approve_alternative('missing-id', 'sp-f')
        assert ok is False

    def test_switch_source_not_approved(self):
        finder = self._finder()
        product = self._product()
        alts = finder.find_alternatives(product)
        result = finder.switch_source(product, alts[0].alternative_id)
        assert result is None  # not approved yet

    def test_switch_source_approved(self):
        finder = self._finder()
        product = self._product()
        alts = finder.find_alternatives(product)
        finder.approve_alternative(alts[0].alternative_id, 'sp-f')
        result = finder.switch_source(product, alts[0].alternative_id)
        assert result is not None
        assert result['switched'] is True

    def test_match_score_calculation(self):
        finder = self._finder()
        score = finder._calculate_match_score(
            original_price=10000.0,
            alt_price=10000.0,  # 동일 가격
            seller_rating=5.0,
            delivery_days=2,    # 빠른 배송
            stock_stable=True,
        )
        assert score > 80.0  # 거의 완벽한 매칭

    def test_to_dict(self):
        finder = self._finder()
        product = self._product()
        alts = finder.find_alternatives(product)
        for a in alts:
            d = a.to_dict()
            assert 'alternative_id' in d
            assert 'match_score' in d
            assert isinstance(d['source_type'], str)


# ─── SourceMonitorScheduler ───────────────────────────────────────────────────

class TestSourceMonitorScheduler:
    def _scheduler(self):
        from src.source_monitor.scheduler import SourceMonitorScheduler
        return SourceMonitorScheduler()

    def _product(self, sp_id='sp-sch'):
        from src.source_monitor.engine import SourceProduct, SourceType
        return SourceProduct(
            source_product_id=sp_id, source_type=SourceType.coupang,
            source_url='https://example.com', seller_id='s1',
            seller_name='Seller', my_product_id='my-sch',
            title='Scheduled Product', current_price=5000.0, original_price=5000.0,
        )

    def test_register(self):
        scheduler = self._scheduler()
        product = self._product()
        entry = scheduler.register(product)
        assert entry.source_product_id == 'sp-sch'
        assert entry.next_check_at is not None

    def test_unregister(self):
        scheduler = self._scheduler()
        product = self._product()
        scheduler.register(product)
        ok = scheduler.unregister('sp-sch')
        assert ok is True

    def test_unregister_missing(self):
        scheduler = self._scheduler()
        ok = scheduler.unregister('missing')
        assert ok is False

    def test_mark_checked_success(self):
        scheduler = self._scheduler()
        product = self._product()
        scheduler.register(product)
        scheduler.mark_checked('sp-sch', success=True)
        entry = scheduler._schedule.get('sp-sch')
        assert entry.failure_count == 0
        assert entry.last_check_at is not None

    def test_mark_checked_failure_escalates(self):
        from src.source_monitor.scheduler import SourceMonitorScheduler
        scheduler = SourceMonitorScheduler()
        product = self._product()
        entry = scheduler.register(product)
        original_interval = entry.interval_minutes
        for _ in range(3):
            scheduler.mark_checked('sp-sch', success=False)
        updated_entry = scheduler._schedule.get('sp-sch')
        assert updated_entry.interval_minutes <= original_interval

    def test_update_interval(self):
        scheduler = self._scheduler()
        product = self._product()
        scheduler.register(product)
        ok = scheduler.update_interval('sp-sch', 60)
        assert ok is True
        assert scheduler._schedule['sp-sch'].interval_minutes == 60

    def test_get_stats(self):
        scheduler = self._scheduler()
        stats = scheduler.get_stats()
        assert 'total_scheduled' in stats

    def test_list_schedule(self):
        scheduler = self._scheduler()
        product = self._product()
        scheduler.register(product)
        schedules = scheduler.list_schedule()
        assert len(schedules) >= 1

    def test_priority_popular(self):
        from src.source_monitor.scheduler import INTERVAL_POPULAR
        scheduler = self._scheduler()
        product = self._product()
        entry = scheduler.register(product, priority=1)
        assert entry.interval_minutes == INTERVAL_POPULAR

    def test_priority_normal(self):
        from src.source_monitor.scheduler import INTERVAL_NORMAL
        scheduler = self._scheduler()
        product = self._product()
        entry = scheduler.register(product, priority=5)
        assert entry.interval_minutes == INTERVAL_NORMAL


# ─── SourceMonitorDashboard ───────────────────────────────────────────────────

class TestSourceMonitorDashboard:
    def _dashboard(self):
        from src.source_monitor.engine import SourceMonitorEngine
        from src.source_monitor.change_detector import ChangeDetector
        from src.source_monitor.auto_deactivation import AutoDeactivationService
        from src.source_monitor.scheduler import SourceMonitorScheduler
        from src.source_monitor.dashboard import SourceMonitorDashboard
        engine = SourceMonitorEngine()
        detector = ChangeDetector()
        deactivation_svc = AutoDeactivationService()
        scheduler = SourceMonitorScheduler()
        return SourceMonitorDashboard(engine, detector, deactivation_svc, scheduler)

    def test_get_dashboard(self):
        dashboard = self._dashboard()
        data = dashboard.get_dashboard()
        assert 'summary' in data
        assert 'recent_events' in data
        assert 'critical_events_count' in data
        assert 'deactivated_count' in data
        assert 'check_success_rate' in data

    def test_get_dashboard_check_success_rate_empty(self):
        dashboard = self._dashboard()
        data = dashboard.get_dashboard()
        assert data['check_success_rate'] == 100.0

    def test_get_price_trend(self):
        dashboard = self._dashboard()
        data = dashboard.get_price_trend('sp-1')
        assert 'source_product_id' in data
        assert 'price_events' in data

    def test_get_status_overview(self):
        dashboard = self._dashboard()
        overview = dashboard.get_status_overview()
        assert 'total' in overview
        assert 'by_status' in overview
        assert 'alive' in overview
        assert 'dead' in overview


# ─── API Blueprint ────────────────────────────────────────────────────────────

class TestSourceMonitorAPI:
    @pytest.fixture
    def client(self):
        from flask import Flask
        from src.api.source_monitor_api import source_monitor_bp, _get_engine, _get_detector, \
            _get_deactivation_svc, _get_alternative_finder, _get_scheduler, _get_dashboard
        import src.api.source_monitor_api as api_module

        # Reset global singletons for test isolation
        api_module._engine = None
        api_module._detector = None
        api_module._deactivation_svc = None
        api_module._alternative_finder = None
        api_module._scheduler = None
        api_module._dashboard = None

        app = Flask(__name__)
        app.config['TESTING'] = True
        app.register_blueprint(source_monitor_bp)
        with app.test_client() as c:
            yield c

    def _register_product(self, client, **kwargs):
        import json
        data = dict(
            source_type='coupang',
            source_url='https://coupang.com/vp/1',
            seller_id='s1',
            seller_name='Seller',
            my_product_id='my-1',
            title='Test Product',
            current_price=10000.0,
            original_price=12000.0,
        )
        data.update(kwargs)
        resp = client.post(
            '/api/v1/source-monitor/sources',
            data=json.dumps(data),
            content_type='application/json',
        )
        return resp

    def test_register_source(self, client):
        resp = self._register_product(client)
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['success'] is True
        assert 'product' in data

    def test_list_sources(self, client):
        self._register_product(client)
        resp = client.get('/api/v1/source-monitor/sources')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['total'] >= 1

    def test_get_source(self, client):
        import json
        resp = self._register_product(client, source_product_id='sp-get')
        sp_id = resp.get_json()['product']['source_product_id']
        resp2 = client.get(f'/api/v1/source-monitor/sources/{sp_id}')
        assert resp2.status_code == 200

    def test_get_source_not_found(self, client):
        resp = client.get('/api/v1/source-monitor/sources/missing-id')
        assert resp.status_code == 404

    def test_update_source(self, client):
        import json
        resp = self._register_product(client, source_product_id='sp-upd')
        sp_id = resp.get_json()['product']['source_product_id']
        resp2 = client.put(
            f'/api/v1/source-monitor/sources/{sp_id}',
            data=json.dumps({'title': 'Updated Product'}),
            content_type='application/json',
        )
        assert resp2.status_code == 200

    def test_delete_source(self, client):
        resp = self._register_product(client, source_product_id='sp-del')
        sp_id = resp.get_json()['product']['source_product_id']
        resp2 = client.delete(f'/api/v1/source-monitor/sources/{sp_id}')
        assert resp2.status_code == 200

    def test_delete_source_not_found(self, client):
        resp = client.delete('/api/v1/source-monitor/sources/missing')
        assert resp.status_code == 404

    def test_check_source(self, client):
        resp = self._register_product(client, source_product_id='sp-chk')
        sp_id = resp.get_json()['product']['source_product_id']
        resp2 = client.post(f'/api/v1/source-monitor/sources/{sp_id}/check')
        assert resp2.status_code == 200
        data = resp2.get_json()
        assert 'check_result' in data

    def test_check_source_not_found(self, client):
        resp = client.post('/api/v1/source-monitor/sources/missing/check')
        assert resp.status_code == 404

    def test_get_source_history(self, client):
        resp = self._register_product(client, source_product_id='sp-hist')
        sp_id = resp.get_json()['product']['source_product_id']
        resp2 = client.get(f'/api/v1/source-monitor/sources/{sp_id}/history')
        assert resp2.status_code == 200

    def test_get_alternatives(self, client):
        resp = self._register_product(client, source_product_id='sp-alt')
        sp_id = resp.get_json()['product']['source_product_id']
        resp2 = client.get(f'/api/v1/source-monitor/sources/{sp_id}/alternatives')
        assert resp2.status_code == 200
        data = resp2.get_json()
        assert 'alternatives' in data

    def test_list_changes(self, client):
        resp = client.get('/api/v1/source-monitor/changes')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'events' in data

    def test_list_critical_changes(self, client):
        resp = client.get('/api/v1/source-monitor/changes/critical')
        assert resp.status_code == 200

    def test_list_deactivated(self, client):
        resp = client.get('/api/v1/source-monitor/deactivated')
        assert resp.status_code == 200

    def test_list_rules(self, client):
        resp = client.get('/api/v1/source-monitor/rules')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['total'] >= 5

    def test_add_rule(self, client):
        import json
        resp = client.post(
            '/api/v1/source-monitor/rules',
            data=json.dumps({
                'trigger_type': 'custom_event',
                'action': 'notify_only',
            }),
            content_type='application/json',
        )
        assert resp.status_code == 201

    def test_get_dashboard(self, client):
        resp = client.get('/api/v1/source-monitor/dashboard')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'summary' in data


# ─── Bot Commands ─────────────────────────────────────────────────────────────

class TestBotCommands:
    def test_cmd_source_status(self):
        from src.bot.commands import cmd_source_status
        result = cmd_source_status()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_cmd_source_check(self):
        from src.bot.commands import cmd_source_check
        result = cmd_source_check('nonexistent-product')
        assert isinstance(result, str)
        assert len(result) > 0

    def test_cmd_source_alerts(self):
        from src.bot.commands import cmd_source_alerts
        result = cmd_source_alerts()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_cmd_source_dead(self):
        from src.bot.commands import cmd_source_dead
        result = cmd_source_dead()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_cmd_source_dashboard(self):
        from src.bot.commands import cmd_source_dashboard
        result = cmd_source_dashboard()
        assert isinstance(result, str)
        assert len(result) > 0


# ─── Formatters ──────────────────────────────────────────────────────────────

class TestFormatters:
    def test_format_source_product(self):
        from src.bot.formatters import format_message
        data = {
            'source_product_id': 'sp-1',
            'title': '테스트 상품',
            'source_type': 'coupang',
            'current_price': 10000.0,
            'currency': 'KRW',
            'stock_status': 'in_stock',
            'status': 'active',
            'is_alive': True,
        }
        result = format_message('source_product', data)
        assert 'sp-1' in result
        assert '테스트 상품' in result

    def test_format_source_status(self):
        from src.bot.formatters import format_message
        data = {
            'total': 10,
            'active': 8,
            'problem': 2,
            'inactive': 0,
            'by_source_type': {'coupang': 5, 'naver': 5},
        }
        result = format_message('source_status', data)
        assert '10' in result

    def test_format_source_change_event(self):
        from src.bot.formatters import format_message
        data = {
            'source_product_id': 'sp-1',
            'change_type': 'price_increase',
            'old_value': '10000',
            'new_value': '13000',
            'severity': 'high',
        }
        result = format_message('source_change_event', data)
        assert 'price_increase' in result
        assert 'high' in result

    def test_format_source_alternatives(self):
        from src.bot.formatters import format_message
        data = [
            {
                'alternative_id': 'a1',
                'source_type': 'naver',
                'price': 11000.0,
                'seller_rating': 4.5,
                'estimated_delivery_days': 3,
                'match_score': 85.0,
                'approved': False,
            }
        ]
        result = format_message('source_alternatives', data)
        assert 'naver' in result

    def test_format_source_dashboard(self):
        from src.bot.formatters import format_message
        data = {
            'summary': {'total': 5, 'active': 4, 'problem': 1, 'inactive': 0},
            'critical_events_count': 2,
            'deactivated_count': 1,
            'check_success_rate': 95.0,
            'auto_processed': 3,
            'manual_required': 2,
        }
        result = format_message('source_dashboard', data)
        assert '5' in result
        assert '95.0' in result
