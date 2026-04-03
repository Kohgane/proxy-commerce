"""src/api/events_api.py — 이벤트 소싱 API Blueprint (Phase 64)."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

events_bp = Blueprint("events", __name__, url_prefix="/api/v1/events")

_store = None
_projection = None
_replay = None


def _get_services():
    global _store, _projection, _replay
    if _store is None:
        from ..event_sourcing.event_store import EventStore
        from ..event_sourcing.event_projection import EventProjection
        from ..event_sourcing.event_replay import EventReplay
        _store = EventStore()
        _projection = EventProjection()
        _replay = EventReplay()
    return _store, _projection, _replay


@events_bp.get("/status")
def status():
    return jsonify({"status": "ok", "module": "events"})


@events_bp.get("/list")
def list_events():
    store, _, _ = _get_services()
    return jsonify({"events": [e.to_dict() for e in store.get_all()]})


@events_bp.get("/<aggregate_id>")
def get_events(aggregate_id: str):
    store, _, _ = _get_services()
    events = store.get_events(aggregate_id)
    return jsonify({"aggregate_id": aggregate_id, "events": [e.to_dict() for e in events]})


@events_bp.post("/append")
def append_event():
    store, _, _ = _get_services()
    data = request.get_json(force=True) or {}
    event_type = data.get("event_type", "")
    aggregate_id = data.get("aggregate_id", "")
    if not event_type or not aggregate_id:
        return jsonify({"error": "event_type, aggregate_id 필요"}), 400
    from ..event_sourcing.event import Event
    event = Event(event_type=event_type, aggregate_id=aggregate_id, data=data.get("data", {}))
    store.append(event)
    return jsonify(event.to_dict()), 201


@events_bp.post("/replay")
def replay_events():
    store, _, replay = _get_services()
    data = request.get_json(force=True) or {}
    aggregate_id = data.get("aggregate_id", "")
    until_version = data.get("until_version")
    events = store.get_events(aggregate_id)
    replayed = replay.replay(events, until_version=until_version)
    return jsonify({"aggregate_id": aggregate_id, "events": [e.to_dict() for e in replayed]})


@events_bp.get("/projections")
def get_projections():
    store, projection, _ = _get_services()
    proj = projection.project(store.get_all())
    return jsonify({"projections": proj})
