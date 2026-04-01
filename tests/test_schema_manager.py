"""tests/test_schema_manager.py — 스키마 버전 관리 테스트."""
import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.migration.schema_manager import SchemaManager  # noqa: E402


def _make_mock_client(version_value=None):
    """gspread 클라이언트 목 생성."""
    mock_ws = MagicMock()
    mock_ws.cell.return_value.value = version_value
    mock_ws.update = MagicMock()

    mock_ss = MagicMock()
    mock_ss.worksheet.return_value = mock_ws
    mock_ss.add_worksheet.return_value = mock_ws
    mock_ss.worksheets.return_value = [mock_ws]

    mock_client = MagicMock()
    mock_client.open_by_key.return_value = mock_ss
    return mock_client, mock_ss, mock_ws


class TestSchemaManagerGetVersion:
    def test_get_current_version_returns_value(self):
        client, _, ws = _make_mock_client("001")
        mgr = SchemaManager(client, "sheet_id")
        assert mgr.get_current_version() == "001"

    def test_get_current_version_no_client_returns_none(self):
        mgr = SchemaManager(None, "sheet_id")
        assert mgr.get_current_version() is None

    def test_get_current_version_empty_cell_returns_none(self):
        client, _, ws = _make_mock_client(None)
        mgr = SchemaManager(client, "sheet_id")
        assert mgr.get_current_version() is None

    def test_get_current_version_worksheet_not_found(self):
        """워크시트가 없으면 None 반환."""
        mock_ss = MagicMock()
        mock_ss.worksheet.side_effect = Exception("워크시트 없음")
        mock_client = MagicMock()
        mock_client.open_by_key.return_value = mock_ss
        mgr = SchemaManager(mock_client, "sheet_id")
        assert mgr.get_current_version() is None


class TestSchemaManagerNeedsMigration:
    def test_needs_migration_when_no_version(self):
        mgr = SchemaManager(None, "sheet_id")
        # 클라이언트 없으면 버전 알 수 없음 → 마이그레이션 필요
        assert mgr.needs_migration() is True

    def test_needs_migration_when_older_version(self):
        client, _, ws = _make_mock_client("000")
        mgr = SchemaManager(client, "sheet_id")
        assert mgr.needs_migration() is True

    def test_no_migration_needed_when_current(self):
        current = SchemaManager.CURRENT_SCHEMA_VERSION
        client, _, ws = _make_mock_client(current)
        mgr = SchemaManager(client, "sheet_id")
        assert mgr.needs_migration() is False


class TestSchemaManagerUpdateVersion:
    def test_update_version_success(self):
        client, _, ws = _make_mock_client("001")
        mgr = SchemaManager(client, "sheet_id")
        result = mgr.update_version("002", "두 번째 마이그레이션")
        assert result is True
        ws.update.assert_called()

    def test_update_version_no_client_returns_false(self):
        mgr = SchemaManager(None, "sheet_id")
        assert mgr.update_version("002") is False

    def test_ensure_worksheet_creates_if_missing(self):
        mock_ss = MagicMock()
        mock_ws = MagicMock()
        mock_ss.worksheet.side_effect = Exception("없음")
        mock_ss.add_worksheet.return_value = mock_ws
        mock_client = MagicMock()
        mock_client.open_by_key.return_value = mock_ss
        mgr = SchemaManager(mock_client, "sheet_id")
        result = mgr.ensure_worksheet()
        assert result is True
        mock_ss.add_worksheet.assert_called()
