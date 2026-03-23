"""tests/test_periodic_report.py — Phase 7 PeriodicReportGenerator 테스트."""

import os
import sys
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.analytics.periodic_report import PeriodicReportGenerator

# ──────────────────────────────────────────────────────────
# 공통 픽스처
# ──────────────────────────────────────────────────────────

TODAY = date.today()
WEEK_MONDAY = TODAY - timedelta(days=TODAY.weekday())
YEAR_MONTH = TODAY.strftime('%Y-%m')

SAMPLE_ROWS = [
    {
        'order_id': '1', 'order_number': '#1001',
        'order_date': str(WEEK_MONDAY),
        'sku': 'PTR-TNK-001', 'vendor': 'PORTER',
        'buy_price': 30000, 'buy_currency': 'JPY',
        'sell_price_krw': 360000, 'sell_price_usd': 267.0,
        'margin_pct': 20.0, 'status': 'delivered',
    },
    {
        'order_id': '2', 'order_number': '#1002',
        'order_date': str(WEEK_MONDAY + timedelta(days=1)),
        'sku': 'MMP-EDP-001', 'vendor': 'MEMO_PARIS',
        'buy_price': 200.0, 'buy_currency': 'EUR',
        'sell_price_krw': 450000, 'sell_price_usd': 333.0,
        'margin_pct': 12.0,  # LOW_MARGIN_THRESHOLD 이하
        'status': 'delivered',
    },
]


def _make_generator(rows=None):
    gen = PeriodicReportGenerator.__new__(PeriodicReportGenerator)
    mock_tracker = MagicMock()
    mock_tracker._get_all_rows.return_value = list(rows if rows is not None else SAMPLE_ROWS)
    gen._tracker = mock_tracker

    from src.dashboard.revenue_report import RevenueReporter
    gen._reporter = RevenueReporter(mock_tracker)
    return gen


# ══════════════════════════════════════════════════════════
# weekly_report 테스트
# ══════════════════════════════════════════════════════════

class TestWeeklyReport:
    def test_returns_dict(self):
        gen = _make_generator()
        result = gen.weekly_report()
        assert isinstance(result, dict)

    def test_type_is_weekly(self):
        gen = _make_generator()
        result = gen.weekly_report()
        assert result['type'] == 'weekly'

    def test_required_keys(self):
        gen = _make_generator()
        result = gen.weekly_report()
        required = {
            'type', 'week_start', 'week_end',
            'total_orders', 'total_revenue_krw', 'gross_margin_pct',
            'growth_pct', 'by_vendor', 'by_channel',
            'top_products', 'risk_skus', 'fx_summary',
        }
        assert required.issubset(result.keys())

    def test_week_start_is_monday(self):
        gen = _make_generator()
        result = gen.weekly_report()
        week_start = date.fromisoformat(result['week_start'])
        assert week_start.weekday() == 0  # 월요일

    def test_week_end_is_sunday(self):
        gen = _make_generator()
        result = gen.weekly_report()
        week_end = date.fromisoformat(result['week_end'])
        assert week_end.weekday() == 6  # 일요일

    def test_explicit_week_start(self):
        gen = _make_generator()
        result = gen.weekly_report(week_start='2026-03-16')  # Monday
        assert result['week_start'] == '2026-03-16'
        assert result['week_end'] == '2026-03-22'

    def test_growth_pct_is_float(self):
        gen = _make_generator()
        result = gen.weekly_report()
        assert isinstance(result['growth_pct'], float)

    def test_risk_skus_contains_low_margin(self):
        gen = _make_generator()
        result = gen.weekly_report()
        # MMP-EDP-001 margin_pct=12.0 < 15.0 (LOW_MARGIN_THRESHOLD)
        risk_skus = result.get('risk_skus', [])
        risk_sku_ids = [s['sku'] for s in risk_skus]
        if SAMPLE_ROWS[1]['order_date'] >= str(WEEK_MONDAY):
            assert 'MMP-EDP-001' in risk_sku_ids

    def test_fx_summary_has_currencies(self):
        gen = _make_generator()
        result = gen.weekly_report()
        fx = result.get('fx_summary', {})
        assert 'USD/KRW' in fx
        assert 'JPY/KRW' in fx
        assert 'EUR/KRW' in fx

    def test_top_products_list(self):
        gen = _make_generator()
        result = gen.weekly_report()
        assert isinstance(result['top_products'], list)

    def test_by_vendor_dict(self):
        gen = _make_generator()
        result = gen.weekly_report()
        assert isinstance(result['by_vendor'], dict)


# ══════════════════════════════════════════════════════════
# monthly_report 테스트
# ══════════════════════════════════════════════════════════

