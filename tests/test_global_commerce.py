"""tests/test_global_commerce.py — Phase 93: 글로벌 커머스 시스템 테스트."""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest

from src.global_commerce.i18n.i18n_manager import I18nManager, SUPPORTED_LOCALES
from src.global_commerce.i18n.locale_detector import LocaleDetector
from src.global_commerce.i18n.translation_sync import TranslationSync
from src.global_commerce.i18n.localized_product_page import LocalizedProductPage
from src.global_commerce.payments.global_payment_router import GlobalPaymentRouter
from src.global_commerce.payments.cross_border_settlement import CrossBorderSettlement
from src.global_commerce.payments.payment_compliance_checker import PaymentComplianceChecker
from src.global_commerce.trade.trade_direction import TradeDirection
from src.global_commerce.trade.import_manager import (
    ImportManager, ImportStatus, CustomsDutyCalculator, CustomsClearanceTracker
)
from src.global_commerce.trade.export_manager import ExportManager, ExportStatus
from src.global_commerce.trade.trade_compliance_checker import TradeComplianceChecker
from src.global_commerce.shipping.international_shipping_manager import InternationalShippingManager
from src.global_commerce.shipping.forwarding_agent import MoltailAgent, OhmyzipAgent
from src.global_commerce.shipping.shipping_insurance import ShippingInsurance


# ---------------------------------------------------------------------------
# I18nManager
# ---------------------------------------------------------------------------

class TestI18nManagerCreate:
    def test_set_and_get_content(self):
        mgr = I18nManager()
        content = mgr.set_content('SKU-001', 'ko', '테스트 상품', '설명', ['특징1'])
        assert content['sku'] == 'SKU-001'
        assert content['locale'] == 'ko'
        assert content['title'] == '테스트 상품'

    def test_get_existing_locale(self):
        mgr = I18nManager()
        mgr.set_content('SKU-001', 'ko', '제목', '설명')
        mgr.set_content('SKU-001', 'en', 'Title', 'Description')
        result = mgr.get_content('SKU-001', 'en')
        assert result['title'] == 'Title'
        assert result['locale'] == 'en'

    def test_fallback_to_default_locale(self):
        mgr = I18nManager(default_locale='ko')
        mgr.set_content('SKU-001', 'ko', '한국어 제목', '한국어 설명')
        result = mgr.get_content('SKU-001', 'ja')  # ja 없음 → ko 폴백
        assert result is not None
        assert result['title'] == '한국어 제목'
        assert result.get('_fallback') is True
        assert result.get('_requested_locale') == 'ja'

    def test_get_nonexistent_sku(self):
        mgr = I18nManager()
        assert mgr.get_content('NONEXISTENT', 'ko') is None

    def test_supported_locales(self):
        mgr = I18nManager()
        locales = mgr.supported_locales()
        for l in ('ko', 'en', 'ja', 'zh'):
            assert l in locales

    def test_invalid_locale_raises(self):
        mgr = I18nManager()
        with pytest.raises(ValueError):
            mgr.set_content('SKU-001', 'xx', '제목', '설명')

    def test_invalid_default_locale_raises(self):
        with pytest.raises(ValueError):
            I18nManager(default_locale='fr')

    def test_list_locales(self):
        mgr = I18nManager()
        mgr.set_content('SKU-001', 'ko', '제목', '설명')
        mgr.set_content('SKU-001', 'en', 'Title', 'Desc')
        locales = mgr.list_locales('SKU-001')
        assert 'ko' in locales
        assert 'en' in locales

    def test_delete_content(self):
        mgr = I18nManager()
        mgr.set_content('SKU-001', 'ko', '제목', '설명')
        result = mgr.delete_content('SKU-001', 'ko')
        assert result is True
        assert mgr.get_content('SKU-001', 'ko') is None

    def test_list_skus(self):
        mgr = I18nManager()
        mgr.set_content('SKU-001', 'ko', '제목1', '설명1')
        mgr.set_content('SKU-002', 'en', 'Title2', 'Desc2')
        skus = mgr.list_skus()
        assert 'SKU-001' in skus
        assert 'SKU-002' in skus

    def test_all_locales_stored(self):
        mgr = I18nManager()
        for locale in ('ko', 'en', 'ja', 'zh'):
            mgr.set_content('SKU-ALL', locale, f'Title {locale}', f'Desc {locale}')
        assert len(mgr.list_locales('SKU-ALL')) == 4

    def test_set_default_locale(self):
        mgr = I18nManager()
        mgr.set_default_locale('en')
        assert mgr.default_locale == 'en'

    def test_set_invalid_default_locale_raises(self):
        mgr = I18nManager()
        with pytest.raises(ValueError):
            mgr.set_default_locale('fr')

    def test_fallback_to_first_available_when_no_default(self):
        mgr = I18nManager(default_locale='ko')
        mgr.set_content('SKU-001', 'en', 'English Title', 'Desc')
        # ko 없고 en만 있음, 요청은 ja
        result = mgr.get_content('SKU-001', 'ja')
        assert result is not None
        assert result.get('_fallback') is True


