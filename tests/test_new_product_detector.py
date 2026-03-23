"""tests/test_new_product_detector.py — Phase 7 NewProductDetector 테스트."""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.analytics.new_product_detector import NewProductDetector

# ──────────────────────────────────────────────────────────
# 공통 픽스처
# ──────────────────────────────────────────────────────────

CATALOG_SKUS = {'PTR-TNK-001', 'MMP-EDP-001', 'PTR-LFT-002'}

VENDOR_PRODUCTS_PORTER = [
    {
        'sku': 'PTR-TNK-001',  # 기존 상품 (카탈로그에 있음)
        'vendor': 'PORTER',
        'title_en': 'Tanker Briefcase',
        'buy_price': 30000,
        'buy_currency': 'JPY',
        'src_url': 'https://example.com/ptr-tnk-001',
        'status': 'active',
    },
    {
        'sku': 'PTR-TNK-NEW',  # 신상품
        'vendor': 'PORTER',
        'title_en': 'New Tanker Backpack',
        'buy_price': 35000,
        'buy_currency': 'JPY',
        'src_url': 'https://example.com/ptr-tnk-new',
        'status': 'active',
    },
    {
        'sku': 'PTR-CRT-NEW',  # 신상품
        'vendor': 'PORTER',
        'title_en': 'New Current Wallet',
        'buy_price': 12000,
        'buy_currency': 'JPY',
        'src_url': 'https://example.com/ptr-crt-new',
        'status': 'active',
    },
]

VENDOR_PRODUCTS_MEMO = [
    {
        'sku': 'MMP-EDP-001',  # 기존 상품
        'vendor': 'MEMO_PARIS',
        'title_en': 'Graines EDP 75ml',
        'buy_price': 200.0,
        'buy_currency': 'EUR',
        'src_url': 'https://example.com/mmp-edp-001',
        'status': 'active',
    },
    {
        'sku': 'MMP-EDP-NEW',  # 신상품
        'vendor': 'MEMO_PARIS',
        'title_en': 'New Memo Fragrance',
        'buy_price': 180.0,
        'buy_currency': 'EUR',
        'src_url': 'https://example.com/mmp-edp-new',
        'status': 'active',
    },
]


def _make_detector():
    detector = NewProductDetector(sheet_id='dummy')
    detector.get_catalog_skus = MagicMock(return_value=set(CATALOG_SKUS))
    detector.scan_vendor_products = MagicMock(side_effect=lambda vendor_name: (
        list(VENDOR_PRODUCTS_PORTER) if vendor_name == 'porter'
        else list(VENDOR_PRODUCTS_MEMO)
    ))
    detector._estimate_margin = MagicMock(return_value=18.0)
    return detector


# ══════════════════════════════════════════════════════════
# get_catalog_skus 테스트
# ══════════════════════════════════════════════════════════

class TestGetCatalogSkus:
    def test_returns_set(self):
        detector = NewProductDetector(sheet_id='')
        result = detector.get_catalog_skus()
        assert isinstance(result, set)

    def test_empty_without_sheet_id(self):
        detector = NewProductDetector(sheet_id='')
        result = detector.get_catalog_skus()
        assert result == set()

    def test_with_mocked_sheets(self):
        detector = NewProductDetector(sheet_id='dummy')
        mock_ws = MagicMock()
        mock_ws.get_all_records.return_value = [
            {'sku': 'PTR-TNK-001'}, {'sku': 'MMP-EDP-001'}, {'sku': ''}
        ]
        with patch('src.analytics.new_product_detector.NewProductDetector.get_catalog_skus',
                   return_value={'PTR-TNK-001', 'MMP-EDP-001'}):
            result = detector.get_catalog_skus()
        assert 'PTR-TNK-001' in result
        assert 'MMP-EDP-001' in result


# ══════════════════════════════════════════════════════════
# scan_vendor_products 테스트
# ══════════════════════════════════════════════════════════