class TestMonthlyReport:
    def test_returns_dict(self):
        gen = _make_generator()
        result = gen.monthly_report()
        assert isinstance(result, dict)

    def test_type_is_monthly(self):
        gen = _make_generator()
        result = gen.monthly_report()
        assert result['type'] == 'monthly'

    def test_required_keys(self):
        gen = _make_generator()
        result = gen.monthly_report()
        required = {
            'type', 'year_month', 'total_orders', 'total_revenue_krw',
            'gross_margin_pct', 'mom_growth_pct', 'yoy_growth_pct',
            'by_vendor', 'by_channel', 'channel_share_pct',
            'top_products', 'new_products', 'discontinued_products',
        }
        assert required.issubset(result.keys())

    def test_year_month_format(self):
        gen = _make_generator()
        result = gen.monthly_report()
        assert len(result['year_month']) == 7  # YYYY-MM
        assert result['year_month'][4] == '-'

    def test_explicit_year_month(self):
        gen = _make_generator()
        result = gen.monthly_report(year_month='2026-03')
        assert result['year_month'] == '2026-03'

    def test_growth_pct_is_float(self):
        gen = _make_generator()
        result = gen.monthly_report()
        assert isinstance(result['mom_growth_pct'], float)
        assert isinstance(result['yoy_growth_pct'], float)

    def test_channel_share_sums_to_100(self):
        gen = _make_generator()
        # 오늘 날짜 포함 주문이 있는 달로 테스트
        result = gen.monthly_report(year_month=TODAY.strftime('%Y-%m'))
        shares = list(result['channel_share_pct'].values())
        if shares:
            assert abs(sum(shares) - 100.0) < 1.0  # float 오차 허용

    def test_december_edge_case(self):
        """12월 처리 시 year+1, month=1 로 종료날짜 설정."""
        gen = _make_generator()
        result = gen.monthly_report(year_month='2025-12')
        assert result['year_month'] == '2025-12'

    def test_january_edge_case(self):
        """1월 전월 = 전년 12월."""
        gen = _make_generator()
        result = gen.monthly_report(year_month='2026-01')
        assert result['year_month'] == '2026-01'


# ══════════════════════════════════════════════════════════
# format_weekly_telegram 테스트
# ══════════════════════════════════════════════════════════

class TestFormatWeeklyTelegram:
    def test_returns_string(self):
        gen = _make_generator()
        report = gen.weekly_report()
        msg = gen.format_weekly_telegram(report)
        assert isinstance(msg, str)

    def test_contains_week_range(self):
        gen = _make_generator()
        report = gen.weekly_report()
        msg = gen.format_weekly_telegram(report)
        assert report['week_start'] in msg
        assert report['week_end'] in msg

    def test_contains_revenue(self):
        gen = _make_generator()
        report = gen.weekly_report()
        msg = gen.format_weekly_telegram(report)
        assert '매출' in msg

    def test_contains_growth_arrow(self):
        gen = _make_generator()
        report = gen.weekly_report()
        msg = gen.format_weekly_telegram(report)
        assert '📈' in msg or '📉' in msg


# ══════════════════════════════════════════════════════════
# format_monthly_telegram 테스트
# ══════════════════════════════════════════════════════════

class TestFormatMonthlyTelegram:
    def test_returns_string(self):
        gen = _make_generator()
        report = gen.monthly_report()
        msg = gen.format_monthly_telegram(report)
        assert isinstance(msg, str)

    def test_contains_year_month(self):
        gen = _make_generator()
        report = gen.monthly_report()
        msg = gen.format_monthly_telegram(report)
        assert report['year_month'] in msg

    def test_contains_mom_and_yoy(self):
        gen = _make_generator()
        report = gen.monthly_report()
        msg = gen.format_monthly_telegram(report)
        assert '전월' in msg
        assert '전년동월' in msg


# ══════════════════════════════════════════════════════════
# format_email_html 테스트
# ══════════════════════════════════════════════════════════

class TestFormatEmailHtml:
    def test_returns_html_string(self):
        gen = _make_generator()
        report = gen.weekly_report()
        html = gen.format_email_html(report)
        assert '<!DOCTYPE html>' in html

    def test_monthly_html_has_title(self):
        gen = _make_generator()
        report = gen.monthly_report()
        html = gen.format_email_html(report)
        assert '월간 리포트' in html

    def test_weekly_html_has_title(self):
        gen = _make_generator()
        report = gen.weekly_report()
        html = gen.format_email_html(report)
        assert '주간 리포트' in html


# ══════════════════════════════════════════════════════════
# send_weekly_report / send_monthly_report 테스트
# ══════════════════════════════════════════════════════════

class TestSendReports:
    @patch.dict(os.environ, {'WEEKLY_REPORT_ENABLED': '0'})
    def test_weekly_disabled_returns_none(self):
        gen = _make_generator()
        result = gen.send_weekly_report()
        assert result is None

    @patch.dict(os.environ, {'MONTHLY_REPORT_ENABLED': '0'})
    def test_monthly_disabled_returns_none(self):
        gen = _make_generator()
        result = gen.send_monthly_report()
        assert result is None

    @patch.dict(os.environ, {
        'WEEKLY_REPORT_ENABLED': '1',
        'TELEGRAM_ENABLED': '0',
        'EMAIL_ENABLED': '0',
    })
    def test_weekly_enabled_returns_report(self):
        gen = _make_generator()
        gen._write_report_to_sheets = MagicMock()
        result = gen.send_weekly_report()
        assert result is not None
        assert result['type'] == 'weekly'

    @patch.dict(os.environ, {
        'MONTHLY_REPORT_ENABLED': '1',
        'TELEGRAM_ENABLED': '0',
        'EMAIL_ENABLED': '0',
    })
    def test_monthly_enabled_returns_report(self):
        gen = _make_generator()
        gen._write_report_to_sheets = MagicMock()
        result = gen.send_monthly_report()
        assert result is not None
        assert result['type'] == 'monthly'
