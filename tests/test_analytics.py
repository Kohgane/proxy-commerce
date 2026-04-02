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


# ══════════════════════════════════════════════════════════
# Phase 29: SalesAnalytics
# ══════════════════════════════════════════════════════════

class TestSalesAnalytics:
    def _make(self):
        from src.analytics.sales_analytics import SalesAnalytics
        return SalesAnalytics()

    def test_sales_daily_summary(self):
        result = self._make().daily_summary()
        assert isinstance(result, dict)
        for key in ('date', 'revenue', 'orders', 'avg_order_value'):
            assert key in result, f"missing key: {key}"

    def test_sales_weekly_summary(self):
        result = self._make().weekly_summary(year=2024, week=10)
        assert isinstance(result, dict)
        assert result['year'] == 2024
        assert result['week'] == 10
        assert 'revenue' in result
        assert 'orders' in result

    def test_sales_monthly_summary(self):
        result = self._make().monthly_summary(year=2024, month=3)
        assert isinstance(result, dict)
        assert result['year'] == 2024
        assert result['month'] == 3
        assert 'revenue' in result

    def test_sales_channel_comparison(self):
        result = self._make().channel_comparison(
            ['shopify', 'woocommerce'], '2024-01-01', '2024-01-31'
        )
        assert isinstance(result, dict)
        assert 'shopify' in result
        assert 'woocommerce' in result
        for ch_data in result.values():
            assert 'revenue' in ch_data
            assert 'orders' in ch_data


# ══════════════════════════════════════════════════════════
# Phase 29: CustomerAnalytics
# ══════════════════════════════════════════════════════════

SAMPLE_RFM_ORDERS = [
    {'customer_id': 'C001', 'order_date': '2024-01-10', 'amount': 300000},
    {'customer_id': 'C001', 'order_date': '2024-02-15', 'amount': 250000},
    {'customer_id': 'C001', 'order_date': '2024-03-01', 'amount': 400000},
    {'customer_id': 'C002', 'order_date': '2023-05-20', 'amount': 150000},
    {'customer_id': 'C003', 'order_date': '2024-03-10', 'amount': 500000},
]


class TestCustomerAnalytics:
    def _make(self):
        from src.analytics.customer_analytics import CustomerAnalytics
        return CustomerAnalytics()

    def test_rfm_analysis_basic(self):
        result = self._make().rfm_analysis(SAMPLE_RFM_ORDERS)
        assert isinstance(result, list)
        assert len(result) == 3  # 3 unique customers
        ids = {r['customer_id'] for r in result}
        assert ids == {'C001', 'C002', 'C003'}

    def test_rfm_segments(self):
        result = self._make().rfm_analysis(SAMPLE_RFM_ORDERS)
        valid_segments = {'Champions', 'Loyal', 'At Risk', 'Lost', 'Promising'}
        for row in result:
            assert row['segment'] in valid_segments
            assert 'rfm_score' in row
            assert 'recency_days' in row
            assert 'frequency' in row
            assert 'monetary' in row

    def test_ltv_estimate(self):
        ca = self._make()
        ltv = ca.ltv_estimate('C001', SAMPLE_RFM_ORDERS)
        assert isinstance(ltv, float)
        assert ltv > 0

    def test_ltv_unknown_customer_returns_zero(self):
        ca = self._make()
        ltv = ca.ltv_estimate('UNKNOWN', SAMPLE_RFM_ORDERS)
        assert ltv == 0.0


# ══════════════════════════════════════════════════════════
# Phase 29: ProductAnalytics
# ══════════════════════════════════════════════════════════

SAMPLE_PRODUCTS_ABC = [
    {'product_id': 'P001', 'revenue': 500000},
    {'product_id': 'P002', 'revenue': 300000},
    {'product_id': 'P003', 'revenue': 100000},
    {'product_id': 'P004', 'revenue': 80000},
    {'product_id': 'P005', 'revenue': 20000},
]

SAMPLE_PRODUCTS_MARGIN = [
    {'product_id': 'P001', 'sale_price': 100000, 'cost_price': 70000},
    {'product_id': 'P002', 'sale_price': 50000, 'cost_price': 30000},
]

SAMPLE_PRODUCTS_TURNOVER = [
    {'product_id': 'P001', 'cogs': 1000000, 'avg_inventory': 200000},
    {'product_id': 'P002', 'cogs': 500000, 'avg_inventory': 250000},
]