# ---------------------------------------------------------------------------
# LocaleDetector
# ---------------------------------------------------------------------------

class TestLocaleDetector:
    def test_detect_ko_from_header(self):
        detector = LocaleDetector()
        assert detector.detect_from_header('ko-KR,ko;q=0.9,en;q=0.8') == 'ko'

    def test_detect_en_from_header(self):
        detector = LocaleDetector()
        assert detector.detect_from_header('en-US,en;q=0.9') == 'en'

    def test_detect_ja_from_header(self):
        detector = LocaleDetector()
        assert detector.detect_from_header('ja-JP,ja;q=0.9') == 'ja'

    def test_detect_zh_from_header(self):
        detector = LocaleDetector()
        assert detector.detect_from_header('zh-CN,zh;q=0.9') == 'zh'

    def test_unknown_locale_falls_back_to_default(self):
        detector = LocaleDetector()
        result = detector.detect_from_header('fr-FR,fr;q=0.9')
        assert result == detector.default

    def test_empty_header_returns_default(self):
        detector = LocaleDetector()
        assert detector.detect_from_header('') == detector.default

    def test_user_preference_takes_priority(self):
        detector = LocaleDetector()
        result = detector.detect(accept_language='en-US', user_preference='ja')
        assert result == 'ja'

    def test_detect_from_user_preference(self):
        detector = LocaleDetector()
        assert detector.detect_from_user_preference('en') == 'en'
        assert detector.detect_from_user_preference('xx') == detector.default

    def test_detect_falls_back_to_accept_language(self):
        detector = LocaleDetector()
        result = detector.detect(accept_language='ja-JP', user_preference=None)
        assert result == 'ja'

    def test_quality_ordering(self):
        detector = LocaleDetector()
        # zh (0.8) > en (0.9) — en wins
        result = detector.detect_from_header('en;q=0.9,zh;q=0.8')
        assert result == 'en'


# ---------------------------------------------------------------------------
# TranslationSync
# ---------------------------------------------------------------------------

class TestTranslationSync:
    def test_sync_without_provider(self):
        sync = TranslationSync()
        result = sync.sync_product('SKU-001', 'ko', 'en', '제목', '설명')
        assert result['sku'] == 'SKU-001'
        assert result['status'] == 'no_provider'

    def test_get_sync_status_not_synced(self):
        sync = TranslationSync()
        result = sync.get_sync_status('SKU-001', 'en')
        assert result['status'] == 'not_synced'

    def test_get_sync_status_all_locales(self):
        sync = TranslationSync()
        sync.sync_product('SKU-001', 'ko', 'en', '제목', '설명')
        result = sync.get_sync_status('SKU-001')
        assert 'statuses' in result

    def test_list_pending_empty(self):
        sync = TranslationSync()
        assert sync.list_pending() == []


# ---------------------------------------------------------------------------
# LocalizedProductPage
# ---------------------------------------------------------------------------

