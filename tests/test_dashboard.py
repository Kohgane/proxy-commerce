"""tests/test_dashboard.py — Phase 4 대시보드 모듈 테스트"""
import os
import sys
from datetime import date, datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, call

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# ──────────────────────────────────────────────────────────
# 공통 픽스처
# ──────────────────────────────────────────────────────────

NOW_ISO = '2026-03-09T13:00:00Z'
TODAY = '2026-03-09'

SAMPLE_ORDER_ROWS = [
    {
        'order_id': '12345', 'order_number': '#1001',
        'customer_name': '홍길동', 'customer_email': 'hong@example.com',
        'order_date': '2026-03-09T10:00:00Z',
        'sku': 'PTR-TNK-100000', 'vendor': 'PORTER', 'forwarder': 'zenmarket',
        'buy_price': 30800, 'buy_currency': 'JPY',
        'sell_price_krw': 360000, 'sell_price_usd': 267.0,
        'margin_pct': 14.4, 'status': 'routed',
        'status_updated_at': '2026-03-09T10:01:00Z',
        'tracking_number': '', 'carrier': '', 'notes': '',
    },
    {
        'order_id': '99999', 'order_number': '#1002',
        'customer_name': '김철수', 'customer_email': 'cs@example.com',
        'order_date': '2026-03-09T11:00:00Z',
        'sku': 'MMP-EDP-200001', 'vendor': 'MEMO_PARIS', 'forwarder': '',
        'buy_price': 250.0, 'buy_currency': 'EUR',
        'sell_price_krw': 500000, 'sell_price_usd': 370.0,
        'margin_pct': 27.0, 'status': 'ordered',
        'status_updated_at': '2026-03-09T11:02:00Z',
        'tracking_number': '', 'carrier': '', 'notes': '',
    },
    {
        'order_id': '11111', 'order_number': '#1000',
        'customer_name': '이영희', 'customer_email': 'lee@example.com',
        'order_date': '2026-03-08T09:00:00Z',
        'sku': 'PTR-TNK-100001', 'vendor': 'PORTER', 'forwarder': 'zenmarket',
        'buy_price': 25000, 'buy_currency': 'JPY',
        'sell_price_krw': 300000, 'sell_price_usd': 222.0,
        'margin_pct': 16.7, 'status': 'delivered',
        'status_updated_at': '2026-03-09T08:00:00Z',
        'tracking_number': 'CJ123456789', 'carrier': 'cj', 'notes': '',
    },
]

SHOPIFY_ORDER_DATA = {
    'id': 12345,
    'order_number': 1001,
    'name': '#1001',
    'created_at': '2026-03-09T10:00:00Z',
    'customer': {'first_name': '길동', 'last_name': '홍', 'email': 'hong@example.com'},
    'line_items': [
        {
            'sku': 'PTR-TNK-100000',
            'title': 'Tanker Briefcase',
            'quantity': 1,
            'price': '360000',
            'price_set': {
                'shop_money': {'amount': '360000', 'currency_code': 'KRW'},
                'presentment_money': {'amount': '267.0', 'currency_code': 'USD'},
            },
        }
    ],
}

ROUTED_DATA = {
    'order_id': 12345,
    'order_number': '#1001',
    'customer': {'name': '홍 길동', 'email': 'hong@example.com'},
    'tasks': [
        {
            'sku': 'PTR-TNK-100000',
            'title': '탱커 브리프케이스',
            'vendor': 'PORTER',
            'forwarder': 'zenmarket',
            'buy_price': 30800,
            'buy_currency': 'JPY',
        }
    ],
    'summary': {'total_tasks': 1, 'by_vendor': {'PORTER': 1}, 'by_forwarder': {'zenmarket': 1}},
}


# ══════════════════════════════════════════════════════════
# OrderStatusTracker 테스트
# ══════════════════════════════════════════════════════════

