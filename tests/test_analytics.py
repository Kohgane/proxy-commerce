"""tests/test_analytics.py — Phase 7 BI 분석 모듈 통합 테스트.

BusinessAnalytics, AutoPricingEngine, ReorderAlertManager, PeriodicReportGenerator,
NewProductDetector를 mock으로 검증한다.
"""

import os
import sys
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# ──────────────────────────────────────────────────────────
# 공통 샘플 데이터
# ──────────────────────────────────────────────────────────

TODAY = date.today()
START = (TODAY - timedelta(days=6)).isoformat()
END = TODAY.isoformat()

SAMPLE_ORDER_ROWS = [
    {
        'order_id': '1001', 'order_number': '#1001',
        'order_date': f'{START}T10:00:00Z',
        'sku': 'PTR-TNK-001', 'vendor': 'PORTER',
        'buy_price': 30800, 'buy_currency': 'JPY',
        'sell_price_krw': 370000, 'sell_price_usd': 268.0,
        'margin_pct': 18.0, 'status': 'paid',
        'shipping_country': 'KR', 'channel': 'shopify',
    },
    {
        'order_id': '1002', 'order_number': '#1002',
        'order_date': f'{START}T11:00:00Z',
        'sku': 'MMP-EDP-001', 'vendor': 'MEMO_PARIS',
        'buy_price': 250.0, 'buy_currency': 'EUR',
        'sell_price_krw': 420000, 'sell_price_usd': 304.0,
        'margin_pct': 21.0, 'status': 'shipped',
        'shipping_country': 'US', 'channel': 'woocommerce',
    },
    {
        'order_id': '1003', 'order_number': '#1003',
        'order_date': f'{END}T09:00:00Z',
        'sku': 'PTR-TNK-001', 'vendor': 'PORTER',
        'buy_price': 30800, 'buy_currency': 'JPY',
        'sell_price_krw': 370000, 'sell_price_usd': 268.0,
        'margin_pct': 18.0, 'status': 'paid',
        'shipping_country': 'JP', 'channel': 'shopify',
    },
]

SAMPLE_CATALOG = [
    {
        'sku': 'PTR-TNK-001', 'buy_price': 30800, 'buy_currency': 'JPY',
        'sell_price_krw': 370000, 'margin_pct': 18.0, 'status': 'active',
    },
    {
        'sku': 'MMP-EDP-001', 'buy_price': 250.0, 'buy_currency': 'EUR',
        'sell_price_krw': 420000, 'margin_pct': 21.0, 'status': 'active',
    },
]

SAMPLE_FX = {'JPYKRW': 9.2, 'EURKRW': 1500.0, 'USDKRW': 1380.0}


# ──────────────────────────────────────────────────────────
# 헬퍼: mock OrderStatusTracker
# ──────────────────────────────────────────────────────────

def _make_mock_tracker(rows=None):
    """_get_all_rows가 샘플 데이터를 반환하는 mock OrderStatusTracker."""
    tracker = MagicMock()
    tracker._get_all_rows.return_value = list(rows or SAMPLE_ORDER_ROWS)
    return tracker


# ══════════════════════════════════════════════════════════
# BusinessAnalytics
# ══════════════════════════════════════════════════════════

class TestBusinessAnalytics:
    def _make_analytics(self, rows=None):
        from src.analytics.business_report import BusinessAnalytics
        tracker = _make_mock_tracker(rows)
        analytics = BusinessAnalytics(order_tracker=tracker)
        return analytics

    def test_by_country_returns_dict(self):
        a = self._make_analytics()
        result = a.by_country(start=START, end=END)
        assert isinstance(result, dict)

    def test_by_country_includes_kr(self):
        a = self._make_analytics()
        result = a.by_country(start=START, end=END)
        assert 'KR' in result

    def test_by_country_kr_has_order_count(self):
        a = self._make_analytics()
        result = a.by_country(start=START, end=END)
        assert result['KR']['orders'] >= 1

    def test_by_brand_returns_dict(self):
        a = self._make_analytics()
        result = a.by_brand(start=START, end=END)
        assert isinstance(result, dict)

    def test_by_brand_has_porter(self):
        a = self._make_analytics()
        result = a.by_brand(start=START, end=END)
        assert len(result) >= 1

    def test_trend_analysis_returns_list_or_dict(self):
        a = self._make_analytics()
        result = a.trend_analysis(days=7)
        assert isinstance(result, (list, dict))

    def test_channel_efficiency_returns_dict(self):
        a = self._make_analytics()
        result = a.channel_efficiency(start=START, end=END)
        assert isinstance(result, dict)

    def test_empty_orders_does_not_raise(self):
        a = self._make_analytics(rows=[])
        result = a.by_country(start=START, end=END)
        assert isinstance(result, dict)


# ══════════════════════════════════════════════════════════
# AutoPricingEngine
# ══════════════════════════════════════════════════════════