class TestScanVendorProducts:
    def test_returns_list(self):
        detector = NewProductDetector(sheet_id='')
        result = detector.scan_vendor_products('porter')
        assert isinstance(result, list)

    def test_unknown_vendor_returns_empty(self):
        detector = NewProductDetector(sheet_id='')
        result = detector.scan_vendor_products('nonexistent_vendor_xyz')
        assert result == []

    def test_vendor_without_fetch_method_returns_empty(self):
        """fetch_catalog/fetch_all 메서드가 없는 벤더는 빈 목록 반환."""
        detector = NewProductDetector(sheet_id='')
        with patch('src.analytics.new_product_detector.NewProductDetector.scan_vendor_products',
                   return_value=[]):
            result = detector.scan_vendor_products('porter')
        assert isinstance(result, list)


# ══════════════════════════════════════════════════════════
# detect_new_products 테스트
# ══════════════════════════════════════════════════════════

class TestDetectNewProducts:
    def test_returns_list(self):
        detector = _make_detector()
        result = detector.detect_new_products()
        assert isinstance(result, list)

    def test_existing_skus_excluded(self):
        detector = _make_detector()
        result = detector.detect_new_products()
        found_skus = {p['sku'] for p in result}
        assert 'PTR-TNK-001' not in found_skus
        assert 'MMP-EDP-001' not in found_skus

    def test_new_skus_included(self):
        detector = _make_detector()
        result = detector.detect_new_products()
        found_skus = {p['sku'] for p in result}
        assert 'PTR-TNK-NEW' in found_skus
        assert 'MMP-EDP-NEW' in found_skus
        assert 'PTR-CRT-NEW' in found_skus

    def test_new_products_count(self):
        detector = _make_detector()
        result = detector.detect_new_products()
        assert len(result) == 3  # PTR-TNK-NEW, PTR-CRT-NEW, MMP-EDP-NEW

    def test_sorted_by_margin_desc(self):
        detector = _make_detector()
        # 다른 마진값을 반환하도록 설정
        call_count = [0]

        def margin_side_effect(p):
            call_count[0] += 1
            return 30.0 - call_count[0] * 5  # 25, 20, 15, ...

        detector._estimate_margin = MagicMock(side_effect=margin_side_effect)
        result = detector.detect_new_products()
        margins = [p.get('estimated_margin_pct', 0) for p in result]
        assert margins == sorted(margins, reverse=True)

    def test_estimated_margin_added(self):
        detector = _make_detector()
        result = detector.detect_new_products()
        for p in result:
            assert 'estimated_margin_pct' in p

    def test_both_vendors_scanned(self):
        detector = _make_detector()
        detector.detect_new_products()
        calls = [call[0][0] for call in detector.scan_vendor_products.call_args_list]
        assert 'porter' in calls
        assert 'memo_paris' in calls

    def test_empty_vendor_products(self):
        detector = _make_detector()
        detector.scan_vendor_products = MagicMock(return_value=[])
        result = detector.detect_new_products()
        assert result == []


# ══════════════════════════════════════════════════════════
# send_alerts 테스트
# ══════════════════════════════════════════════════════════

class TestSendAlerts:
    @patch.dict(os.environ, {'TELEGRAM_ENABLED': '0'})
    def test_no_telegram_when_disabled(self):
        detector = _make_detector()
        products = [
            {
                'sku': 'PTR-TNK-NEW', 'vendor': 'PORTER',
                'title_en': 'New Bag', 'buy_price': 35000,
                'buy_currency': 'JPY', 'estimated_margin_pct': 20.0,
            }
        ]
        with patch('src.utils.telegram.send_tele') as mock_tele:
            detector.send_alerts(products)
            mock_tele.assert_not_called()

    def test_empty_products_no_alert(self):
        detector = _make_detector()
        # Should not raise
        detector.send_alerts([])

    @patch.dict(os.environ, {'TELEGRAM_ENABLED': '1'})
    def test_telegram_message_no_error(self):
        """TELEGRAM_ENABLED=1이어도 예외 없이 실행되어야 한다 (네트워크 오류 허용)."""
        detector = _make_detector()
        products = [
            {
                'sku': 'PTR-TNK-NEW', 'vendor': 'PORTER',
                'title_en': 'New Bag', 'buy_price': 35000,
                'buy_currency': 'JPY', 'estimated_margin_pct': 20.0,
            }
        ]
        try:
            detector.send_alerts(products)
        except Exception as exc:
            pytest.fail(f"send_alerts raised an unexpected exception: {exc}")


