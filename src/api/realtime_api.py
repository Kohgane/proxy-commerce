"""src/api/realtime_api.py — 실시간 대시보드 API Blueprint (Phase 67)."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

realtime_bp = Blueprint("realtime", __name__, url_prefix="/api/v1/realtime")


@realtime_bp.get("/stream")
def stream():
    """실시간 SSE 스트림 엔드포인트.

    이 배포에는 요청 간 상태를 공유하는 지속 푸시 브로커가 없어 진짜 SSE
    스트리밍은 제공하지 않는다(정직 응답 — 가짜 'connected' 반환 금지).
    실시간 갱신이 필요하면 폴링 API(`/api/v1/realtime/metrics`)를 사용한다.
    """
    return jsonify({
        "ok": False,
        "implemented": False,
        "error": "실시간 SSE 스트리밍은 이 배포에서 제공되지 않습니다. "
                 "폴링 API(/api/v1/realtime/metrics)를 사용하세요.",
    }), 501


@realtime_bp.post("/subscribe")
def subscribe():
    """채널 구독.

    주의: 현재 구독 상태는 요청 단위 인메모리라 요청 간 유지되지 않는다(데모).
    """
    body = request.get_json(silent=True) or {}
    channel = body.get("channel", "default")
    client_id = body.get("client_id", "anonymous")
    from ..realtime.event_stream import EventStream
    stream_obj = EventStream()
    stream_obj.subscribe(channel, client_id)
    return jsonify({
        "channel": channel,
        "client_id": client_id,
        "subscribed": True,
        "persistent": False,
        "note": "구독은 요청 단위 인메모리로 유지되지 않습니다(브로커 미연동).",
    })


@realtime_bp.get("/metrics")
def metrics():
    """대시보드 메트릭 조회.

    DashboardMetrics는 데모용 샘플(무작위) 값을 반환하므로 실데이터가 아님을
    응답에 명시한다(`is_demo`).
    """
    from ..realtime.dashboard_metrics import DashboardMetrics
    dm = DashboardMetrics()
    return jsonify({
        "metrics": dm.collect(),
        "is_demo": True,
        "note": "데모용 샘플 메트릭입니다(실데이터 아님). 실시간 지표 연동은 후속 작업.",
    })


@realtime_bp.get("/connections")
def connections():
    """연결 통계 조회."""
    from ..realtime.connection_manager import ConnectionManager
    mgr = ConnectionManager()
    return jsonify(mgr.get_stats())