class TestOrderStatusTracker:
    def _make_tracker(self, rows=None):
        from src.dashboard.order_status import OrderStatusTracker
        tracker = OrderStatusTracker(sheet_id='dummy', worksheet='orders')
        tracker._get_all_rows = MagicMock(return_value=list(rows if rows is not None else SAMPLE_ORDER_ROWS))
        return tracker

    # ── record_order ──────────────────────────────────────

    def test_record_order_appends_row(self):
        from src.dashboard.order_status import OrderStatusTracker, ORDER_HEADERS
        tracker = OrderStatusTracker(sheet_id='dummy', worksheet='orders')

        mock_ws = MagicMock()
        mock_ws.get_all_values.return_value = [ORDER_HEADERS]
        with patch.object(tracker, '_get_worksheet', return_value=mock_ws):
            result = tracker.record_order(SHOPIFY_ORDER_DATA, ROUTED_DATA)

        mock_ws.append_row.assert_called_once()
        assert result['status'] == 'routed'
        assert result['sku'] == 'PTR-TNK-100000'
        assert result['order_id'] == '12345'

    def test_record_order_creates_header_if_empty(self):
        from src.dashboard.order_status import OrderStatusTracker, ORDER_HEADERS
        tracker = OrderStatusTracker(sheet_id='dummy', worksheet='orders')

        mock_ws = MagicMock()
        mock_ws.get_all_values.return_value = []  # empty sheet
        with patch.object(tracker, '_get_worksheet', return_value=mock_ws):
            tracker.record_order(SHOPIFY_ORDER_DATA, ROUTED_DATA)

        # First call inserts headers, second appends the data row
        assert mock_ws.append_row.call_count == 2
        first_call_arg = mock_ws.append_row.call_args_list[0][0][0]
        assert first_call_arg == ORDER_HEADERS

    def test_record_order_sell_price_extracted(self):
        from src.dashboard.order_status import OrderStatusTracker, ORDER_HEADERS
        tracker = OrderStatusTracker(sheet_id='dummy', worksheet='orders')

        mock_ws = MagicMock()
        mock_ws.get_all_values.return_value = [ORDER_HEADERS]
        with patch.object(tracker, '_get_worksheet', return_value=mock_ws):
            result = tracker.record_order(SHOPIFY_ORDER_DATA, ROUTED_DATA)

        assert result['sell_price_krw'] == 360000.0

    def test_record_order_multiple_tasks(self):
        from src.dashboard.order_status import OrderStatusTracker, ORDER_HEADERS
        tracker = OrderStatusTracker(sheet_id='dummy', worksheet='orders')

        mock_ws = MagicMock()
        mock_ws.get_all_values.return_value = [ORDER_HEADERS]

        multi_routed = {
            'order_id': 99999,
            'order_number': '#1002',
            'customer': {'name': '김철수', 'email': 'cs@example.com'},
            'tasks': [
                {'sku': 'PTR-TNK-100000', 'vendor': 'PORTER', 'forwarder': 'zenmarket',
                 'buy_price': 30800, 'buy_currency': 'JPY'},
                {'sku': 'MMP-EDP-200001', 'vendor': 'MEMO_PARIS', 'forwarder': '',
                 'buy_price': 250.0, 'buy_currency': 'EUR'},
            ],
            'summary': {},
        }
        with patch.object(tracker, '_get_worksheet', return_value=mock_ws):
            result = tracker.record_order(SHOPIFY_ORDER_DATA, multi_routed)

        # Two data rows appended
        assert mock_ws.append_row.call_count == 2

    # ── update_status ─────────────────────────────────────

    def test_update_status_valid(self):
        from src.dashboard.order_status import OrderStatusTracker, ORDER_HEADERS
        tracker = OrderStatusTracker(sheet_id='dummy', worksheet='orders')

        row_values = [
            ORDER_HEADERS,
            ['12345', '#1001', '홍길동', 'hong@example.com', '2026-03-09T10:00:00Z',
             'PTR-TNK-100000', 'PORTER', 'zenmarket', 30800, 'JPY', 360000, 267.0,
             14.4, 'routed', '2026-03-09T10:01:00Z', '', '', ''],
        ]
        mock_ws = MagicMock()
        mock_ws.get_all_values.return_value = row_values
        with patch.object(tracker, '_get_worksheet', return_value=mock_ws):
            result = tracker.update_status(
                order_id='12345',
                sku='PTR-TNK-100000',
                new_status='ordered',
            )

        assert result['status'] == 'ordered'
        assert mock_ws.update_cell.called

    def test_update_status_with_tracking(self):
        from src.dashboard.order_status import OrderStatusTracker, ORDER_HEADERS
        tracker = OrderStatusTracker(sheet_id='dummy', worksheet='orders')

        row_values = [
            ORDER_HEADERS,
            ['12345', '#1001', '홍길동', 'hong@example.com', '2026-03-09T10:00:00Z',
             'PTR-TNK-100000', 'PORTER', 'zenmarket', 30800, 'JPY', 360000, 267.0,
             14.4, 'at_forwarder', '2026-03-09T10:01:00Z', '', '', ''],
        ]
        mock_ws = MagicMock()
        mock_ws.get_all_values.return_value = row_values
        with patch.object(tracker, '_get_worksheet', return_value=mock_ws):
            result = tracker.update_status(
                order_id='12345',
                sku='PTR-TNK-100000',
                new_status='shipped_domestic',
                tracking_number='CJ123456789',
                carrier='cj',
            )

        assert result['tracking_number'] == 'CJ123456789'
        assert result['carrier'] == 'cj'

    def test_update_status_invalid_raises(self):
        from src.dashboard.order_status import OrderStatusTracker
        tracker = OrderStatusTracker(sheet_id='dummy', worksheet='orders')

        with pytest.raises(ValueError, match="유효하지 않은 status"):
            tracker.update_status('12345', 'PTR-TNK-100000', 'invalid_status')

    def test_update_status_not_found_raises(self):
        from src.dashboard.order_status import OrderStatusTracker, ORDER_HEADERS
        tracker = OrderStatusTracker(sheet_id='dummy', worksheet='orders')

        mock_ws = MagicMock()
        mock_ws.get_all_values.return_value = [ORDER_HEADERS]
        with patch.object(tracker, '_get_worksheet', return_value=mock_ws):
            with pytest.raises(KeyError):
                tracker.update_status('NONEXISTENT', 'SKU', 'routed')

    # ── get_orders_by_status ──────────────────────────────

    def test_get_orders_by_status_routed(self):
        tracker = self._make_tracker()
        rows = tracker.get_orders_by_status('routed')
        assert len(rows) == 1
        assert rows[0]['order_id'] == '12345'

    def test_get_orders_by_status_empty(self):
        tracker = self._make_tracker()
        rows = tracker.get_orders_by_status('cancelled')
        assert rows == []

    def test_get_orders_by_status_delivered(self):
        tracker = self._make_tracker()
        rows = tracker.get_orders_by_status('delivered')
        assert len(rows) == 1

    # ── get_order_history ─────────────────────────────────

    def test_get_order_history(self):
        tracker = self._make_tracker()
        rows = tracker.get_order_history('12345')
        assert len(rows) == 1
        assert rows[0]['sku'] == 'PTR-TNK-100000'

    def test_get_order_history_not_found(self):
        tracker = self._make_tracker()
        rows = tracker.get_order_history('NONEXISTENT')
        assert rows == []

    # ── get_pending_orders ────────────────────────────────

    def test_get_pending_orders_excludes_delivered(self):
        tracker = self._make_tracker()
        rows = tracker.get_pending_orders()
        statuses = {r['status'] for r in rows}
        assert 'delivered' not in statuses
        assert 'cancelled' not in statuses

    def test_get_pending_orders_count(self):
        tracker = self._make_tracker()
        rows = tracker.get_pending_orders()
        # 3 rows total, 1 delivered → 2 pending
        assert len(rows) == 2

    # ── get_stats ────────────────────────────────────────

    def test_get_stats_total(self):
        tracker = self._make_tracker()
        stats = tracker.get_stats()
        assert stats['total'] == 3

    def test_get_stats_by_status(self):
        tracker = self._make_tracker()
        stats = tracker.get_stats()
        assert stats['by_status']['routed'] == 1
        assert stats['by_status']['ordered'] == 1
        assert stats['by_status']['delivered'] == 1

    def test_get_stats_by_vendor(self):
        tracker = self._make_tracker()
        stats = tracker.get_stats()
        assert 'porter' in stats['by_vendor']
        assert 'memo_paris' in stats['by_vendor']

    def test_get_stats_avg_processing_days(self):
        tracker = self._make_tracker()
        stats = tracker.get_stats()
        # delivered row: order_date=2026-03-08T09:00:00Z, updated=2026-03-09T08:00:00Z → ~0.96 days
        assert stats['avg_processing_days'] >= 0

    def test_get_stats_empty_sheet(self):
        tracker = self._make_tracker(rows=[])
        stats = tracker.get_stats()
        assert stats['total'] == 0
        assert stats['by_status'] == {}
        assert stats['avg_processing_days'] == 0.0


