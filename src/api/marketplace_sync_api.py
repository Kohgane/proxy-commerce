"""src/api/marketplace_sync_api.py — 마켓플레이스 동기화 API Blueprint (Phase 71)."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

marketplace_sync_bp = Blueprint("marketplace_sync", __name__, url_prefix="/api/v1/marketplace-sync")


@marketplace_sync_bp.post("/sync")
def sync():
    """마켓플레이스 동기화 실행."""
    body = request.get_json(silent=True) or {}
    marketplace = body.get("marketplace", "coupang")
    job_type = body.get("job_type", "all")
    from ..marketplace_sync.sync_manager import MarketplaceSyncManager
    mgr = MarketplaceSyncManager()
    job = mgr.sync(marketplace, job_type)
    return jsonify(job.to_dict())


@marketplace_sync_bp.get("/status")
def status():
    """동기화 현황 조회."""
    from ..marketplace_sync.sync_manager import MarketplaceSyncManager
    mgr = MarketplaceSyncManager()
    return jsonify(mgr.get_status())


@marketplace_sync_bp.get("/schedule")
def schedule():
    """동기화 스케줄 조회."""
    from ..marketplace_sync.sync_scheduler import SyncScheduler
    scheduler = SyncScheduler()
    return jsonify(scheduler.list_schedules())


@marketplace_sync_bp.get("/logs")
def logs():
    """동기화 로그 조회."""
    from ..marketplace_sync.sync_log import SyncLog
    log = SyncLog()
    return jsonify(log.get_logs())


@marketplace_sync_bp.get("/conflicts")
def conflicts():
    """충돌 목록 조회 (모의)."""
    return jsonify({"conflicts": [], "message": "충돌 없음"})
