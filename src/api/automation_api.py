"""src/api/automation_api.py — 자동화 API.

Flask Blueprint 기반 워크플로 자동화 규칙/스케줄러 API.

엔드포인트:
  GET  /api/automation/rules          — 자동화 규칙 목록
  POST /api/automation/rules          — 규칙 생성
  PATCH /api/automation/rules/<id>    — 규칙 수정
  GET  /api/automation/jobs           — 스케줄러 작업 목록
  GET  /api/automation/history        — 실행 이력

환경변수:
  DASHBOARD_API_KEY — API 인증 키
"""

import logging

from flask import Blueprint, jsonify, request

from .auth_middleware import require_api_key

logger = logging.getLogger(__name__)

automation_bp = Blueprint("automation", __name__, url_prefix="/api/automation")


def _get_engine():
    from ..automation.rule_engine import RuleEngine
    return RuleEngine()


def _get_scheduler():
    from ..automation.scheduler import Scheduler
    return Scheduler()


@automation_bp.get("/rules")
@require_api_key
def list_rules():
    """자동화 규칙 목록을 반환한다."""
    trigger = request.args.get("trigger")
    enabled_only = request.args.get("enabled_only", "0") != "0"
    engine = _get_engine()
    try:
        rules = engine.get_rules(trigger=trigger, enabled_only=enabled_only)
    except Exception as exc:
        logger.warning("규칙 목록 조회 실패: %s", exc)
        rules = []

    return jsonify({"rules": rules, "count": len(rules)})


@automation_bp.post("/rules")
@require_api_key
def create_rule():
    """새 자동화 규칙을 생성한다."""
    data = request.get_json(silent=True) or {}
    engine = _get_engine()
    try:
        ok = engine.add_rule(data)
    except Exception as exc:
        logger.warning("규칙 생성 실패: %s", exc)
        return jsonify({"error": str(exc)}), 500

    if not ok:
        return jsonify({"error": "규칙 생성 실패"}), 500
    return jsonify({"ok": True, "rule": data}), 201


@automation_bp.patch("/rules/<rule_id>")
@require_api_key
def update_rule(rule_id: str):
    """자동화 규칙을 수정한다."""
    data = request.get_json(silent=True) or {}
    engine = _get_engine()
    try:
        ok = engine.update_rule(rule_id, data)
    except Exception as exc:
        logger.warning("규칙 수정 실패 (%s): %s", rule_id, exc)
        return jsonify({"error": str(exc)}), 500

    if not ok:
        return jsonify({"error": "규칙을 찾을 수 없습니다"}), 404
    return jsonify({"ok": True, "rule_id": rule_id})


@automation_bp.get("/jobs")
@require_api_key
def list_jobs():
    """스케줄러 등록 작업 목록을 반환한다."""
    scheduler = _get_scheduler()
    try:
        jobs = scheduler.list_jobs()
    except Exception as exc:
        logger.warning("작업 목록 조회 실패: %s", exc)
        jobs = []

    return jsonify({"jobs": jobs, "count": len(jobs)})


@automation_bp.get("/history")
@require_api_key
def get_history():
    """스케줄러 실행 이력을 반환한다."""
    limit = int(request.args.get("limit", 50))
    scheduler = _get_scheduler()
    try:
        history = scheduler.get_history(limit=limit)
    except Exception as exc:
        logger.warning("실행 이력 조회 실패: %s", exc)
        history = []

    return jsonify({"history": history, "count": len(history)})
