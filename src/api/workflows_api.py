"""src/api/workflows_api.py — 워크플로 엔진 API Blueprint (Phase 66)."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

workflows_bp = Blueprint("workflows", __name__, url_prefix="/api/v1/workflows")

_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        from ..workflow.workflow_engine import WorkflowEngine
        from ..workflow.workflows.order_workflow import OrderWorkflow
        from ..workflow.workflows.return_workflow import ReturnWorkflow
        _engine = WorkflowEngine()
        _engine.register(OrderWorkflow.build())
        _engine.register(ReturnWorkflow.build())
    return _engine


@workflows_bp.get("/status")
def status():
    return jsonify({"status": "ok", "module": "workflows"})


@workflows_bp.get("/list")
def list_definitions():
    engine = _get_engine()
    return jsonify({"definitions": engine.list_definitions()})


@workflows_bp.post("/define")
def define_workflow():
    engine = _get_engine()
    data = request.get_json(force=True) or {}
    if not data.get("name") or not data.get("initial_state"):
        return jsonify({"error": "name, initial_state 필요"}), 400
    from ..workflow.workflow_definition import WorkflowDefinition
    try:
        definition = WorkflowDefinition.from_dict(data)
        engine.register(definition)
        return jsonify(definition.to_dict()), 201
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@workflows_bp.post("/start")
def start_workflow():
    engine = _get_engine()
    data = request.get_json(force=True) or {}
    workflow_name = data.get("workflow_name", "")
    if not workflow_name:
        return jsonify({"error": "workflow_name 필요"}), 400
    try:
        instance = engine.start(workflow_name)
        return jsonify(instance.to_dict()), 201
    except KeyError as exc:
        return jsonify({"error": str(exc)}), 404


@workflows_bp.post("/<instance_id>/transition")
def transition_workflow(instance_id: str):
    engine = _get_engine()
    data = request.get_json(force=True) or {}
    event = data.get("event", "")
    if not event:
        return jsonify({"error": "event 필요"}), 400
    try:
        instance = engine.transition(instance_id, event)
        return jsonify(instance.to_dict())
    except (KeyError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400


@workflows_bp.get("/<instance_id>/status")
def get_status(instance_id: str):
    engine = _get_engine()
    status_data = engine.get_status(instance_id)
    if status_data is None:
        return jsonify({"error": "인스턴스 없음"}), 404
    return jsonify(status_data)


@workflows_bp.get("/history")
def get_history():
    engine = _get_engine()
    return jsonify({"history": engine.get_all_history()})
