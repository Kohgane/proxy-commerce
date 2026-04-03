"""src/api/email_api.py — 이메일 서비스 API Blueprint (Phase 56)."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

email_bp = Blueprint("email_service", __name__, url_prefix="/api/v1/email")

_provider = None
_queue = None
_tracker = None


def _get_services():
    global _provider, _queue, _tracker
    if _provider is None:
        from ..email_service.smtp_provider import SMTPProvider
        from ..email_service.email_queue import EmailQueue
        from ..email_service.email_tracker import EmailTracker
        _provider = SMTPProvider()
        _queue = EmailQueue()
        _tracker = EmailTracker()
    return _provider, _queue, _tracker


@email_bp.get("/status")
def status():
    return jsonify({"status": "ok", "module": "email"})


@email_bp.post("/send")
def send_email():
    provider, queue, tracker = _get_services()
    data = request.get_json(force=True) or {}
    to = data.get("to", "")
    template_name = data.get("template", "order_confirm")
    context = data.get("context", {})

    if not to:
        return jsonify({"error": "수신자 이메일 필요"}), 400

    email_id = queue.enqueue(to, template_name, context)
    results = queue.process_queue(provider)
    for r in results:
        if r["email_id"] == email_id and r["status"] == "sent":
            tracker.record_sent(email_id, to, template_name)
    return jsonify({"email_id": email_id, "results": results}), 201


@email_bp.get("/templates")
def list_templates():
    from ..email_service.email_template import EmailTemplate
    return jsonify({"templates": EmailTemplate.list_builtins()})


@email_bp.get("/history")
def get_history():
    _, _, tracker = _get_services()
    limit = request.args.get("limit", type=int)
    return jsonify({"history": tracker.get_history(limit=limit)})


@email_bp.get("/stats")
def get_stats():
    _, _, tracker = _get_services()
    return jsonify(tracker.get_stats())
