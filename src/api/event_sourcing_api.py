"""src/api/event_sourcing_api.py — 이벤트 소싱 API Blueprint (Phase 77)."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

event_sourcing_bp = Blueprint("event_sourcing", __name__, url_prefix="/api/v1/events")


@event_sourcing_bp.get("/")
def list_events():
    """이벤트 목록 조회."""
    from ..event_sourcing import EventStore
    store = EventStore()
    return jsonify([e.to_dict() for e in store.get_all()])


@event_sourcing_bp.post("/store")
def store_event():
    """이벤트 저장."""
    body = request.get_json(silent=True) or {}
    event_type = body.get("event_type", "")
    aggregate_id = body.get("aggregate_id", "")
    if not event_type or not aggregate_id:
        return jsonify({"error": "event_type, aggregate_id 필드가 필요합니다"}), 400
    from ..event_sourcing import Event, EventStore
    store = EventStore()
    event = Event(
        event_type=event_type,
        aggregate_id=aggregate_id,
        data=body.get("data", {}),
        version=body.get("version", 1),
    )
    store.append(event)
    return jsonify(event.to_dict()), 201


@event_sourcing_bp.get("/aggregates/<aggregate_id>")
def get_aggregate_events(aggregate_id: str):
    """특정 애그리거트 이벤트 목록."""
    from ..event_sourcing import EventStore
    store = EventStore()
    events = store.get_events(aggregate_id)
    return jsonify({
        "aggregate_id": aggregate_id,
        "events": [e.to_dict() for e in events],
        "count": len(events),
    })


@event_sourcing_bp.post("/aggregates/<aggregate_id>/replay")
def replay_events(aggregate_id: str):
    """이벤트 리플레이."""
    body = request.get_json(silent=True) or {}
    until_version = body.get("until_version")
    from ..event_sourcing import EventStore, EventReplay
    store = EventStore()
    replay = EventReplay()
    events = store.get_events(aggregate_id)
    if until_version is not None:
        replayed = replay.replay_until_version(events, until_version=int(until_version))
    else:
        replayed = replay.replay(events)
    return jsonify({
        "aggregate_id": aggregate_id,
        "replayed_count": len(replayed),
        "events": [e.to_dict() for e in replayed],
    })


@event_sourcing_bp.get("/snapshots/<aggregate_id>")
def get_snapshots(aggregate_id: str):
    """스냅샷 목록 조회."""
    from ..event_sourcing import SnapshotStore
    store = SnapshotStore()
    snaps = store.get_all(aggregate_id)
    return jsonify({
        "aggregate_id": aggregate_id,
        "snapshots": [s.to_dict() for s in snaps],
    })


@event_sourcing_bp.get("/projections")
def get_projections():
    """이벤트 프로젝션 조회."""
    from ..event_sourcing import EventStore, EventProjection
    store = EventStore()
    projection = EventProjection()
    result = projection.project(store.get_all())
    return jsonify(result)