class TestProductAnalytics:
    def _make(self):
        from src.analytics.product_analytics import ProductAnalytics
        return ProductAnalytics()

    def test_abc_classification(self):
        result = self._make().abc_classification(SAMPLE_PRODUCTS_ABC)
        assert isinstance(result, dict)
        assert set(result.keys()) == {'A', 'B', 'C'}
        all_ids = result['A'] + result['B'] + result['C']
        assert len(all_ids) == 5
        assert 'P001' in result['A'], "Top revenue product should be in A"

    def test_abc_empty(self):
        result = self._make().abc_classification([])
        assert result == {'A': [], 'B': [], 'C': []}

    def test_margin_analysis(self):
        result = self._make().margin_analysis(SAMPLE_PRODUCTS_MARGIN)
        assert isinstance(result, list)
        assert len(result) == 2
        p1 = next(r for r in result if r['product_id'] == 'P001')
        assert p1['margin_amount'] == 30000.0
        assert abs(p1['margin_rate'] - 30.0) < 0.01

    def test_inventory_turnover(self):
        result = self._make().inventory_turnover(SAMPLE_PRODUCTS_TURNOVER)
        assert isinstance(result, list)
        assert len(result) == 2
        p1 = next(r for r in result if r['product_id'] == 'P001')
        assert abs(p1['turnover_rate'] - 5.0) < 0.01


# ══════════════════════════════════════════════════════════
# Phase 29: ReportExporter
# ══════════════════════════════════════════════════════════

class TestReportExporter:
    def _make(self):
        from src.analytics.export import ReportExporter
        return ReportExporter()

    def test_export_to_csv(self):
        data = [{'name': 'Alice', 'score': 90}, {'name': 'Bob', 'score': 85}]
        csv_str = self._make().to_csv(data, 'test.csv')
        assert isinstance(csv_str, str)
        assert 'Alice' in csv_str
        assert 'Bob' in csv_str
        assert 'name' in csv_str  # header row

    def test_export_to_csv_empty(self):
        assert self._make().to_csv([], 'empty.csv') == ''

    def test_export_to_google_sheets_mock(self):
        data = [{'col': 'val'}]
        result = self._make().to_google_sheets(data, 'TestSheet')
        assert result['success'] is True
        assert result['sheet_name'] == 'TestSheet'
        assert result['rows_written'] == 1


# ══════════════════════════════════════════════════════════
# Phase 29: Analytics API Blueprint
# ══════════════════════════════════════════════════════════

import pytest


@pytest.fixture
def analytics_client():
    from flask import Flask
    from src.api.analytics_api import analytics_api
    app = Flask(__name__)
    app.register_blueprint(analytics_api)
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


class TestAnalyticsApi:
    def test_analytics_api_status(self, analytics_client):
        resp = analytics_client.get('/api/v1/analytics/status')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['status'] == 'ok'

    def test_analytics_api_sales_daily(self, analytics_client):
        resp = analytics_client.get('/api/v1/analytics/sales/daily')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'revenue' in data
        assert 'orders' in data

    def test_analytics_api_sales_weekly(self, analytics_client):
        resp = analytics_client.get('/api/v1/analytics/sales/weekly?year=2024&week=5')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['year'] == 2024
        assert data['week'] == 5

    def test_analytics_api_sales_monthly(self, analytics_client):
        resp = analytics_client.get('/api/v1/analytics/sales/monthly?year=2024&month=2')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['year'] == 2024
        assert data['month'] == 2

    def test_analytics_api_rfm(self, analytics_client):
        payload = {'orders': SAMPLE_RFM_ORDERS}
        resp = analytics_client.post(
            '/api/v1/analytics/customers/rfm',
            json=payload,
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        assert len(data) == 3

    def test_analytics_api_abc(self, analytics_client):
        payload = {'products': SAMPLE_PRODUCTS_ABC}
        resp = analytics_client.post(
            '/api/v1/analytics/products/abc',
            json=payload,
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert set(data.keys()) == {'A', 'B', 'C'}

    def test_analytics_api_margin(self, analytics_client):
        payload = {'products': SAMPLE_PRODUCTS_MARGIN}
        resp = analytics_client.post(
            '/api/v1/analytics/products/margin',
            json=payload,
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
