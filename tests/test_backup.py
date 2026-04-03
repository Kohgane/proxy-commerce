"""tests/test_backup.py — Phase 61: 백업/복원 테스트."""
from __future__ import annotations

import pytest

from src.backup import (
    BackupManager, BackupStrategy, FullBackup, IncrementalBackup,
    BackupScheduler, BackupEncryption, RestoreValidator,
)


class TestFullBackup:
    def test_create_and_restore(self):
        fb = FullBackup()
        data = {"key": "value", "num": 42}
        serialized = fb.create(data)
        assert isinstance(serialized, str)
        restored = fb.restore(serialized)
        assert restored == data

    def test_empty_data(self):
        fb = FullBackup()
        serialized = fb.create({})
        assert fb.restore(serialized) == {}


class TestIncrementalBackup:
    def test_create_captures_changes(self):
        ib = IncrementalBackup()
        data1 = {"a": 1, "b": 2}
        serialized = ib.create(data1)
        assert "changed" in serialized
        assert "deleted" in serialized

    def test_subsequent_backup_only_changed(self):
        import json
        ib = IncrementalBackup()
        ib.create({"a": 1, "b": 2})
        serialized2 = ib.create({"a": 1, "b": 3})
        snap = json.loads(serialized2)
        assert "b" in snap["changed"]
        assert "a" not in snap["changed"]


class TestBackupManager:
    def test_create_backup(self):
        manager = BackupManager()
        entry = manager.create({"x": 1})
        assert "backup_id" in entry
        assert entry["strategy"] == "FullBackup"

    def test_list_backups(self):
        manager = BackupManager()
        manager.create({"a": 1})
        manager.create({"b": 2})
        backups = manager.list_backups()
        assert len(backups) == 2

    def test_restore_backup(self):
        manager = BackupManager()
        data = {"restore_me": True}
        entry = manager.create(data)
        restored = manager.restore(entry["backup_id"])
        assert restored == data

    def test_delete_backup(self):
        manager = BackupManager()
        entry = manager.create({"d": 1})
        manager.delete(entry["backup_id"])
        assert manager.list_backups() == []

    def test_delete_missing_raises(self):
        manager = BackupManager()
        with pytest.raises(KeyError):
            manager.delete("nonexistent")

    def test_restore_missing_raises(self):
        manager = BackupManager()
        with pytest.raises(KeyError):
            manager.restore("nonexistent")


class TestBackupScheduler:
    def test_default_schedule(self):
        scheduler = BackupScheduler()
        schedule = scheduler.get_schedule()
        assert schedule["frequency"] == "daily"

    def test_set_valid_schedule(self):
        scheduler = BackupScheduler()
        result = scheduler.set_schedule("weekly")
        assert result["frequency"] == "weekly"

    def test_set_invalid_schedule(self):
        scheduler = BackupScheduler()
        with pytest.raises(ValueError):
            scheduler.set_schedule("hourly")


class TestBackupEncryption:
    def test_sign_and_verify(self):
        enc = BackupEncryption()
        signed = enc.sign("hello world")
        assert enc.verify(signed)

    def test_tampered_fails(self):
        enc = BackupEncryption()
        signed = enc.sign("hello")
        signed["data"] = "tampered"
        assert not enc.verify(signed)


class TestRestoreValidator:
    def test_valid_backup(self):
        validator = RestoreValidator()
        result = validator.validate({"key": "value"}, required_keys=["key"])
        assert result["valid"] is True

    def test_missing_required_key(self):
        validator = RestoreValidator()
        result = validator.validate({"a": 1}, required_keys=["b"])
        assert result["valid"] is False
        assert "b" in result["errors"][0]

    def test_non_dict_fails(self):
        validator = RestoreValidator()
        result = validator.validate("not a dict")
        assert result["valid"] is False

    def test_type_validation(self):
        validator = RestoreValidator()
        result = validator.validate_types({"count": "string"}, {"count": int})
        assert result["valid"] is False
