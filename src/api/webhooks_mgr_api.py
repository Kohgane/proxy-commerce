"""src/api/webhooks_mgr_api.py — 웹훅 관리 API Blueprint (Phase 51)."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

webhooks_mgr_bp = Blueprint("webhooks_mgr", __name__, url_prefix="/api/v1/webhooks")

_registry = None
_dispatcher = None
_log = None


def _get_services():
    global _registry, _dispatcher, _log
    if _registry is None:
        from ..webhook_manager.webhook_registry import WebhookRegistry
        from ..webhook_manager.webhook_dispatcher import WebhookDispatcher
        from ..webhook_manager.delivery_log import DeliveryLog
        _log = DeliveryLog()
        _registry = WebhookRegistry()
        _dispatcher = WebhookDispatcher(registry=_registry, log=_log)
    return _registry, _dispatcher, _log


@webhooks_mgr_bp.get("/status")
def status():
    return jsonify({"status": "ok", "module": "webhook_manager"})


@webhooks_mgr_bp.get("/")
def list_webhooks():
    registry, _, _ = _get_services()
    event = request.args.get("event")
    return jsonify(registry.list(event=event))


@webhooks_mgr_bp.post("/")
def register_webhook():
    registry, _, _ = _get_services()
    data = request.get_json(force=True) or {}
    try:
        webhook = registry.register(
            url=data.get("url", ""),
            events=data.get("events", []),
            secret=data.get("secret", ""),
            name=data.get("name", ""),
        )
        return jsonify(webhook), 201
    except ValueError:
        return jsonify({"error": "url은 필수입니다."}), 400


@webhooks_mgr_bp.get("/<webhook_id>")
def get_webhook(webhook_id: str):
    registry, _, _ = _get_services()
    webhook = registry.get(webhook_id)
    if not webhook:
        return jsonify({"error": "웹훅 없음"}), 404
    return jsonify(webhook)


@webhooks_mgr_bp.put("/<webhook_id>")
def update_webhook(webhook_id: str):
    registry, _, _ = _get_services()
    data = request.get_json(force=True) or {}
    try:
        return jsonify(registry.update(webhook_id, **data))
    except KeyError:
        return jsonify({"error": "웹훅 없음"}), 404


@webhooks_mgr_bp.delete("/<webhook_id>")
def delete_webhook(webhook_id: str):
    registry, _, _ = _get_services()
    deleted = registry.delete(webhook_id)
    if not deleted:
        return jsonify({"error": "웹훅 없음"}), 404
    return jsonify({"deleted": True})


@webhooks_mgr_bp.post("/<webhook_id>/test")
def test_webhook(webhook_id: str):
    _, dispatcher, _ = _get_services()
    try:
        result = dispatcher.test_webhook(webhook_id)
        return jsonify(result)
    except KeyError:
        return jsonify({"error": "웹훅 없음"}), 404
    except Exception:
        return jsonify({"error": "웹훅 테스트 중 오류가 발생했습니다."}), 500


@webhooks_mgr_bp.get("/<webhook_id>/deliveries")
def get_deliveries(webhook_id: str):
    _, _, log = _get_services()
    status_filter = request.args.get("status")
    limit = int(request.args.get("limit", 50))
    deliveries = log.get_deliveries(webhook_id, status=status_filter, limit=limit)
    return jsonify(deliveries)
