"""tests/test_business_report.py — Phase 7 BusinessAnalytics 테스트."""

import os
import sys
from datetime import date, timedelta
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.analytics.business_report import BusinessAnalytics  # noqa: E402

# ──────────────────────────────────────────────────────────
# 공통 픽스처
# ──────────────────────────────────────────────────────────

TODAY = str(date.today())
YESTERDAY = str(date.today() - timedelta(days=1))
WEEK_AGO = str(date.today() - timedelta(days=7))

SAMPLE_ROWS = [
    {
        'order_id': '1', 'order_number': '#1001',
        'order_date': TODAY,
        'sku': 'PTR-TNK-001', 'vendor': 'PORTER',
        'buy_price': 30000, 'buy_currency': 'JPY',
        'sell_price_krw': 360000, 'sell_price_usd': 267.0,
        'margin_pct': 20.0, 'status': 'delivered',
        'shipping_country': 'KR', 'destination_country': 'KR',
        'channel': 'shopify',
    },
    {
        'order_id': '2', 'order_number': '#1002',
        'order_date': TODAY,
        'sku': 'MMP-EDP-001', 'vendor': 'MEMO_PARIS',
        'buy_price': 200.0, 'buy_currency': 'EUR',
        'sell_price_krw': 450000, 'sell_price_usd': 333.0,
        'margin_pct': 25.0, 'status': 'delivered',
        'shipping_country': 'US', 'destination_country': 'US',
        'channel': 'shopify',
    },
    {
        'order_id': '3', 'order_number': '#1003',
        'order_date': YESTERDAY,
        'sku': 'PTR-TNK-002', 'vendor': 'PORTER',
        'buy_price': 25000, 'buy_currency': 'JPY',
        'sell_price_krw': 300000, 'sell_price_usd': 0,
        'margin_pct': 18.0, 'status': 'delivered',
        'shipping_country': 'KR', 'destination_country': 'KR',
        'channel': 'woocommerce',
    },
]


def _make_analytics(rows=None):
    analytics = BusinessAnalytics.__new__(BusinessAnalytics)
    mock_tracker = MagicMock()
    mock_tracker._get_all_rows.return_value = list(rows if rows is not None else SAMPLE_ROWS)
    analytics._tracker = mock_tracker
    return analytics


# ══════════════════════════════════════════════════════════
# by_country 테스트
# ══════════════════════════════════════════════════════════

class TestByCountry:
    def test_returns_dict(self):
        analytics = _make_analytics()
        result = analytics.by_country()
        assert isinstance(result, dict)

    def test_country_keys_uppercase(self):
        analytics = _make_analytics()
        result = analytics.by_country()
        for key in result:
            assert key == key.upper()

    def test_kr_and_us_countries_present(self):
        analytics = _make_analytics()
        result = analytics.by_country()
        assert 'KR' in result
        assert 'US' in result

    def test_country_structure(self):
        analytics = _make_analytics()
        result = analytics.by_country()
        for country, data in result.items():
            assert 'orders' in data
            assert 'revenue_krw' in data
            assert 'margin_pct' in data
            assert 'aov_krw' in data

    def test_kr_order_count(self):
        analytics = _make_analytics()
        result = analytics.by_country()
        assert result['KR']['orders'] == 2  # #1001 + #1003

    def test_aov_calculation(self):
        analytics = _make_analytics()
        result = analytics.by_country()
        # KR: (360000 + 300000) / 2 = 330000
        assert result['KR']['aov_krw'] == 330000

    def test_unknown_country_fallback(self):
        rows = [dict(r) for r in SAMPLE_ROWS]
        rows[0].pop('shipping_country', None)
        rows[0].pop('destination_country', None)
        analytics = _make_analytics(rows)
        result = analytics.by_country()
        assert 'UNKNOWN' in result

    def test_date_range_filter(self):
        analytics = _make_analytics()
        # 오늘 날짜만 필터링
        result = analytics.by_country(start=TODAY, end=str(date.today() + timedelta(days=1)))
        # US는 오늘 주문만 있음
        assert 'US' in result
        assert result['US']['orders'] == 1


# ══════════════════════════════════════════════════════════
# by_brand 테스트
# ══════════════════════════════════════════════════════════

class TestByBrand:
    def test_returns_dict(self):
        analytics = _make_analytics()
        result = analytics.by_brand()
        assert isinstance(result, dict)

    def test_porter_and_memo_paris_present(self):
        analytics = _make_analytics()
        result = analytics.by_brand()
        assert 'PORTER' in result
        assert 'MEMO_PARIS' in result

    def test_brand_structure(self):
        analytics = _make_analytics()
        result = analytics.by_brand()
        for brand, data in result.items():
            assert 'orders' in data
            assert 'revenue_krw' in data
            assert 'margin_pct' in data
            assert 'unique_skus' in data
            assert 'turnover_rate' in data

    def test_porter_order_count(self):
        analytics = _make_analytics()
        result = analytics.by_brand()
        assert result['PORTER']['orders'] == 2

    def test_turnover_rate_non_negative(self):
        analytics = _make_analytics()
        result = analytics.by_brand()
        for brand, data in result.items():
            assert data['turnover_rate'] >= 0.0

    def test_unique_skus_count(self):
        analytics = _make_analytics()
        result = analytics.by_brand()
        # PTR-TNK-001, PTR-TNK-002 → 2개
        assert result['PORTER']['unique_skus'] == 2


