"""tests/test_scheduled_export.py — 정기 내보내기 스케줄러 테스트."""

import datetime
from unittest.mock import MagicMock, patch

import pytest

from src.export.scheduled_export import ScheduledExport


class TestScheduledExportDaily:
    def test_run_daily_disabled(self, monkeypatch):
        """EXPORT_ENABLED=0 시 일일 내보내기 건너뜀."""
        monkeypatch.setenv("EXPORT_ENABLED", "0")
        with patch("src.export.scheduled_export._EXPORT_ENABLED", False):
            scheduler = ScheduledExport()
            result = scheduler.run_daily()
        assert result is False

    def test_run_daily_daily_disabled(self, monkeypatch):
        """EXPORT_DAILY_ENABLED=0 시 일일 내보내기 건너뜀."""
        monkeypatch.setenv("EXPORT_DAILY_ENABLED", "0")
        with patch("src.export.scheduled_export._DAILY_ENABLED", False):
            scheduler = ScheduledExport()
            result = scheduler.run_daily()
        assert result is False

    def test_run_daily_success(self):
        """일일 내보내기 성공 테스트."""
        with patch("src.export.scheduled_export._EXPORT_ENABLED", True), \
             patch("src.export.scheduled_export._DAILY_ENABLED", True), \
             patch("src.export.csv_exporter.open_sheet") as mock_sheet, \
             patch("src.export.report_generator.send_tele") as mock_tele, \
             patch("src.export.scheduled_export.open_sheet") as mock_sheet2:
            ws = MagicMock()
            ws.get_all_records.return_value = []
            ws.append_row.return_value = None
            mock_sheet.return_value = ws
            mock_sheet2.return_value = ws
            mock_tele.return_value = None

            scheduler = ScheduledExport()
            result = scheduler.run_daily()

        assert result is True


class TestScheduledExportWeekly:
    def test_run_weekly_disabled(self, monkeypatch):
        """EXPORT_WEEKLY_ENABLED=0 시 주간 내보내기 건너뜀."""
        with patch("src.export.scheduled_export._EXPORT_ENABLED", True), \
             patch("src.export.scheduled_export._WEEKLY_ENABLED", False):
            scheduler = ScheduledExport()
            result = scheduler.run_weekly()
        assert result is False

    def test_run_weekly_success(self):
        """주간 리포트 발송 성공 테스트."""
        with patch("src.export.scheduled_export._EXPORT_ENABLED", True), \
             patch("src.export.scheduled_export._WEEKLY_ENABLED", True), \
             patch("src.export.report_generator.open_sheet") as mock_sheet, \
             patch("src.export.report_generator.send_tele") as mock_tele:
            ws = MagicMock()
            ws.get_all_records.return_value = []
            mock_sheet.return_value = ws
            mock_tele.return_value = None

            scheduler = ScheduledExport()
            result = scheduler.run_weekly()

        assert result is True