class TestLocalizedProductPage:
    def _make_page(self):
        i18n = I18nManager()
        i18n.set_content('SKU-001', 'ko', '한국어 제목', '한국어 설명', ['기능1'])
        i18n.set_content('SKU-001', 'en', 'English Title', 'English Desc', ['Feature1'])
        return LocalizedProductPage(i18n_manager=i18n, base_url='https://test.com')

    def test_build_ko(self):
        page = self._make_page()
        result = page.build('SKU-001', 'ko', price=10000)
        assert result['title'] == '한국어 제목'
        assert result['locale'] == 'ko'
        assert result['currency'] == 'KRW'
        assert 'seo' in result

    def test_build_en(self):
        page = self._make_page()
        result = page.build('SKU-001', 'en', price=10.0)
        assert result['title'] == 'English Title'
        assert result['currency'] == 'USD'

    def test_build_fallback(self):
        page = self._make_page()
        result = page.build('SKU-001', 'zh')  # zh 없음 → ko 폴백
        assert result['is_fallback'] is True

    def test_build_not_found(self):
        page = self._make_page()
        result = page.build('NONEXISTENT', 'ko')
        assert 'error' in result

    def test_seo_meta_keys(self):
        page = self._make_page()
        result = page.build('SKU-001', 'ko')
        seo = result['seo']
        assert 'title' in seo
        assert 'canonical' in seo
        assert 'og_title' in seo
        assert 'hreflang' in seo

    def test_detect_locale(self):
        page = self._make_page()
        locale = page.detect_locale(accept_language='en-US')
        assert locale == 'en'


# ---------------------------------------------------------------------------
# GlobalPaymentRouter
# ---------------------------------------------------------------------------

class TestGlobalPaymentRouter:
    def test_route_kr_returns_toss(self):
        router = GlobalPaymentRouter()
        result = router.route('KR', 'KRW')
        assert result.pg_name == 'toss'

    def test_route_cn_returns_alipay(self):
        router = GlobalPaymentRouter()
        result = router.route('CN', 'CNY')
        assert result.pg_name == 'alipay'

    def test_route_us_returns_stripe(self):
        router = GlobalPaymentRouter()
        result = router.route('US', 'USD')
        assert result.pg_name == 'stripe'

    def test_route_unknown_country_falls_back(self):
        router = GlobalPaymentRouter()
        result = router.route('XX', 'USD')
        assert result.pg_name in ('stripe', 'paypal')

    def test_route_result_to_dict(self):
        router = GlobalPaymentRouter()
        result = router.route('US', 'USD')
        d = result.to_dict()
        assert 'pg_name' in d
        assert 'supported' in d

    def test_process_payment_stripe(self):
        router = GlobalPaymentRouter()
        result = router.process_payment('US', 'USD', 100.0, 'ORD-001')
        assert result.status in ('succeeded', 'COMPLETED', 'TRADE_SUCCESS', 'DONE')
        assert result.amount == 100.0

    def test_process_payment_toss(self):
        router = GlobalPaymentRouter()
        result = router.process_payment('KR', 'KRW', 50000.0, 'ORD-002')
        assert result.pg_name == 'toss'
        assert result.status == 'DONE'

    def test_list_supported_countries(self):
        router = GlobalPaymentRouter()
        countries = router.list_supported_countries()
        assert 'KR' in countries
        assert 'US' in countries

    def test_list_supported_currencies(self):
        router = GlobalPaymentRouter()
        currencies = router.list_supported_currencies()
        assert 'KRW' in currencies
        assert 'USD' in currencies

    def test_payment_result_has_payment_id(self):
        router = GlobalPaymentRouter()
        result = router.process_payment('US', 'USD', 50.0, 'ORD-003')
        assert result.payment_id

    def test_route_has_alternative_pgs(self):
        router = GlobalPaymentRouter()
        result = router.route('US', 'USD')
        assert isinstance(result.alternative_pgs, list)


# ---------------------------------------------------------------------------
# CrossBorderSettlement
# ---------------------------------------------------------------------------

