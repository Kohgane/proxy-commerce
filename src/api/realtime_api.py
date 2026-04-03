"""src/api/realtime_api.py — 실시간 대시보드 API Blueprint (Phase 67)."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

realtime_bp = Blueprint("realtime", __name__, url_prefix="/api/v1/realtime")


@realtime_bp.get("/stream")
def stream():
    """SSE 스트림 엔드포인트 (모의)."""
    return jsonify({"type": "stream", "status": "connected", "message": "SSE stream mock"})


@realtime_bp.post("/subscribe")
def subscribe():
    """채널 구독."""
    body = request.get_json(silent=True) or {}
    channel = body.get("channel", "default")
    client_id = body.get("client_id", "anonymous")
    from ..realtime.event_stream import EventStream
    stream_obj = EventStream()
    stream_obj.subscribe(channel, client_id)
    return jsonify({"channel": channel, "client_id": client_id, "subscribed": True})


@realtime_bp.get("/metrics")
def metrics():
    """대시보드 메트릭 조회."""
    from ..realtime.dashboard_metrics import DashboardMetrics
    dm = DashboardMetrics()
    return jsonify(dm.collect())


@realtime_bp.get("/connections")
def connections():
    """연결 통계 조회."""
    from ..realtime.connection_manager import ConnectionManager
    mgr = ConnectionManager()
    return jsonify(mgr.get_stats())
