"""src/api/backup_api.py — 백업/복원 API Blueprint (Phase 61)."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

backup_bp = Blueprint("backup", __name__, url_prefix="/api/v1/backup")

_manager = None
_scheduler = None


def _get_services():
    global _manager, _scheduler
    if _manager is None:
        from ..backup.backup_manager import BackupManager
        from ..backup.backup_scheduler import BackupScheduler
        _manager = BackupManager()
        _scheduler = BackupScheduler()
    return _manager, _scheduler


@backup_bp.get("/status")
def status():
    return jsonify({"status": "ok", "module": "backup"})


@backup_bp.get("/list")
def list_backups():
    manager, _ = _get_services()
    return jsonify({"backups": manager.list_backups()})


@backup_bp.post("/create")
def create_backup():
    manager, _ = _get_services()
    data = request.get_json(force=True) or {}
    strategy_name = data.get("strategy", "full")
    payload = data.get("data", {})

    if strategy_name == "incremental":
        from ..backup.incremental_backup import IncrementalBackup
        strategy = IncrementalBackup()
    else:
        from ..backup.full_backup import FullBackup
        strategy = FullBackup()

    entry = manager.create(payload, strategy=strategy)
    return jsonify(entry), 201


@backup_bp.post("/restore/<backup_id>")
def restore_backup(backup_id: str):
    manager, _ = _get_services()
    try:
        restored = manager.restore(backup_id)
        return jsonify({"backup_id": backup_id, "restored": restored})
    except KeyError:
        return jsonify({"error": "백업 없음"}), 404


@backup_bp.delete("/<backup_id>")
def delete_backup(backup_id: str):
    manager, _ = _get_services()
    try:
        manager.delete(backup_id)
        return jsonify({"deleted": backup_id})
    except KeyError:
        return jsonify({"error": "백업 없음"}), 404


@backup_bp.get("/schedule")
def get_schedule():
    _, scheduler = _get_services()
    return jsonify(scheduler.get_schedule())


@backup_bp.post("/schedule")
def set_schedule():
    _, scheduler = _get_services()
    data = request.get_json(force=True) or {}
    frequency = data.get("frequency", "daily")
    try:
        schedule = scheduler.set_schedule(frequency)
        return jsonify(schedule)
    except ValueError:
        return jsonify({"error": "유효하지 않은 주기 값입니다. (daily/weekly/monthly)"}), 400