class TestCrossBorderSettlement:
    def test_settle_usd(self):
        sett = CrossBorderSettlement()
        record = sett.settle('ORD-001', 100.0, 'USD')
        assert record.original_currency == 'USD'
        assert record.settled_amount_krw == pytest.approx(100.0 * 1350.0, rel=0.01)
        assert record.net_amount_krw < record.settled_amount_krw

    def test_settle_krw_no_remittance_fee(self):
        sett = CrossBorderSettlement()
        record = sett.settle('ORD-002', 50000.0, 'KRW')
        assert record.remittance_fee == 0.0

    def test_fx_fee_calculation(self):
        sett = CrossBorderSettlement()
        fee = sett.calculate_fx_fee(1000000.0, 'USD')
        assert fee == pytest.approx(1000000.0 * 0.015, rel=0.01)

    def test_remittance_fee_minimum(self):
        sett = CrossBorderSettlement()
        fee = sett.calculate_remittance_fee(100.0)
        assert fee == 5000.0  # minimum

    def test_to_krw_conversion(self):
        sett = CrossBorderSettlement()
        krw = sett.to_krw(1.0, 'USD')
        assert krw == 1350.0

    def test_settlement_cycle(self):
        sett = CrossBorderSettlement()
        assert sett.get_settlement_cycle('KRW') == 1
        assert sett.get_settlement_cycle('USD') == 2
        assert sett.get_settlement_cycle('CNY') == 5

    def test_list_records(self):
        sett = CrossBorderSettlement()
        sett.settle('ORD-001', 100.0, 'USD')
        sett.settle('ORD-002', 50.0, 'EUR')
        assert len(sett.list_records()) == 2

    def test_list_records_by_order(self):
        sett = CrossBorderSettlement()
        sett.settle('ORD-001', 100.0, 'USD')
        sett.settle('ORD-002', 50.0, 'EUR')
        assert len(sett.list_records(order_id='ORD-001')) == 1

    def test_record_to_dict(self):
        sett = CrossBorderSettlement()
        record = sett.settle('ORD-001', 100.0, 'USD')
        d = record.to_dict()
        assert 'settlement_id' in d
        assert 'net_amount_krw' in d


# ---------------------------------------------------------------------------
# PaymentComplianceChecker
# ---------------------------------------------------------------------------

class TestPaymentComplianceChecker:
    def test_small_amount_passes(self):
        checker = PaymentComplianceChecker()
        result = checker.check(100.0, 'USD', 'US')
        assert result.passed is True
        assert len(result.violations) == 0

    def test_exceeds_limit_fails(self):
        checker = PaymentComplianceChecker()
        result = checker.check(15000.0, 'USD', 'US')  # > 10000 limit
        assert result.passed is False
        assert len(result.violations) > 0

    def test_kyc_required_for_large_amount(self):
        checker = PaymentComplianceChecker()
        result = checker.check(5000.0, 'USD', 'US')
        assert result.kyc_required is True

    def test_kyc_not_required_for_small_amount(self):
        checker = PaymentComplianceChecker()
        result = checker.check(100.0, 'USD', 'US')
        assert result.kyc_required is False

    def test_result_to_dict(self):
        checker = PaymentComplianceChecker()
        result = checker.check(100.0, 'USD', 'KR')
        d = result.to_dict()
        assert 'passed' in d
        assert 'kyc_required' in d
        assert 'violations' in d


# ---------------------------------------------------------------------------
# TradeDirection
# ---------------------------------------------------------------------------

class TestTradeDirection:
    def test_import_value(self):
        assert TradeDirection.IMPORT.value == 'import'

    def test_export_value(self):
        assert TradeDirection.EXPORT.value == 'export'

    def test_proxy_buy_value(self):
        assert TradeDirection.PROXY_BUY.value == 'proxy_buy'

    def test_from_string(self):
        assert TradeDirection('import') == TradeDirection.IMPORT


# ---------------------------------------------------------------------------
# ImportManager
# ---------------------------------------------------------------------------