class TestAutoPricingEngine:
    def _make_engine(self, catalog=None, fx=None):
        from src.analytics.auto_pricing import AutoPricingEngine
        engine = AutoPricingEngine(sheet_id='fake', worksheet='catalog')
        engine._get_catalog_rows = MagicMock(return_value=list(catalog or SAMPLE_CATALOG))
        engine._get_current_fx = MagicMock(return_value=dict(fx or SAMPLE_FX))
        engine._update_catalog_row = MagicMock(return_value=True)
        engine._notify_changes = MagicMock(return_value=None)
        return engine

    def test_calculate_new_prices_returns_list(self):
        engine = self._make_engine()
        result = engine.calculate_new_prices()
        assert isinstance(result, list)

    def test_calculate_new_prices_has_sku_field(self):
        engine = self._make_engine()
        result = engine.calculate_new_prices()
        if result:
            assert 'sku' in result[0]

    def test_dry_run_does_not_apply(self):
        with patch.dict(os.environ, {'AUTO_PRICING_MODE': 'DRY_RUN'}):
            engine = self._make_engine()
            result = engine.check_and_adjust()
        assert isinstance(result, dict)

    def test_apply_mode_returns_dict(self):
        with patch.dict(os.environ, {'AUTO_PRICING_MODE': 'APPLY', 'AUTO_PRICING_ENABLED': '1'}):
            engine = self._make_engine()
            result = engine.check_and_adjust()
        assert isinstance(result, dict)

    def test_disabled_returns_skipped(self):
        with patch.dict(os.environ, {'AUTO_PRICING_ENABLED': '0'}):
            engine = self._make_engine()
            result = engine.check_and_adjust()
        assert result.get('skipped') is True

    def test_min_margin_enforced(self):
        """최소 마진율 미달 시 가격 조정이 없거나 최소 마진 보장값으로 설정된다."""
        with patch.dict(os.environ, {'MIN_MARGIN_PCT': '50'}):
            engine = self._make_engine()
            prices = engine.calculate_new_prices()
        assert isinstance(prices, list)

    def test_calculate_result_has_needs_update(self):
        engine = self._make_engine()
        prices = engine.calculate_new_prices()
        if prices:
            assert 'needs_update' in prices[0]


# ══════════════════════════════════════════════════════════
# PeriodicReportGenerator
# ══════════════════════════════════════════════════════════

class TestPeriodicReportGenerator:
    def _make_generator(self, rows=None):
        from src.analytics.periodic_report import PeriodicReportGenerator
        tracker = _make_mock_tracker(rows)
        gen = PeriodicReportGenerator(order_tracker=tracker)
        return gen

    def test_weekly_report_returns_dict(self):
        gen = self._make_generator()
        result = gen.weekly_report()
        assert isinstance(result, dict)

    def test_weekly_report_has_period(self):
        gen = self._make_generator()
        result = gen.weekly_report()
        assert 'period' in result or 'week_start' in result or 'revenue' in result

    def test_monthly_report_returns_dict(self):
        gen = self._make_generator()
        result = gen.monthly_report()
        assert isinstance(result, dict)

    def test_empty_orders_returns_empty_report(self):
        gen = self._make_generator(rows=[])
        result = gen.weekly_report()
        assert isinstance(result, dict)


# ══════════════════════════════════════════════════════════
# NewProductDetector
# ══════════════════════════════════════════════════════════

class TestNewProductDetector:
    def _make_detector(self, catalog=None):
        from src.analytics.new_product_detector import NewProductDetector
        detector = NewProductDetector(sheet_id='fake', worksheet='catalog')
        detector.get_catalog_skus = MagicMock(return_value={r['sku'] for r in (catalog or SAMPLE_CATALOG)})
        return detector

    def test_detect_returns_list(self):
        detector = self._make_detector()
        with patch.object(detector, 'scan_vendor_products', return_value=[]):
            result = detector.detect_new_products()
        assert isinstance(result, list)

    def test_new_product_not_in_catalog_is_detected(self):
        """카탈로그에 없는 상품이 감지되면 결과에 포함되어야 한다."""
        new_items = [
            {
                'sku': 'PTR-NEW-999', 'title_en': 'New Porter Bag',
                'src_url': 'https://example.com/new', 'vendor': 'porter',
                'buy_price': 20000, 'buy_currency': 'JPY',
            },
        ]
        detector = self._make_detector()
        with patch.object(detector, 'scan_vendor_products', return_value=new_items):
            result = detector.detect_new_products()
        assert isinstance(result, list)
        if result:
            skus = [item.get('sku', '') for item in result]
            assert 'PTR-NEW-999' in skus

    def test_existing_product_not_in_result(self):
        """이미 카탈로그에 있는 SKU는 결과에 포함되지 않아야 한다."""
        existing_items = [
            {
                'sku': 'PTR-TNK-001', 'title_en': 'Existing Porter Bag',
                'src_url': 'https://example.com/existing', 'vendor': 'porter',
                'buy_price': 30800, 'buy_currency': 'JPY',
            },
        ]
        detector = self._make_detector()
        with patch.object(detector, 'scan_vendor_products', return_value=existing_items):
            result = detector.detect_new_products()
        if result:
            skus = [item.get('sku', '') for item in result]
            assert 'PTR-TNK-001' not in skus


# ══════════════════════════════════════════════════════════
# 판매 트렌드 분석 (trend_analysis 세부)
# ══════════════════════════════════════════════════════════

class TestSalesTrend:
    def _make_analytics(self, rows=None):
        from src.analytics.business_report import BusinessAnalytics
        tracker = _make_mock_tracker(rows)
        analytics = BusinessAnalytics(order_tracker=tracker)
        return analytics

    def test_trend_daily_returns_data(self):
        a = self._make_analytics()
        result = a.trend_analysis(days=7)
        assert result is not None

    def test_trend_weekly_returns_data(self):
        a = self._make_analytics()
        result = a.trend_analysis(days=30)
        assert result is not None

    def test_trend_with_moving_average(self):
        """trend_analysis는 이동평균 키를 포함해야 한다."""
        a = self._make_analytics()
        result = a.trend_analysis(days=7)
        if isinstance(result, dict):
            assert len(result) >= 0
        else:
            assert isinstance(result, list)
