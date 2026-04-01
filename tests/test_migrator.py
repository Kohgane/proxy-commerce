"""tests/test_migrator.py — 마이그레이션 실행/롤백 테스트."""
import os
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.migration.migrator import Migrator, MigrationRecord  # noqa: E402
from src.migration.versions.v001_initial_schema import WORKSHEET_SCHEMAS, VERSION  # noqa: E402


# ── 더미 마이그레이션 모듈 생성 헬퍼 ─────────────────────────────

def _make_migration_module(version: str, description: str, up_raises=False, down_raises=False):
    """테스트용 마이그레이션 모듈을 동적으로 생성한다."""
    mod = types.ModuleType(f"v{version}_test")
    mod.VERSION = version
    mod.DESCRIPTION = description

    def up(client, sheet_id):
        if up_raises:
            raise RuntimeError(f"v{version} up 실패")

    def down(client, sheet_id):
        if down_raises:
            raise RuntimeError(f"v{version} down 실패")

    mod.up = up
    mod.down = down
    return mod


class TestMigrationRecord:
    def test_success_repr(self):
        rec = MigrationRecord("001", "초기 스키마", success=True)
        assert "✓" in repr(rec)

    def test_failure_repr(self):
        rec = MigrationRecord("001", "초기 스키마", success=False, error="오류")
        assert "✗" in repr(rec)


class TestMigratorDiscover:
    def test_discover_finds_v001(self):
        """실제 v001_initial_schema 모듈이 발견되어야 한다."""
        migrator = Migrator()
        migrations = migrator.discover_migrations()
        versions = [m["version"] for m in migrations]
        assert "001" in versions

    def test_discover_sorted_ascending(self):
        migrator = Migrator()
        migrations = migrator.discover_migrations()
        versions = [m["version"] for m in migrations]
        assert versions == sorted(versions)


class TestMigratorRun:
    def test_dry_run_returns_records_without_executing(self):
        """드라이런 모드에서는 실제 실행 없이 이력만 반환한다."""
        migrator = Migrator(sheets_client=None, sheet_id="fake_id")

        # 스키마 매니저가 버전 없음을 반환하도록 패치
        with patch("src.migration.migrator.SchemaManager") as MockMgr:
            mock_mgr_instance = MockMgr.return_value
            mock_mgr_instance.get_current_version.return_value = None
            mock_mgr_instance.update_version = MagicMock()

            mod = _make_migration_module("001", "테스트")
            with patch.object(migrator, "discover_migrations", return_value=[
                {"version": "001", "description": "테스트", "module": mod, "module_name": "v001_test"}
            ]):
                records = migrator.run(dry_run=True)

        assert len(records) == 1
        assert records[0].success is True
        mock_mgr_instance.update_version.assert_not_called()

    def test_run_calls_up_function(self):
        """run()은 마이그레이션 모듈의 up() 함수를 호출해야 한다."""
        called = []
        mod = _make_migration_module("001", "테스트")
        original_up = mod.up

        def tracked_up(client, sheet_id):
            called.append(True)
            original_up(client, sheet_id)
        mod.up = tracked_up

        migrator = Migrator(sheets_client=MagicMock(), sheet_id="fake_id")

        with patch("src.migration.migrator.SchemaManager") as MockMgr:
            mock_mgr_instance = MockMgr.return_value
            mock_mgr_instance.get_current_version.return_value = None
            mock_mgr_instance.update_version = MagicMock()

            with patch.object(migrator, "discover_migrations", return_value=[
                {"version": "001", "description": "테스트", "module": mod, "module_name": "v001_test"}
            ]):
                records = migrator.run(dry_run=False)

        assert len(called) == 1
        assert records[0].success is True

    def test_run_up_failure_stops_execution(self):
        """up() 실패 시 이후 마이그레이션 실행을 중단해야 한다."""
        mod1 = _make_migration_module("001", "실패", up_raises=True)
        mod2 = _make_migration_module("002", "성공")
        called_v002 = []
        original_up2 = mod2.up

        def tracked_up2(client, sheet_id):
            called_v002.append(True)
            original_up2(client, sheet_id)
        mod2.up = tracked_up2

        migrator = Migrator(sheets_client=MagicMock(), sheet_id="fake_id")

        with patch("src.migration.migrator.SchemaManager") as MockMgr:
            mock_mgr_instance = MockMgr.return_value
            mock_mgr_instance.get_current_version.return_value = None
            mock_mgr_instance.update_version = MagicMock()

            with patch.object(migrator, "discover_migrations", return_value=[
                {"version": "001", "description": "실패", "module": mod1, "module_name": "v001_test"},
                {"version": "002", "description": "성공", "module": mod2, "module_name": "v002_test"},
            ]):
                records = migrator.run(dry_run=False)

        assert records[0].success is False
        assert len(called_v002) == 0  # v002는 실행되지 않아야 함

    def test_no_migration_when_up_to_date(self):
        """최신 버전이면 마이그레이션을 실행하지 않는다."""
        migrator = Migrator(sheets_client=None, sheet_id="fake_id")

        with patch("src.migration.migrator.SchemaManager") as MockMgr:
            mock_mgr_instance = MockMgr.return_value
            mock_mgr_instance.get_current_version.return_value = "999"  # 미래 버전

            records = migrator.run()

        assert records == []


class TestMigratorRollback:
    def test_rollback_dry_run(self):
        migrator = Migrator(sheets_client=None, sheet_id="fake_id")
        mod = _make_migration_module("001", "테스트")

        with patch("src.migration.migrator.SchemaManager") as MockMgr:
            mock_mgr_instance = MockMgr.return_value
            mock_mgr_instance.get_current_version.return_value = "001"
            mock_mgr_instance.update_version = MagicMock()

            with patch.object(migrator, "discover_migrations", return_value=[
                {"version": "001", "description": "테스트", "module": mod, "module_name": "v001_test"}
            ]):
                records = migrator.rollback(steps=1, dry_run=True)

        assert len(records) == 1
        assert records[0].success is True


class TestV001InitialSchema:
    def test_version_constant(self):
        assert VERSION == "001"

    def test_worksheet_schemas_defined(self):
        assert "catalog" in WORKSHEET_SCHEMAS
        assert "orders" in WORKSHEET_SCHEMAS
        assert "fx_history" in WORKSHEET_SCHEMAS
        assert "fx_rates" in WORKSHEET_SCHEMAS
        assert "audit_log" in WORKSHEET_SCHEMAS
        assert "daily_exports" in WORKSHEET_SCHEMAS

    def test_catalog_headers(self):
        headers = WORKSHEET_SCHEMAS["catalog"]
        assert "sku" in headers
        assert "buy_price" in headers
        assert "vendor" in headers

    def test_orders_headers(self):
        headers = WORKSHEET_SCHEMAS["orders"]
        assert "order_id" in headers
        assert "status" in headers
        assert "total_krw" in headers

    def test_up_raises_without_client(self):
        from src.migration.versions.v001_initial_schema import up
        with pytest.raises(ValueError):
            up(None, "sheet_id")

    def test_down_raises_without_client(self):
        from src.migration.versions.v001_initial_schema import down
        with pytest.raises(ValueError):
            down(None, "sheet_id")
