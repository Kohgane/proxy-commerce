"""src/api/flags_api.py — 피쳐 플래그 API Blueprint (Phase 59)."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

flags_bp = Blueprint("flags", __name__, url_prefix="/api/v1/flags")

_manager = None
_evaluator = None
_audit_log = None


def _get_services():
    global _manager, _evaluator, _audit_log
    if _manager is None:
        from ..feature_flags.feature_flag_manager import FeatureFlagManager
        from ..feature_flags.flag_evaluator import FlagEvaluator
        from ..feature_flags.flag_audit_log import FlagAuditLog
        _manager = FeatureFlagManager()
        _evaluator = FlagEvaluator(manager=_manager)
        _audit_log = FlagAuditLog()
    return _manager, _evaluator, _audit_log


@flags_bp.get("/status")
def status():
    return jsonify({"status": "ok", "module": "flags"})


@flags_bp.get("/list")
def list_flags():
    manager, _, _ = _get_services()
    return jsonify({"flags": manager.list_flags()})


@flags_bp.post("/create")
def create_flag():
    manager, _, audit = _get_services()
    data = request.get_json(force=True) or {}
    name = data.get("name", "")
    if not name:
        return jsonify({"error": "플래그 이름 필요"}), 400
    try:
        flag = manager.create_flag(name, enabled=data.get("enabled", False),
                                   description=data.get("description", ""))
        audit.record(name, "create", None, flag)
        return jsonify(flag), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 409


@flags_bp.get("/<name>")
def get_flag(name: str):
    manager, _, _ = _get_services()
    flag = manager.get_flag(name)
    if not flag:
        return jsonify({"error": "플래그 없음"}), 404
    return jsonify(flag)


@flags_bp.put("/<name>")
def update_flag(name: str):
    manager, _, audit = _get_services()
    data = request.get_json(force=True) or {}
    old = manager.get_flag(name)
    if not old:
        return jsonify({"error": "플래그 없음"}), 404
    try:
        updated = manager.update_flag(name, **data)
        audit.record(name, "update", old, updated)
        return jsonify(updated)
    except KeyError as e:
        return jsonify({"error": str(e)}), 404


@flags_bp.delete("/<name>")
def delete_flag(name: str):
    manager, _, audit = _get_services()
    old = manager.get_flag(name)
    if not old:
        return jsonify({"error": "플래그 없음"}), 404
    manager.delete_flag(name)
    audit.record(name, "delete", old, None)
    return jsonify({"deleted": name})


@flags_bp.post("/<name>/evaluate")
def evaluate_flag(name: str):
    _, evaluator, _ = _get_services()
    data = request.get_json(force=True) or {}
    user_id = data.get("user_id")
    user_context = data.get("user_context")
    result = evaluator.evaluate(name, user_id=user_id, user_context=user_context)
    return jsonify({"flag": name, "enabled": result})


@flags_bp.get("/<name>/audit")
def get_audit(name: str):
    _, _, audit = _get_services()
    return jsonify({"flag": name, "log": audit.get_log(flag_name=name)})
