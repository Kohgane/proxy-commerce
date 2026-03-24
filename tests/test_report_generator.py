"""tests/test_report_generator.py — 리포트 생성기 테스트."""

import datetime
from unittest.mock import MagicMock, patch

import pytest

from src.export.report_generator import ReportGenerator


@pytest.fixture
def mock_orders():
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    yesterday = (now - datetime.timedelta(days=1)).isoformat()
    return [
        {
            "order_id": "10001", "order_date": yesterday,
            "sell_price_krw": 370000, "margin_pct": 18.0,
            "vendor": "PORTER", "status": "paid",
        },
        {
            "order_id": "10002", "order_date": yesterday,
            "sell_price_krw": 420000, "margin_pct": 20.0,
            "vendor": "MEMO_PARIS", "status": "shipped",
        },
    ]


@pytest.fixture
def mock_catalog():
    return [
        {"sku": "PTR-001", "margin_pct": 18.0, "stock": 5, "stock_status": "in_stock"},
        {"sku": "MMP-001", "margin_pct": 20.0, "stock": 1, "stock_status": "low_stock"},
    ]


class TestDailyReport:
    def test_daily_report_contains_date(self, mock_orders, mock_catalog):
        """일일 리포트에 날짜 포함 확인."""
        with patch("src.export.report_generator.open_sheet") as mock_open:
            ws = MagicMock()
            ws.get_all_records.return_value = mock_orders
            mock_open.return_value = ws
            gen = ReportGenerator()
            report = gen.daily_report(date=datetime.date(2026, 3, 1))

        assert "2026-03-01" in report
        assert "일일 운영 리포트" in report

    def test_daily_report_shows_revenue(self, mock_orders, mock_catalog):
        """일일 리포트에 매출 포함 확인."""
        with patch("src.export.report_generator.open_sheet") as mock_open:
            ws = MagicMock()
            ws.get_all_records.return_value = mock_orders
            mock_open.return_value = ws
            gen = ReportGenerator()
            report = gen.daily_report(date=datetime.date.today() - datetime.timedelta(days=1))

        assert "총 매출" in report


class TestWeeklyReport:
    def test_weekly_report_structure(self, mock_orders, mock_catalog):
        """주간 리포트 구조 확인."""
        with patch("src.export.report_generator.open_sheet") as mock_open:
            ws = MagicMock()
            ws.get_all_records.return_value = mock_orders
            mock_open.return_value = ws
            gen = ReportGenerator()
            report = gen.weekly_report()

        assert "주간 종합 리포트" in report
        assert "벤더별" in report


class TestMonthlyReport:
    def test_monthly_report_structure(self, mock_orders, mock_catalog):
        """월간 리포트 구조 확인."""
        with patch("src.export.report_generator.open_sheet") as mock_open:
            ws = MagicMock()
            ws.get_all_records.return_value = mock_orders
            mock_open.return_value = ws
            gen = ReportGenerator()
            report = gen.monthly_report()

        assert "월간 운영 리포트" in report


class TestMarginAnalysisReport:
    def test_margin_report_shows_top5(self, mock_catalog):
        """마진 분석 리포트에 TOP 5 포함 확인."""
        with patch("src.export.report_generator.open_sheet") as mock_open:
            ws = MagicMock()
            ws.get_all_records.return_value = mock_catalog
            mock_open.return_value = ws
            gen = ReportGenerator()
            report = gen.margin_analysis_report()

        assert "마진 분석 리포트" in report
        assert "고마진" in report

    def test_margin_report_empty_catalog(self):
        """빈 카탈로그에 대한 마진 리포트 테스트."""
        with patch("src.export.report_generator.open_sheet") as mock_open:
            ws = MagicMock()
            ws.get_all_records.return_value = []
            mock_open.return_value = ws
            gen = ReportGenerator()
            report = gen.margin_analysis_report()

        assert "없음" in report


class TestSendToTelegram:
    def test_send_to_telegram_success(self):
        """텔레그램 발송 성공 테스트."""
        with patch("src.export.report_generator.send_tele") as mock_tele:
            mock_tele.return_value = None
            gen = ReportGenerator()
            result = gen.send_to_telegram("테스트 메시지")

        assert result is True

    def test_send_to_telegram_failure(self):
        """텔레그램 발송 실패 테스트."""
        with patch("src.export.report_generator.send_tele", side_effect=Exception("conn error")):
            gen = ReportGenerator()
            result = gen.send_to_telegram("테스트 메시지")

        assert result is False