class TestImportManager:
    def test_create_import_order(self):
        mgr = ImportManager()
        order = mgr.create('https://amazon.com/item', 'US')
        assert order.order_id
        assert order.source_country == 'US'
        assert order.status == ImportStatus.PLACED

    def test_get_existing_order(self):
        mgr = ImportManager()
        order = mgr.create('https://example.com', 'JP')
        found = mgr.get(order.order_id)
        assert found is not None
        assert found.order_id == order.order_id

    def test_get_nonexistent_order(self):
        mgr = ImportManager()
        assert mgr.get('nonexistent') is None

    def test_transition_placed_to_purchased(self):
        mgr = ImportManager()
        order = mgr.create('https://example.com', 'US')
        updated = mgr.transition(order.order_id, 'purchased')
        assert updated.status == ImportStatus.PURCHASED

    def test_transition_full_flow(self):
        mgr = ImportManager()
        order = mgr.create('https://example.com', 'US')
        for status in ('purchased', 'in_transit', 'customs', 'cleared', 'delivered'):
            order = mgr.transition(order.order_id, status)
        assert order.status == ImportStatus.DELIVERED

    def test_invalid_transition_raises(self):
        mgr = ImportManager()
        order = mgr.create('https://example.com', 'US')
        with pytest.raises(ValueError):
            mgr.transition(order.order_id, 'delivered')  # 바로 delivered 불가

    def test_invalid_status_raises(self):
        mgr = ImportManager()
        order = mgr.create('https://example.com', 'US')
        with pytest.raises(ValueError):
            mgr.transition(order.order_id, 'invalid_status')

    def test_transition_nonexistent_raises(self):
        mgr = ImportManager()
        with pytest.raises(KeyError):
            mgr.transition('nonexistent', 'purchased')

    def test_list_all(self):
        mgr = ImportManager()
        mgr.create('https://a.com', 'US')
        mgr.create('https://b.com', 'JP')
        assert len(mgr.list()) == 2

    def test_list_by_status(self):
        mgr = ImportManager()
        order = mgr.create('https://a.com', 'US')
        mgr.create('https://b.com', 'JP')
        mgr.transition(order.order_id, 'purchased')
        placed = mgr.list(status='placed')
        assert len(placed) == 1

    def test_list_by_source_country(self):
        mgr = ImportManager()
        mgr.create('https://a.com', 'US')
        mgr.create('https://b.com', 'JP')
        us_orders = mgr.list(source_country='US')
        assert len(us_orders) == 1

    def test_to_dict_keys(self):
        mgr = ImportManager()
        order = mgr.create('https://example.com', 'US', product_name='Phone',
                            quantity=2, unit_price_usd=500.0)
        d = order.to_dict()
        assert d['total_price_usd'] == 1000.0
        assert 'order_id' in d
        assert 'status' in d

    def test_cancel_from_placed(self):
        mgr = ImportManager()
        order = mgr.create('https://example.com', 'US')
        cancelled = mgr.transition(order.order_id, 'cancelled')
        assert cancelled.status == ImportStatus.CANCELLED

    def test_customs_tracking_on_customs_arrival(self):
        mgr = ImportManager()
        order = mgr.create('https://example.com', 'US')
        mgr.transition(order.order_id, 'purchased')
        mgr.transition(order.order_id, 'in_transit')
        mgr.transition(order.order_id, 'customs')
        history = mgr.customs_tracker.get_history(order.order_id)
        assert len(history) >= 1
        assert history[0]['event_type'] == 'customs_arrived'


# ---------------------------------------------------------------------------
# CustomsDutyCalculator
# ---------------------------------------------------------------------------

class TestCustomsDutyCalculator:
    def test_duty_free_us_under_threshold(self):
        calc = CustomsDutyCalculator()
        result = calc.calculate(100.0, 'DEFAULT', 'US')
        assert result['duty_free'] is True

    def test_duty_free_us_at_threshold(self):
        calc = CustomsDutyCalculator()
        result = calc.calculate(800.0, 'DEFAULT', 'US')
        assert result['duty_free'] is True

    def test_duty_charged_us_over_threshold(self):
        calc = CustomsDutyCalculator()
        result = calc.calculate(801.0, 'DEFAULT', 'US')
        assert result['duty_free'] is False
        assert result['customs_duty_krw'] > 0

    def test_duty_free_kr_under_150(self):
        calc = CustomsDutyCalculator()
        result = calc.calculate(100.0, 'DEFAULT', 'KR')
        assert result['duty_free'] is True

    def test_vat_calculated(self):
        calc = CustomsDutyCalculator()
        result = calc.calculate(1000.0, '6109', 'US')
        assert result['vat_krw'] > 0

    def test_computer_zero_duty(self):
        calc = CustomsDutyCalculator()
        rate = calc.get_duty_rate('8471')
        assert rate == 0.0

    def test_clothing_duty_rate(self):
        calc = CustomsDutyCalculator()
        rate = calc.get_duty_rate('6109')
        assert rate == 0.13

    def test_is_duty_free_check(self):
        calc = CustomsDutyCalculator()
        assert calc.is_duty_free(100.0, 'KR') is True
        assert calc.is_duty_free(200.0, 'KR') is False

    def test_default_hs_code_rate(self):
        calc = CustomsDutyCalculator()
        rate = calc.get_duty_rate('9999')  # 없는 코드
        assert rate == 0.08  # default rate


