from __future__ import annotations

from flask import Blueprint, jsonify, session

from src.cs_bot.sla import check_and_notify_sla

bp = Blueprint("cs_bot_views", __name__)


@bp.post("/admin/cs/check-sla")
def admin_check_sla():
    if not session.get("user_id"):
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    if session.get("user_role") != "admin":
        return jsonify({"ok": False, "error": "forbidden"}), 403

    summary = check_and_notify_sla()
    return jsonify(
        {
            "ok": True,
            "nearing": summary.get("nearing_count", 0),
            "overdue": summary.get("overdue_count", 0),
        }
    )