# ══════════════════════════════════════════════════════════
# trend_analysis 테스트
# ══════════════════════════════════════════════════════════

class TestTrendAnalysis:
    def test_returns_dict(self):
        analytics = _make_analytics()
        result = analytics.trend_analysis()
        assert isinstance(result, dict)

    def test_required_keys(self):
        analytics = _make_analytics()
        result = analytics.trend_analysis()
        assert 'period_days' in result
        assert 'current_period' in result
        assert 'prev_period' in result
        assert 'growth_pct' in result
        assert 'daily_series' in result
        assert 'moving_avg_7d' in result
        assert 'monthly_seasonality' in result

    def test_daily_series_length(self):
        analytics = _make_analytics()
        result = analytics.trend_analysis(days=14)
        assert len(result['daily_series']) == 14
        assert result['period_days'] == 14

    def test_moving_avg_length_matches_daily(self):
        analytics = _make_analytics()
        result = analytics.trend_analysis(days=10)
        assert len(result['moving_avg_7d']) == len(result['daily_series'])

    def test_first_6_moving_avg_are_none(self):
        analytics = _make_analytics()
        result = analytics.trend_analysis(days=10)
        for v in result['moving_avg_7d'][:6]:
            assert v is None

    def test_7th_moving_avg_is_not_none(self):
        analytics = _make_analytics()
        result = analytics.trend_analysis(days=10)
        assert result['moving_avg_7d'][6] is not None

    def test_growth_pct_is_float(self):
        analytics = _make_analytics()
        result = analytics.trend_analysis()
        assert isinstance(result['growth_pct'], float)

    def test_current_period_structure(self):
        analytics = _make_analytics()
        result = analytics.trend_analysis()
        cp = result['current_period']
        assert 'start' in cp
        assert 'end' in cp
        assert 'revenue_krw' in cp
        assert 'orders' in cp

    def test_monthly_seasonality_keys_are_str(self):
        analytics = _make_analytics()
        result = analytics.trend_analysis()
        for k in result['monthly_seasonality']:
            assert isinstance(k, str)


# ══════════════════════════════════════════════════════════
# channel_efficiency 테스트
# ══════════════════════════════════════════════════════════

class TestChannelEfficiency:
    def test_returns_dict(self):
        analytics = _make_analytics()
        result = analytics.channel_efficiency()
        assert isinstance(result, dict)

    def test_channel_structure(self):
        analytics = _make_analytics()
        result = analytics.channel_efficiency()
        for ch, data in result.items():
            assert 'orders' in data
            assert 'revenue_krw' in data
            assert 'margin_pct' in data
            assert 'aov_krw' in data

    def test_shopify_channel_detected(self):
        analytics = _make_analytics()
        result = analytics.channel_efficiency()
        assert 'shopify' in result

    def test_woocommerce_channel_detected(self):
        analytics = _make_analytics()
        result = analytics.channel_efficiency()
        assert 'woocommerce' in result

    def test_aov_is_non_negative(self):
        analytics = _make_analytics()
        result = analytics.channel_efficiency()
        for ch, data in result.items():
            assert data['aov_krw'] >= 0

    def test_detect_channel_explicit_field(self):
        """channel 필드가 명시된 경우 그대로 사용."""
        from src.analytics.business_report import BusinessAnalytics
        row = {'channel': 'coupang', 'sell_price_usd': 0}
        assert BusinessAnalytics._detect_channel(row) == 'coupang'

    def test_detect_channel_by_usd(self):
        """sell_price_usd > 0이면 shopify."""
        from src.analytics.business_report import BusinessAnalytics
        row = {'channel': '', 'sell_price_usd': 100}
        assert BusinessAnalytics._detect_channel(row) == 'shopify'

    def test_detect_channel_woocommerce_fallback(self):
        """sell_price_usd = 0, channel 없으면 woocommerce."""
        from src.analytics.business_report import BusinessAnalytics
        row = {'channel': '', 'sell_price_usd': 0}
        assert BusinessAnalytics._detect_channel(row) == 'woocommerce'

    def test_date_range_filter(self):
        analytics = _make_analytics()
        result = analytics.channel_efficiency(
            start=TODAY,
            end=str(date.today() + timedelta(days=1))
        )
        # 오늘 주문만 필터링: shopify 2건
        if 'shopify' in result:
            assert result['shopify']['orders'] == 2