# ---------------------------------------------------------------------------
# ExportManager
# ---------------------------------------------------------------------------

class TestExportManager:
    def test_create_export_order(self):
        mgr = ExportManager()
        order = mgr.create('Phone', 'KR', 'US', quantity=1, unit_price_usd=500.0,
                           customer_name='John Doe', customer_address='123 Main St')
        assert order.order_id
        assert order.status == ExportStatus.ORDERED
        assert order.destination_country == 'US'

    def test_transition_ordered_to_collected(self):
        mgr = ExportManager()
        order = mgr.create('Phone', 'KR', 'US')
        updated = mgr.transition(order.order_id, 'collected')
        assert updated.status == ExportStatus.COLLECTED

    def test_transition_full_flow(self):
        mgr = ExportManager()
        order = mgr.create('Phone', 'KR', 'US', unit_price_usd=100.0)
        for status in ('collected', 'quality_check', 'shipped', 'delivered'):
            order = mgr.transition(order.order_id, status)
        assert order.status == ExportStatus.DELIVERED

    def test_invalid_transition_raises(self):
        mgr = ExportManager()
        order = mgr.create('Phone', 'KR', 'US')
        with pytest.raises(ValueError):
            mgr.transition(order.order_id, 'delivered')

    def test_generate_invoice(self):
        mgr = ExportManager()
        order = mgr.create('Phone', 'KR', 'US', quantity=2, unit_price_usd=500.0,
                           customer_name='John')
        invoice = mgr.generate_invoice(order.order_id)
        assert 'invoice_number' in invoice
        assert invoice['total_usd'] == 1000.0

    def test_generate_packing_list(self):
        mgr = ExportManager()
        order = mgr.create('Phone', 'KR', 'US', quantity=2)
        packing = mgr.generate_packing_list(order.order_id)
        assert 'packing_list_number' in packing
        assert packing['total_packages'] == 1

    def test_list_all(self):
        mgr = ExportManager()
        mgr.create('A', 'KR', 'US')
        mgr.create('B', 'KR', 'JP')
        assert len(mgr.list()) == 2

    def test_list_by_destination(self):
        mgr = ExportManager()
        mgr.create('A', 'KR', 'US')
        mgr.create('B', 'KR', 'JP')
        us = mgr.list(destination_country='US')
        assert len(us) == 1

    def test_total_price_calculation(self):
        mgr = ExportManager()
        order = mgr.create('Item', 'KR', 'US', quantity=3, unit_price_usd=100.0)
        assert order.total_price_usd == 300.0

    def test_tracking_number_on_shipped(self):
        mgr = ExportManager()
        order = mgr.create('Item', 'KR', 'US')
        mgr.transition(order.order_id, 'collected')
        mgr.transition(order.order_id, 'quality_check')
        updated = mgr.transition(order.order_id, 'shipped', tracking_number='TRACK123')
        assert updated.tracking_number == 'TRACK123'


# ---------------------------------------------------------------------------
# TradeComplianceChecker
# ---------------------------------------------------------------------------

