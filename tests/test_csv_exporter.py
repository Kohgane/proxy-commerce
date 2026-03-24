"""tests/test_csv_exporter.py — CSV 내보내기 테스트."""

import csv
import datetime
import io
from unittest.mock import MagicMock, patch

import pytest

from src.export.csv_exporter import CsvExporter, ORDER_COLUMNS, INVENTORY_COLUMNS


@pytest.fixture
def mock_orders_ws(sample_order_rows):
    ws = MagicMock()
    ws.get_all_records.return_value = sample_order_rows
    return ws


@pytest.fixture
def mock_catalog_ws(sample_catalog_rows):
    ws = MagicMock()
    ws.get_all_records.return_value = sample_catalog_rows
    return ws


class TestCsvExporterEncoding:
    def test_bom_utf8_encoding(self, sample_order_rows):
        """BOM 포함 UTF-8 인코딩 검증."""
        with patch("src.export.csv_exporter.open_sheet") as mock_open:
            ws = MagicMock()
            ws.get_all_records.return_value = sample_order_rows
            mock_open.return_value = ws
            exporter = CsvExporter()
            csv_bytes = exporter.export_orders()

        # BOM 시그니처 확인 (0xEF 0xBB 0xBF)
        assert csv_bytes[:3] == b'\xef\xbb\xbf'

    def test_korean_data_encoding(self, sample_order_rows):
        """한국어 데이터 인코딩 테스트."""
        with patch("src.export.csv_exporter.open_sheet") as mock_open:
            ws = MagicMock()
            ws.get_all_records.return_value = sample_order_rows
            mock_open.return_value = ws
            exporter = CsvExporter()
            csv_bytes = exporter.export_orders()

        decoded = csv_bytes.decode("utf-8-sig")
        assert "홍길동" in decoded


class TestCsvExporterOrders:
    def test_export_orders_columns(self, sample_order_rows):
        """주문 CSV 열 순서 검증."""
        with patch("src.export.csv_exporter.open_sheet") as mock_open:
            ws = MagicMock()
            ws.get_all_records.return_value = sample_order_rows
            mock_open.return_value = ws
            exporter = CsvExporter()
            csv_bytes = exporter.export_orders()

        reader = csv.DictReader(io.StringIO(csv_bytes.decode("utf-8-sig")))
        assert list(reader.fieldnames) == ORDER_COLUMNS

    def test_export_orders_row_count(self, sample_order_rows):
        """주문 CSV 행 수 검증."""
        with patch("src.export.csv_exporter.open_sheet") as mock_open:
            ws = MagicMock()
            ws.get_all_records.return_value = sample_order_rows
            mock_open.return_value = ws
            exporter = CsvExporter()
            csv_bytes = exporter.export_orders()

        reader = csv.DictReader(io.StringIO(csv_bytes.decode("utf-8-sig")))
        rows = list(reader)
        assert len(rows) == len(sample_order_rows)

    def test_export_orders_date_filter(self, sample_order_rows):
        """날짜 필터 테스트."""
        with patch("src.export.csv_exporter.open_sheet") as mock_open:
            ws = MagicMock()
            ws.get_all_records.return_value = sample_order_rows
            mock_open.return_value = ws
            exporter = CsvExporter()
            # 2026-03-01만 포함
            csv_bytes = exporter.export_orders(
                date_from=datetime.date(2026, 3, 1),
                date_to=datetime.date(2026, 3, 1),
            )

        reader = csv.DictReader(io.StringIO(csv_bytes.decode("utf-8-sig")))
        rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["order_id"] == "10001"

    def test_export_orders_status_filter(self, sample_order_rows):
        """상태 필터 테스트."""
        with patch("src.export.csv_exporter.open_sheet") as mock_open:
            ws = MagicMock()
            ws.get_all_records.return_value = sample_order_rows
            mock_open.return_value = ws
            exporter = CsvExporter()
            csv_bytes = exporter.export_orders(status="shipped")

        reader = csv.DictReader(io.StringIO(csv_bytes.decode("utf-8-sig")))
        rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["order_id"] == "10002"


class TestCsvExporterInventory:
    def test_export_inventory_columns(self, sample_catalog_rows):
        """재고 CSV 열 순서 검증."""
        with patch("src.export.csv_exporter.open_sheet") as mock_open:
            ws = MagicMock()
            ws.get_all_records.return_value = sample_catalog_rows
            mock_open.return_value = ws
            exporter = CsvExporter()
            csv_bytes = exporter.export_inventory()

        reader = csv.DictReader(io.StringIO(csv_bytes.decode("utf-8-sig")))
        assert list(reader.fieldnames) == INVENTORY_COLUMNS

    def test_export_inventory_empty(self):
        """빈 재고 CSV 테스트."""
        with patch("src.export.csv_exporter.open_sheet") as mock_open:
            ws = MagicMock()
            ws.get_all_records.return_value = []
            mock_open.return_value = ws
            exporter = CsvExporter()
            csv_bytes = exporter.export_inventory()

        reader = csv.DictReader(io.StringIO(csv_bytes.decode("utf-8-sig")))
        rows = list(reader)
        assert len(rows) == 0


class TestCsvExporterAudit:
    def test_export_audit_recent_days(self):
        """감사 로그 날짜 필터 테스트."""
        now = datetime.datetime.now(tz=datetime.timezone.utc)
        audit_rows = [
            {
                "timestamp": (now - datetime.timedelta(days=1)).isoformat(),
                "event_type": "order.created",
                "actor": "system",
                "resource": "order:1",
                "details": "{}",
                "ip_address": "1.2.3.4",
            },
            {
                "timestamp": (now - datetime.timedelta(days=40)).isoformat(),
                "event_type": "order.shipped",
                "actor": "system",
                "resource": "order:2",
                "details": "{}",
                "ip_address": "1.2.3.4",
            },
        ]
        with patch("src.export.csv_exporter.open_sheet") as mock_open:
            ws = MagicMock()
            ws.get_all_records.return_value = audit_rows
            mock_open.return_value = ws
            exporter = CsvExporter()
            csv_bytes = exporter.export_audit(days=30)

        reader = csv.DictReader(io.StringIO(csv_bytes.decode("utf-8-sig")))
        rows = list(reader)
        # 40일 전 항목은 제외
        assert len(rows) == 1
