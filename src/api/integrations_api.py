"""src/api/integrations_api.py — 외부 연동 허브 API Blueprint (Phase 60)."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

integrations_bp = Blueprint("integrations", __name__, url_prefix="/api/v1/integrations")

_registry = None
_health_check = None
_scheduler = None
_log = None


def _get_services():
    global _registry, _health_check, _scheduler, _log
    if _registry is None:
        from ..integrations.integration_registry import IntegrationRegistry
        from ..integrations.connection_health_check import ConnectionHealthCheck
        from ..integrations.sync_scheduler import SyncScheduler
        from ..integrations.integration_log import IntegrationLog
        from ..integrations.slack_connector import SlackConnector
        from ..integrations.google_sheets_connector import GoogleSheetsConnector
        from ..integrations.shopify_connector import ShopifyConnector
        _registry = IntegrationRegistry()
        _health_check = ConnectionHealthCheck()
        _scheduler = SyncScheduler()
        _log = IntegrationLog()
        # 기본 커넥터 등록
        for connector in [SlackConnector(), GoogleSheetsConnector(), ShopifyConnector()]:
            _registry.register(connector)
    return _registry, _health_check, _scheduler, _log


@integrations_bp.get("/status")
def status():
    return jsonify({"status": "ok", "module": "integrations"})


@integrations_bp.get("/list")
def list_integrations():
    registry, _, _, _ = _get_services()
    return jsonify({"integrations": registry.list_all(), "active": registry.list_active()})


@integrations_bp.post("/register")
def register():
    registry, _, _, log = _get_services()
    data = request.get_json(force=True) or {}
    name = data.get("name", "")
    if not name:
        return jsonify({"error": "연동 이름 필요"}), 400
    log.record(name, True, "registered")
    return jsonify({"registered": name}), 201


@integrations_bp.get("/<name>/health")
def health(name: str):
    registry, health_check, _, log = _get_services()
    result = health_check.check_one(name, registry)
    log.record(name, result.get("status") == "ok", "health_check")
    return jsonify(result)


@integrations_bp.post("/<name>/sync")
def sync(name: str):
    registry, _, _, log = _get_services()
    connector = registry.get(name)
    if not connector:
        return jsonify({"error": "연동 없음"}), 404
    try:
        result = connector.sync()
        log.record(name, True, "sync", None)
        return jsonify({"name": name, "result": result})
    except Exception as exc:
        log.record(name, False, "sync", str(exc))
        return jsonify({"error": str(exc)}), 500


@integrations_bp.get("/logs")
def get_logs():
    _, _, _, log = _get_services()
    name = request.args.get("name")
    return jsonify({"logs": log.get_log(name=name)})


@integrations_bp.get("/schedule")
def get_schedule():
    _, _, scheduler, _ = _get_services()
    return jsonify({"schedule": scheduler.get_schedule()})