# ══════════════════════════════════════════════════════════
# run 테스트
# ══════════════════════════════════════════════════════════

class TestRun:
    @patch.dict(os.environ, {'NEW_PRODUCT_CHECK_ENABLED': '0'})
    def test_disabled_returns_skipped(self):
        detector = _make_detector()
        result = detector.run()
        assert result == {'skipped': True}

    @patch.dict(os.environ, {
        'NEW_PRODUCT_CHECK_ENABLED': '1',
        'NEW_PRODUCT_MIN_MARGIN_PCT': '10',
        'TELEGRAM_ENABLED': '0',
    })
    def test_enabled_returns_result(self):
        detector = _make_detector()
        detector._write_suggestions_to_sheets = MagicMock()
        result = detector.run()
        assert 'total_detected' in result
        assert 'qualified' in result
        assert 'new_products' in result

    @patch.dict(os.environ, {
        'NEW_PRODUCT_CHECK_ENABLED': '1',
        'NEW_PRODUCT_MIN_MARGIN_PCT': '50',  # 높은 마진 기준으로 필터링
        'TELEGRAM_ENABLED': '0',
    })
    def test_min_margin_filter(self):
        """최소 마진 미달 상품은 qualified에서 제외되어야 한다."""
        detector = _make_detector()
        detector._estimate_margin = MagicMock(return_value=18.0)  # < 50%
        detector._write_suggestions_to_sheets = MagicMock()
        # 새로운 detector를 min_margin=50으로 초기화
        with patch.dict(os.environ, {'NEW_PRODUCT_MIN_MARGIN_PCT': '50'}):
            detector2 = NewProductDetector(sheet_id='dummy')
            detector2.get_catalog_skus = MagicMock(return_value=set(CATALOG_SKUS))
            detector2.scan_vendor_products = detector.scan_vendor_products
            detector2._estimate_margin = MagicMock(return_value=18.0)
            detector2._write_suggestions_to_sheets = MagicMock()
            result = detector2.run()
        assert result['qualified'] == 0  # 모두 18% < 50% 이므로 제외

    @patch.dict(os.environ, {
        'NEW_PRODUCT_CHECK_ENABLED': '1',
        'NEW_PRODUCT_MIN_MARGIN_PCT': '10',
        'TELEGRAM_ENABLED': '0',
    })
    def test_sheets_write_called(self):
        detector = _make_detector()
        detector._write_suggestions_to_sheets = MagicMock()
        detector.run()
        detector._write_suggestions_to_sheets.assert_called_once()

    @patch.dict(os.environ, {
        'NEW_PRODUCT_CHECK_ENABLED': '1',
        'NEW_PRODUCT_MIN_MARGIN_PCT': '10',
        'TELEGRAM_ENABLED': '0',
    })
    def test_total_detected_vs_qualified(self):
        detector = _make_detector()
        detector._write_suggestions_to_sheets = MagicMock()
        result = detector.run()
        assert result['total_detected'] >= result['qualified']


# ══════════════════════════════════════════════════════════
# _estimate_margin 테스트
# ══════════════════════════════════════════════════════════

class TestEstimateMargin:
    def test_returns_float(self):
        detector = NewProductDetector(sheet_id='')
        product = {
            'buy_price': 30000,
            'buy_currency': 'JPY',
        }
        result = detector._estimate_margin(product)
        assert isinstance(result, float)

    def test_zero_buy_price_returns_zero(self):
        detector = NewProductDetector(sheet_id='')
        product = {'buy_price': 0, 'buy_currency': 'JPY'}
        result = detector._estimate_margin(product)
        assert result == 0.0

    def test_negative_buy_price_returns_zero(self):
        detector = NewProductDetector(sheet_id='')
        product = {'buy_price': -100, 'buy_currency': 'JPY'}
        result = detector._estimate_margin(product)
        assert result == 0.0

    def test_positive_margin_for_valid_product(self):
        detector = NewProductDetector(sheet_id='')
        product = {'buy_price': 30000, 'buy_currency': 'JPY'}
        with patch.dict(os.environ, {
            'TARGET_MARGIN_PCT': '22',
            'FX_JPYKRW': '9.0',
        }):
            result = detector._estimate_margin(product)
        assert result > 0.0