class TestTradeComplianceChecker:
    def test_normal_product_passes(self):
        checker = TradeComplianceChecker()
        result = checker.check('import', 'US', 'KR', 'Laptop', 1)
        assert result.passed is True

    def test_prohibited_keyword_fails(self):
        checker = TradeComplianceChecker()
        result = checker.check('import', 'US', 'KR', 'illegal drug powder', 1)
        assert result.passed is False
        assert len(result.violations) > 0

    def test_export_restricted_country_fails(self):
        checker = TradeComplianceChecker()
        result = checker.check('export', 'KR', 'KP', 'Electronics', 1)
        assert result.passed is False

    def test_import_from_restricted_country_fails(self):
        checker = TradeComplianceChecker()
        result = checker.check('import', 'KP', 'KR', 'Goods', 1)
        assert result.passed is False

    def test_quantity_limit_warning(self):
        checker = TradeComplianceChecker()
        result = checker.check('import', 'US', 'KR', 'cosmetic item', 20)
        assert len(result.warnings) > 0

    def test_result_to_dict(self):
        checker = TradeComplianceChecker()
        result = checker.check('import', 'US', 'KR', 'Phone', 1)
        d = result.to_dict()
        assert 'passed' in d
        assert 'violations' in d
        assert 'warnings' in d


# ---------------------------------------------------------------------------
# InternationalShippingManager
# ---------------------------------------------------------------------------

class TestInternationalShippingManager:
    def test_calculate_basic(self):
        mgr = InternationalShippingManager()
        quote = mgr.calculate(1.0, 'KR', 'US')
        assert quote.total_fee_krw > 0
        assert quote.transit_days == 7

    def test_calculate_with_dimensions(self):
        mgr = InternationalShippingManager()
        quote = mgr.calculate(0.5, 'KR', 'JP', length_cm=30, width_cm=20, height_cm=10)
        assert quote.volumetric_weight_kg > 0

    def test_chargeable_weight_is_max(self):
        mgr = InternationalShippingManager()
        # 부피 무게가 실제 무게보다 클 때
        quote = mgr.calculate(0.1, 'KR', 'US', length_cm=50, width_cm=50, height_cm=50)
        assert quote.chargeable_weight_kg >= quote.actual_weight_kg

    def test_fuel_surcharge_applied(self):
        mgr = InternationalShippingManager()
        quote = mgr.calculate(1.0, 'KR', 'US')
        expected_surcharge = round(quote.base_fee_krw * 0.12, 0)
        assert quote.fuel_surcharge_krw == expected_surcharge

    def test_get_route(self):
        mgr = InternationalShippingManager()
        route = mgr.get_route('KR', 'US')
        assert route.origin_country == 'KR'
        assert route.destination_country == 'US'
        assert route.origin_hub == 'ICN'
        assert route.destination_hub == 'LAX'

    def test_route_to_dict(self):
        mgr = InternationalShippingManager()
        route = mgr.get_route('KR', 'JP')
        d = route.to_dict()
        assert 'transit_days' in d
        assert 'waypoints' in d

    def test_quote_to_dict(self):
        mgr = InternationalShippingManager()
        quote = mgr.calculate(1.0, 'KR', 'US')
        d = quote.to_dict()
        assert 'total_fee_krw' in d
        assert 'transit_days' in d

    def test_volumetric_weight_calculation(self):
        mgr = InternationalShippingManager()
        vol = mgr.calculate_volumetric_weight(50, 40, 30)
        assert vol == pytest.approx(50 * 40 * 30 / 5000.0, rel=0.01)

    def test_minimum_chargeable_weight(self):
        mgr = InternationalShippingManager()
        quote = mgr.calculate(0.0, 'KR', 'US')
        assert quote.chargeable_weight_kg >= 0.1


# ---------------------------------------------------------------------------
# ForwardingAgent (Moltail)
# ---------------------------------------------------------------------------