# ══════════════════════════════════════════════════════════
# RevenueReporter 테스트
# ══════════════════════════════════════════════════════════

class TestRevenueReporter:
    def _make_reporter(self, rows=None):
        from src.dashboard.order_status import OrderStatusTracker
        from src.dashboard.revenue_report import RevenueReporter
        tracker = OrderStatusTracker(sheet_id='dummy', worksheet='orders')
        tracker._get_all_rows = MagicMock(return_value=list(rows if rows is not None else SAMPLE_ORDER_ROWS))
        return RevenueReporter(order_tracker=tracker)

    # ── daily_revenue ─────────────────────────────────────

    def test_daily_revenue_today(self):
        reporter = self._make_reporter()
        result = reporter.daily_revenue(TODAY)
        # Two rows with order_date 2026-03-09
        assert result['date'] == TODAY
        assert result['total_orders'] == 2

    def test_daily_revenue_no_orders(self):
        reporter = self._make_reporter()
        result = reporter.daily_revenue('2020-01-01')
        assert result['total_orders'] == 0
        assert result['total_revenue_krw'] == 0

    def test_daily_revenue_none_defaults_to_today(self):
        reporter = self._make_reporter(rows=[])
        result = reporter.daily_revenue(None)
        assert 'date' in result

    def test_daily_revenue_by_vendor(self):
        reporter = self._make_reporter()
        result = reporter.daily_revenue(TODAY)
        assert 'porter' in result['by_vendor'] or 'memo_paris' in result['by_vendor']

    def test_daily_revenue_top_products(self):
        reporter = self._make_reporter()
        result = reporter.daily_revenue(TODAY)
        assert isinstance(result['top_products'], list)

    def test_daily_revenue_gross_profit(self):
        reporter = self._make_reporter()
        result = reporter.daily_revenue(TODAY)
        assert result['gross_profit_krw'] == result['total_revenue_krw'] - result['total_cost_krw']

    # ── weekly_revenue ────────────────────────────────────

    def test_weekly_revenue_structure(self):
        reporter = self._make_reporter()
        result = reporter.weekly_revenue('2026-03-09')
        assert 'week_start' in result
        assert 'week_end' in result
        assert 'daily' in result
        assert len(result['daily']) == 7

    def test_weekly_revenue_none_defaults_to_this_week(self):
        reporter = self._make_reporter(rows=[])
        result = reporter.weekly_revenue(None)
        assert 'week_start' in result

    # ── monthly_revenue ───────────────────────────────────

    def test_monthly_revenue_structure(self):
        reporter = self._make_reporter()
        result = reporter.monthly_revenue('2026-03')
        assert result['year_month'] == '2026-03'
        assert 'total_revenue_krw' in result

    def test_monthly_revenue_none_defaults_to_current(self):
        reporter = self._make_reporter(rows=[])
        result = reporter.monthly_revenue(None)
        assert 'year_month' in result

    def test_monthly_revenue_december_boundary(self):
        """12월 → 다음 해 1월 경계 처리."""
        reporter = self._make_reporter(rows=[])
        result = reporter.monthly_revenue('2025-12')
        assert result['year_month'] == '2025-12'

    # ── margin_analysis ───────────────────────────────────

    def test_margin_analysis_structure(self):
        reporter = self._make_reporter()
        result = reporter.margin_analysis()
        assert 'overall_margin_pct' in result
        assert 'by_vendor' in result
        assert 'by_category' in result
        assert 'low_margin_products' in result
        assert 'high_margin_products' in result

    def test_margin_analysis_low_margin_threshold(self):
        reporter = self._make_reporter()
        result = reporter.margin_analysis()
        for p in result['low_margin_products']:
            assert p['margin_pct'] < 15.0

    def test_margin_analysis_high_margin_threshold(self):
        reporter = self._make_reporter()
        result = reporter.margin_analysis()
        for p in result['high_margin_products']:
            assert p['margin_pct'] >= 35.0

    def test_margin_analysis_empty_data(self):
        reporter = self._make_reporter(rows=[])
        result = reporter.margin_analysis()
        assert result['overall_margin_pct'] == 0.0

    # ── currency_impact ───────────────────────────────────

    def test_currency_impact_structure(self):
        reporter = self._make_reporter()
        result = reporter.currency_impact()
        assert 'fx_current' in result
        assert 'impacts' in result
        assert 'avg_margin_delta' in result

    def test_currency_impact_empty(self):
        reporter = self._make_reporter(rows=[])
        result = reporter.currency_impact()
        assert result['avg_margin_delta'] == 0.0
        assert result['impacts'] == []


