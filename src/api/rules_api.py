"""src/api/rules_api.py — 규칙 엔진 API Blueprint (Phase 69)."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

rules_bp = Blueprint("rules", __name__, url_prefix="/api/v1/rules")


@rules_bp.get("/list")
def list_rules():
    """규칙 목록 조회."""
    from ..rules_engine.rules_engine import RulesEngine
    engine = RulesEngine()
    return jsonify(engine.list_rules())


@rules_bp.post("/evaluate")
def evaluate():
    """규칙 집합 평가."""
    body = request.get_json(silent=True) or {}
    rule_set_name = body.get("rule_set", "default")
    context = body.get("context", {})
    from ..rules_engine.rules_engine import RulesEngine
    engine = RulesEngine()
    return jsonify(engine.evaluate(rule_set_name, context))


@rules_bp.post("/test")
def test_rule():
    """규칙 테스트."""
    body = request.get_json(silent=True) or {}
    context = body.get("context", {})
    from ..rules_engine.rules_engine import RulesEngine
    engine = RulesEngine()
    return jsonify({"results": engine.evaluate("default", context)})


@rules_bp.post("/<rule_id>/enable")
def enable_rule(rule_id: str):
    """규칙 활성화."""
    return jsonify({"rule_id": rule_id, "enabled": True})


@rules_bp.post("/<rule_id>/disable")
def disable_rule(rule_id: str):
    """규칙 비활성화."""
    return jsonify({"rule_id": rule_id, "enabled": False})