class TestMoltailAgent:
    def test_confirm_inbound(self):
        agent = MoltailAgent()
        item = agent.confirm_inbound('ORD-001', 'Shoes', 1, 0.5)
        assert item.item_id.startswith('MT-')
        assert item.agent_id == 'moltail'
        assert item.status == 'received'

    def test_request_consolidation(self):
        agent = MoltailAgent()
        item = agent.confirm_inbound('ORD-001', 'Shirt', 1, 0.3)
        req = agent.request_consolidation([item.item_id], 'KR')
        assert req.request_id.startswith('MT-CON-')
        assert req.status == 'pending'

    def test_request_outbound(self):
        agent = MoltailAgent()
        item = agent.confirm_inbound('ORD-001', 'Bag', 1, 1.0)
        req = agent.request_outbound([item.item_id], 'KR', '홍길동', '서울시 강남구')
        assert req.tracking_number.startswith('MT')
        assert req.status == 'processing'

    def test_get_status(self):
        agent = MoltailAgent()
        agent.confirm_inbound('ORD-001', 'Item', 1, 0.5)
        status = agent.get_status()
        assert status['status'] == 'operational'
        assert status['inbound_count'] == 1

    def test_list_items(self):
        agent = MoltailAgent()
        agent.confirm_inbound('ORD-001', 'Item', 1, 0.5)
        agent.confirm_inbound('ORD-002', 'Item2', 2, 1.0)
        assert len(agent.list_items()) == 2


# ---------------------------------------------------------------------------
# OhmyzipAgent
# ---------------------------------------------------------------------------

class TestOhmyzipAgent:
    def test_confirm_inbound(self):
        agent = OhmyzipAgent()
        item = agent.confirm_inbound('ORD-001', 'Phone', 1, 0.3)
        assert item.item_id.startswith('OMZ-')
        assert item.agent_id == 'ohmyzip'

    def test_request_outbound(self):
        agent = OhmyzipAgent()
        item = agent.confirm_inbound('ORD-001', 'Laptop', 1, 2.0)
        req = agent.request_outbound([item.item_id], 'KR', 'Test User', 'Test Address')
        assert req.tracking_number.startswith('OMZ')

    def test_get_status(self):
        agent = OhmyzipAgent()
        status = agent.get_status()
        assert status['agent_id'] == 'ohmyzip'
        assert status['status'] == 'operational'


# ---------------------------------------------------------------------------
# ShippingInsurance
# ---------------------------------------------------------------------------

class TestShippingInsurance:
    def test_calculate_basic(self):
        ins = ShippingInsurance()
        quote = ins.calculate(100000.0, 'US')
        assert quote.total_premium_krw >= 3000.0  # minimum
        assert quote.coverage_krw == 100000.0

    def test_minimum_premium(self):
        ins = ShippingInsurance()
        quote = ins.calculate(1000.0, 'US')  # 1000 * 2% = 20 < 3000
        assert quote.total_premium_krw >= 3000.0

    def test_high_risk_country_premium(self):
        ins = ShippingInsurance()
        low_risk_quote = ins.calculate(1000000.0, 'US')
        med_risk_quote = ins.calculate(1000000.0, 'CN')
        assert med_risk_quote.total_premium_krw > low_risk_quote.total_premium_krw

    def test_risk_level(self):
        ins = ShippingInsurance()
        assert ins.risk_level('US') == 'LOW'
        assert ins.risk_level('CN') == 'MEDIUM'
        assert ins.risk_level('XX') == 'MEDIUM'  # default

    def test_to_dict(self):
        ins = ShippingInsurance()
        quote = ins.calculate(500000.0, 'JP')
        d = quote.to_dict()
        assert 'total_premium_krw' in d
        assert 'coverage_krw' in d
        assert 'risk_level' in d


# ---------------------------------------------------------------------------
# CustomsClearanceTracker
# ---------------------------------------------------------------------------

class TestCustomsClearanceTracker:
    def test_add_and_get_event(self):
        tracker = CustomsClearanceTracker()
        event = tracker.add_event('ORD-001', 'arrived', '세관 도착')
        assert event['event_type'] == 'arrived'
        history = tracker.get_history('ORD-001')
        assert len(history) == 1

    def test_get_latest(self):
        tracker = CustomsClearanceTracker()
        tracker.add_event('ORD-001', 'arrived')
        tracker.add_event('ORD-001', 'cleared')
        latest = tracker.get_latest('ORD-001')
        assert latest['event_type'] == 'cleared'

    def test_get_history_empty(self):
        tracker = CustomsClearanceTracker()
        assert tracker.get_history('NONEXISTENT') == []

    def test_get_latest_none_when_empty(self):
        tracker = CustomsClearanceTracker()
        assert tracker.get_latest('NONEXISTENT') is None