# ══════════════════════════════════════════════════════════
# DailySummaryGenerator 테스트
# ══════════════════════════════════════════════════════════

class TestDailySummaryGenerator:
    def _make_generator(self, rows=None):
        from src.dashboard.daily_summary import DailySummaryGenerator
        gen = DailySummaryGenerator.__new__(DailySummaryGenerator)

        from src.dashboard.order_status import OrderStatusTracker
        from src.dashboard.revenue_report import RevenueReporter
        tracker = OrderStatusTracker(sheet_id='dummy', worksheet='orders')
        tracker._get_all_rows = MagicMock(return_value=list(rows if rows is not None else SAMPLE_ORDER_ROWS))
        reporter = RevenueReporter(order_tracker=tracker)

        gen.order_tracker = tracker
        gen.reporter = reporter
        return gen

    # ── generate_summary ──────────────────────────────────

    def test_generate_summary_structure(self):
        gen = self._make_generator()
        summary = gen.generate_summary(TODAY)
        assert 'date' in summary
        assert 'revenue' in summary
        assert 'order_stats' in summary
        assert 'pending_orders' in summary
        assert 'alerts' in summary

    def test_generate_summary_date(self):
        gen = self._make_generator()
        summary = gen.generate_summary(TODAY)
        assert summary['date'] == TODAY

    def test_generate_summary_none_uses_today(self):
        gen = self._make_generator(rows=[])
        summary = gen.generate_summary(None)
        assert summary['date'] == str(date.today())

    # ── format_telegram ───────────────────────────────────

    def test_format_telegram_contains_date(self):
        gen = self._make_generator()
        summary = gen.generate_summary(TODAY)
        msg = gen.format_telegram(summary)
        assert TODAY in msg

    def test_format_telegram_contains_revenue(self):
        gen = self._make_generator()
        summary = gen.generate_summary(TODAY)
        msg = gen.format_telegram(summary)
        assert '매출' in msg
        assert '₩' in msg

    def test_format_telegram_contains_margin(self):
        gen = self._make_generator()
        summary = gen.generate_summary(TODAY)
        msg = gen.format_telegram(summary)
        assert '마진' in msg

    def test_format_telegram_with_alerts(self):
        gen = self._make_generator()
        summary = {
            'date': TODAY,
            'revenue': {'total_revenue_krw': 0, 'total_orders': 0, 'gross_margin_pct': 0.0, 'by_vendor': {}},
            'order_stats': {},
            'pending_orders': [],
            'alerts': ['주문 #12345 발주 후 8일 경과 (porter)'],
        }
        msg = gen.format_telegram(summary)
        assert '알림' in msg
        assert '#12345' in msg

    # ── format_email_html ─────────────────────────────────

    def test_format_email_html_is_html(self):
        gen = self._make_generator()
        summary = gen.generate_summary(TODAY)
        html = gen.format_email_html(summary)
        assert '<html' in html
        assert '</html>' in html

    def test_format_email_html_contains_date(self):
        gen = self._make_generator()
        summary = gen.generate_summary(TODAY)
        html = gen.format_email_html(summary)
        assert TODAY in html

    def test_format_email_html_with_alerts(self):
        gen = self._make_generator()
        summary = gen.generate_summary(TODAY)
        summary['alerts'] = ['테스트 알림']
        html = gen.format_email_html(summary)
        assert '알림' in html
        assert '테스트 알림' in html

    # ── _check_alerts ─────────────────────────────────────

    def test_check_alerts_stale_ordered(self):
        """발주 완료 후 7일 이상 경과한 주문 알림."""
        gen = self._make_generator()
        # Create an 'ordered' row with status_updated_at 10 days ago
        stale_time = (datetime.now(timezone.utc) - timedelta(days=10)).strftime('%Y-%m-%dT%H:%M:%SZ')
        pending = [
            {
                'order_id': '55555',
                'status': 'ordered',
                'vendor': 'porter',
                'status_updated_at': stale_time,
            }
        ]
        with patch.dict(os.environ, {'ALERT_STALE_ORDER_DAYS': '7'}):
            alerts = gen._check_alerts({}, pending)
        assert any('55555' in a for a in alerts)
        assert any('발주 후' in a for a in alerts)

    def test_check_alerts_forwarder_too_long(self):
        """배대지 도착 후 5일 이상 경과한 주문 알림."""
        gen = self._make_generator()
        stale_time = (datetime.now(timezone.utc) - timedelta(days=8)).strftime('%Y-%m-%dT%H:%M:%SZ')
        pending = [
            {
                'order_id': '77777',
                'status': 'at_forwarder',
                'vendor': 'porter',
                'status_updated_at': stale_time,
            }
        ]
        with patch.dict(os.environ, {'ALERT_FORWARDER_DAYS': '5'}):
            alerts = gen._check_alerts({}, pending)
        assert any('77777' in a for a in alerts)
        assert any('배대지' in a for a in alerts)

    def test_check_alerts_no_stale(self):
        """최근 주문은 알림 없음."""
        gen = self._make_generator()
        fresh_time = (datetime.now(timezone.utc) - timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%SZ')
        pending = [
            {
                'order_id': '88888',
                'status': 'ordered',
                'vendor': 'porter',
                'status_updated_at': fresh_time,
            }
        ]
        with patch.dict(os.environ, {'ALERT_STALE_ORDER_DAYS': '7'}):
            alerts = gen._check_alerts({}, pending)
        assert not any('88888' in a for a in alerts)

    # ── send_daily_summary ────────────────────────────────

    def test_send_daily_summary_telegram_called(self):
        gen = self._make_generator()
        with patch('src.utils.telegram.send_tele') as mock_tele, \
             patch.dict(os.environ, {'DAILY_SUMMARY_ENABLED': '1', 'TELEGRAM_ENABLED': '1', 'EMAIL_ENABLED': '0'}):
            result = gen.send_daily_summary(TODAY)
        mock_tele.assert_called_once()
        assert result is not None

    def test_send_daily_summary_disabled(self):
        gen = self._make_generator()
        with patch('src.utils.telegram.send_tele') as mock_tele, \
             patch.dict(os.environ, {'DAILY_SUMMARY_ENABLED': '0'}):
            result = gen.send_daily_summary(TODAY)
        mock_tele.assert_not_called()
        assert result is None

    def test_send_daily_summary_email_called(self):
        gen = self._make_generator()
        with patch('src.utils.emailer.send_mail') as mock_mail, \
             patch('src.utils.telegram.send_tele'), \
             patch.dict(os.environ, {'DAILY_SUMMARY_ENABLED': '1', 'TELEGRAM_ENABLED': '0', 'EMAIL_ENABLED': '1'}):
            gen.send_daily_summary(TODAY)
        mock_mail.assert_called_once()

    def test_send_daily_summary_telegram_failure_graceful(self):
        """텔레그램 실패해도 Exception이 propagate되지 않아야 함."""
        gen = self._make_generator()
        with patch('src.utils.telegram.send_tele', side_effect=Exception("Network error")), \
             patch.dict(os.environ, {'DAILY_SUMMARY_ENABLED': '1', 'TELEGRAM_ENABLED': '1', 'EMAIL_ENABLED': '0'}):
            # Should not raise
            gen.send_daily_summary(TODAY)


# ══════════════════════════════════════════════════════════
# CLI 테스트
# ══════════════════════════════════════════════════════════

class TestDashboardCLI:
    def test_cli_daily_summary_action(self):
        from src.dashboard.cli import _build_parser
        parser = _build_parser()
        ns = parser.parse_args(['--action', 'daily-summary', '--date', TODAY])
        assert ns.action == 'daily-summary'
        assert ns.date == TODAY

    def test_cli_revenue_daily(self):
        from src.dashboard.cli import _build_parser
        parser = _build_parser()
        ns = parser.parse_args(['--action', 'revenue', '--period', 'daily', '--date', TODAY])
        assert ns.action == 'revenue'
        assert ns.period == 'daily'

    def test_cli_revenue_weekly(self):
        from src.dashboard.cli import _build_parser
        parser = _build_parser()
        ns = parser.parse_args(['--action', 'revenue', '--period', 'weekly', '--week-start', '2026-03-03'])
        assert ns.period == 'weekly'
        assert ns.week_start == '2026-03-03'

    def test_cli_revenue_monthly(self):
        from src.dashboard.cli import _build_parser
        parser = _build_parser()
        ns = parser.parse_args(['--action', 'revenue', '--period', 'monthly', '--month', '2026-03'])
        assert ns.period == 'monthly'
        assert ns.month == '2026-03'

    def test_cli_status_pending(self):
        from src.dashboard.cli import _build_parser
        parser = _build_parser()
        ns = parser.parse_args(['--action', 'status', '--filter', 'pending'])
        assert ns.action == 'status'
        assert ns.filter == 'pending'

    def test_cli_status_order_id(self):
        from src.dashboard.cli import _build_parser
        parser = _build_parser()
        ns = parser.parse_args(['--action', 'status', '--order-id', '12345'])
        assert ns.order_id == '12345'

    def test_cli_margin_analysis(self):
        from src.dashboard.cli import _build_parser
        parser = _build_parser()
        ns = parser.parse_args(['--action', 'margin-analysis'])
        assert ns.action == 'margin-analysis'

    def test_cli_main_revenue_daily(self, capsys):
        from src.dashboard.cli import main
        from src.dashboard.order_status import OrderStatusTracker
        mock_tracker = MagicMock()
        mock_tracker._get_all_rows = MagicMock(return_value=list(SAMPLE_ORDER_ROWS))

        with patch('src.dashboard.revenue_report.RevenueReporter.__init__', return_value=None), \
             patch('src.dashboard.revenue_report.RevenueReporter._tracker', mock_tracker, create=True), \
             patch('src.dashboard.revenue_report.RevenueReporter.daily_revenue',
                   return_value={'date': TODAY, 'total_orders': 2, 'total_revenue_krw': 860000,
                                 'total_cost_krw': 300000, 'gross_profit_krw': 560000,
                                 'gross_margin_pct': 25.0, 'by_vendor': {}, 'by_channel': {}, 'top_products': []}):
            main(['--action', 'revenue', '--period', 'daily', '--date', TODAY])

        captured = capsys.readouterr()
        assert 'date' in captured.out

    def test_cli_main_status_pending(self, capsys):
        from src.dashboard.cli import main
        from src.dashboard.order_status import OrderStatusTracker

        with patch.object(OrderStatusTracker, 'get_pending_orders', return_value=SAMPLE_ORDER_ROWS[:2]):
            main(['--action', 'status', '--filter', 'pending'])

        captured = capsys.readouterr()
        assert 'PTR-TNK-100000' in captured.out

    def test_cli_main_margin_analysis(self, capsys):
        from src.dashboard.cli import main
        from src.dashboard.order_status import OrderStatusTracker

        with patch.object(OrderStatusTracker, '_get_all_rows', return_value=list(SAMPLE_ORDER_ROWS)):
            main(['--action', 'margin-analysis'])

        captured = capsys.readouterr()
        assert 'overall_margin_pct' in captured.out


# ══════════════════════════════════════════════════════════
# Webhook 통합 테스트
# ══════════════════════════════════════════════════════════

class TestWebhookIntegration:
    """order_webhook.py에서 status_tracker가 올바르게 호출되는지 확인."""

    def _make_app(self):
        import importlib
        import src.order_webhook as webhook_module
        return webhook_module.app

    def test_shopify_order_webhook_records_status(self):
        """POST /webhook/shopify/order 시 status_tracker.record_order 호출."""
        import json
        import src.order_webhook as wm

        mock_routed = {
            'order_id': 12345,
            'order_number': '#1001',
            'customer': {'name': '홍길동', 'email': 'hong@example.com'},
            'tasks': [],
            'summary': {'total_tasks': 0, 'by_vendor': {}, 'by_forwarder': {}},
        }

        with wm.app.test_client() as client:
            with patch('src.order_webhook.verify_webhook', return_value=True), \
                 patch('src.order_webhook.router') as mock_router, \
                 patch('src.order_webhook.notifier'), \
                 patch('src.order_webhook.status_tracker') as mock_st:
                mock_router.route_order.return_value = mock_routed
                resp = client.post(
                    '/webhook/shopify/order',
                    data=json.dumps(SHOPIFY_ORDER_DATA).encode(),
                    content_type='application/json',
                )
        assert resp.status_code == 200
        mock_st.record_order.assert_called_once()

    def test_shopify_order_webhook_status_failure_does_not_break(self):
        """status_tracker.record_order 실패해도 200 반환."""
        import json
        import src.order_webhook as wm

        mock_routed = {
            'order_id': 12345,
            'order_number': '#1001',
            'customer': {'name': '홍길동', 'email': 'hong@example.com'},
            'tasks': [],
            'summary': {'total_tasks': 0, 'by_vendor': {}, 'by_forwarder': {}},
        }

        with wm.app.test_client() as client:
            with patch('src.order_webhook.verify_webhook', return_value=True), \
                 patch('src.order_webhook.router') as mock_router, \
                 patch('src.order_webhook.notifier'), \
                 patch('src.order_webhook.status_tracker') as mock_st:
                mock_router.route_order.return_value = mock_routed
                mock_st.record_order.side_effect = Exception("Sheets error")
                resp = client.post(
                    '/webhook/shopify/order',
                    data=json.dumps(SHOPIFY_ORDER_DATA).encode(),
                    content_type='application/json',
                )
        assert resp.status_code == 200

    def test_tracking_webhook_updates_status(self):
        """POST /webhook/forwarder/tracking 시 status_tracker.update_status 호출."""
        import json
        import src.order_webhook as wm

        tracking_payload = {
            'order_id': '12345',
            'sku': 'PTR-TNK-100000',
            'tracking_number': 'CJ123456789',
            'carrier': 'cj',
            'status': 'shipped',
        }

        with wm.app.test_client() as client:
            with patch('src.order_webhook.tracker') as mock_tracker, \
                 patch('src.order_webhook.notifier'), \
                 patch('src.order_webhook.status_tracker') as mock_st:
                mock_tracker.process_tracking.return_value = {'shopify_updated': True, 'woo_updated': False, 'notification_sent': True}
                resp = client.post(
                    '/webhook/forwarder/tracking',
                    data=json.dumps(tracking_payload).encode(),
                    content_type='application/json',
                )

        assert resp.status_code == 200
        mock_st.update_status.assert_called_once_with(
            order_id='12345',
            sku='PTR-TNK-100000',
            new_status='shipped_domestic',
            tracking_number='CJ123456789',
            carrier='cj',
        )

    def test_tracking_webhook_status_failure_does_not_break(self):
        """status_tracker.update_status 실패해도 200 반환."""
        import json
        import src.order_webhook as wm

        tracking_payload = {
            'order_id': '12345',
            'sku': 'PTR-TNK-100000',
            'tracking_number': 'CJ123456789',
            'carrier': 'cj',
        }

        with wm.app.test_client() as client:
            with patch('src.order_webhook.tracker') as mock_tracker, \
                 patch('src.order_webhook.notifier'), \
                 patch('src.order_webhook.status_tracker') as mock_st:
                mock_tracker.process_tracking.return_value = {'shopify_updated': False, 'woo_updated': False, 'notification_sent': False}
                mock_st.update_status.side_effect = Exception("Sheets error")
                resp = client.post(
                    '/webhook/forwarder/tracking',
                    data=json.dumps(tracking_payload).encode(),
                    content_type='application/json',
                )
        assert resp.status_code == 200
