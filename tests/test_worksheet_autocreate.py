"""tests/test_worksheet_autocreate.py — WorksheetNotFound 방어 로직 단위 테스트"""
import os
import sys
from unittest.mock import MagicMock, patch

import gspread

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


# ── open_sheet 자동 생성 테스트 ─────────────────────────────

class TestOpenSheetAutoCreate:
    """src/utils/sheets.py open_sheet() 워크시트 자동 생성 테스트."""

    def _make_mock_client(self, worksheet_exists=True):
        mock_client = MagicMock()
        mock_sh = MagicMock()
        mock_ws = MagicMock()
        mock_client.open_by_key.return_value = mock_sh
        if worksheet_exists:
            mock_sh.worksheet.return_value = mock_ws
        else:
            mock_sh.worksheet.side_effect = gspread.exceptions.WorksheetNotFound('orders')
            mock_sh.add_worksheet.return_value = mock_ws
        return mock_client, mock_sh, mock_ws

    @patch('src.utils.sheets._service_account')
    def test_open_sheet_existing_worksheet(self, mock_sa):
        """워크시트가 이미 존재하면 그대로 반환."""
        mock_client, mock_sh, mock_ws = self._make_mock_client(worksheet_exists=True)
        mock_sa.return_value = mock_client

        from src.utils.sheets import open_sheet
        result = open_sheet('sheet-id', 'orders')

        mock_sh.worksheet.assert_called_once_with('orders')
        mock_sh.add_worksheet.assert_not_called()
        assert result is mock_ws

    @patch('src.utils.sheets._service_account')
    def test_open_sheet_creates_missing_worksheet(self, mock_sa):
        """워크시트가 없으면 자동 생성 후 반환."""
        mock_client, mock_sh, mock_ws = self._make_mock_client(worksheet_exists=False)
        mock_sa.return_value = mock_client

        from src.utils.sheets import open_sheet
        result = open_sheet('sheet-id', 'orders')

        mock_sh.worksheet.assert_called_once_with('orders')
        mock_sh.add_worksheet.assert_called_once_with(title='orders', rows=1000, cols=20)
        assert result is mock_ws


# ── OrderStatusTracker._get_worksheet 자동 헤더 삽입 테스트 ──

class TestGetWorksheetAutoHeader:
    """order_status.py _get_worksheet() 빈 시트 헤더 자동 삽입 테스트."""

    @patch('src.utils.sheets.open_sheet')
    def test_get_worksheet_adds_headers_when_empty(self, mock_open_sheet):
        """open_sheet이 빈 시트를 반환하면 ORDER_HEADERS가 append_row로 삽입됨."""
        from src.dashboard.order_status import OrderStatusTracker, ORDER_HEADERS

        mock_ws = MagicMock()
        mock_ws.get_all_values.return_value = []
        mock_open_sheet.return_value = mock_ws

        tracker = OrderStatusTracker(sheet_id='sid', worksheet='orders')
        result = tracker._get_worksheet()

        mock_ws.append_row.assert_called_once_with(ORDER_HEADERS)
        assert result is mock_ws

    @patch('src.utils.sheets.open_sheet')
    def test_get_worksheet_no_header_when_not_empty(self, mock_open_sheet):
        """시트에 이미 데이터가 있으면 헤더를 삽입하지 않음."""
        from src.dashboard.order_status import OrderStatusTracker, ORDER_HEADERS

        mock_ws = MagicMock()
        sample_row = ['1'] + [''] * (len(ORDER_HEADERS) - 1)
        mock_ws.get_all_values.return_value = [ORDER_HEADERS, sample_row]
        mock_open_sheet.return_value = mock_ws

        tracker = OrderStatusTracker(sheet_id='sid', worksheet='orders')
        result = tracker._get_worksheet()

        mock_ws.append_row.assert_not_called()
        assert result is mock_ws


# ── OrderStatusTracker._get_all_rows 예외 방어 테스트 ──────

class TestGetAllRowsDefensive:
    """order_status.py _get_all_rows() 예외 시 빈 리스트 반환 테스트."""

    @patch('src.utils.sheets.open_sheet')
    def test_get_all_rows_returns_empty_on_exception(self, mock_open_sheet):
        """open_sheet이 예외를 던지면 빈 리스트 반환."""
        mock_open_sheet.side_effect = RuntimeError('connection error')

        from src.dashboard.order_status import OrderStatusTracker
        tracker = OrderStatusTracker(sheet_id='sid', worksheet='orders')
        result = tracker._get_all_rows()

        assert result == []

    @patch('src.utils.sheets.open_sheet')
    def test_get_all_rows_returns_empty_when_only_header(self, mock_open_sheet):
        """시트에 헤더만 있으면 get_all_records()가 빈 리스트 반환."""
        from src.dashboard.order_status import OrderStatusTracker, ORDER_HEADERS

        mock_ws = MagicMock()
        mock_ws.get_all_values.return_value = [ORDER_HEADERS]
        mock_ws.get_all_records.return_value = []
        mock_open_sheet.return_value = mock_ws

        tracker = OrderStatusTracker(sheet_id='sid', worksheet='orders')
        result = tracker._get_all_rows()

        assert result == []


# ── DailySummaryGenerator.generate_summary 방어 테스트 ─────

class TestGenerateSummaryDefensive:
    """daily_summary.py generate_summary() 예외 시 기본값 반환 테스트."""

    def _make_generator(self):
        from src.dashboard.daily_summary import DailySummaryGenerator
        gen = DailySummaryGenerator.__new__(DailySummaryGenerator)
        gen.order_tracker = MagicMock()
        gen.reporter = MagicMock()
        return gen

    def test_generate_summary_with_revenue_failure(self):
        """daily_revenue() 실패 시 기본값으로 요약 생성."""
        gen = self._make_generator()
        gen.reporter.daily_revenue.side_effect = Exception('sheet error')
        gen.order_tracker.get_stats.return_value = {'total': 0, 'by_status': {}, 'by_vendor': {}, 'avg_processing_days': 0.0}
        gen.order_tracker.get_pending_orders.return_value = []

        from src.dashboard.daily_summary import DailySummaryGenerator
        # Bind the real generate_summary to our mock instance
        result = DailySummaryGenerator.generate_summary(gen, '2026-03-23')

        assert result['date'] == '2026-03-23'
        assert result['revenue']['total_orders'] == 0
        assert result['revenue']['total_revenue_krw'] == 0

    def test_generate_summary_with_stats_failure(self):
        """get_stats() 실패 시 기본값으로 요약 생성."""
        gen = self._make_generator()
        gen.reporter.daily_revenue.return_value = {'date': '2026-03-23', 'total_orders': 5}
        gen.order_tracker.get_stats.side_effect = Exception('stats error')
        gen.order_tracker.get_pending_orders.return_value = []

        from src.dashboard.daily_summary import DailySummaryGenerator
        result = DailySummaryGenerator.generate_summary(gen, '2026-03-23')

        assert result['order_stats'] == {'total': 0, 'by_status': {}, 'by_vendor': {}, 'avg_processing_days': 0.0}

    def test_generate_summary_with_pending_failure(self):
        """get_pending_orders() 실패 시 빈 리스트 사용."""
        gen = self._make_generator()
        gen.reporter.daily_revenue.return_value = {'date': '2026-03-23', 'total_orders': 5}
        gen.order_tracker.get_stats.return_value = {'total': 5, 'by_status': {}, 'by_vendor': {}, 'avg_processing_days': 0.0}
        gen.order_tracker.get_pending_orders.side_effect = Exception('pending error')

        from src.dashboard.daily_summary import DailySummaryGenerator
        result = DailySummaryGenerator.generate_summary(gen, '2026-03-23')

        assert result['pending_orders'] == []


# ── RevenueReporter._rows_for_date / _rows_for_range 방어 테스트 ─

class TestRevenueReporterDefensive:
    """revenue_report.py 행 조회 예외 시 빈 리스트 반환 테스트."""

    def test_rows_for_date_returns_empty_on_exception(self):
        """_get_all_rows() 예외 시 _rows_for_date()가 빈 리스트 반환."""
        from src.dashboard.revenue_report import RevenueReporter
        mock_tracker = MagicMock()
        mock_tracker._get_all_rows.side_effect = Exception('sheet unavailable')

        reporter = RevenueReporter(order_tracker=mock_tracker)
        from datetime import date
        result = reporter._rows_for_date(date(2026, 3, 23))

        assert result == []

    def test_rows_for_range_returns_empty_on_exception(self):
        """_get_all_rows() 예외 시 _rows_for_range()가 빈 리스트 반환."""
        from src.dashboard.revenue_report import RevenueReporter
        mock_tracker = MagicMock()
        mock_tracker._get_all_rows.side_effect = Exception('sheet unavailable')

        reporter = RevenueReporter(order_tracker=mock_tracker)
        from datetime import date
        result = reporter._rows_for_range(date(2026, 3, 1), date(2026, 3, 31))

        assert result == []
