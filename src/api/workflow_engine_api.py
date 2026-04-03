"""src/api/workflow_engine_api.py — 워크플로 엔진 API Blueprint (Phase 75)."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

workflow_engine_bp = Blueprint("workflow_engine", __name__,
                               url_prefix="/api/v1/workflows")


@workflow_engine_bp.get("/")
def list_workflows():
    """워크플로 정의 목록 조회."""
    from ..workflow_engine import WorkflowEngine
    engine = WorkflowEngine()
    return jsonify(engine.list_definitions())


@workflow_engine_bp.post("/")
def create_workflow():
    """워크플로 정의 생성."""
    body = request.get_json(silent=True) or {}
    name = body.get("name", "")
    if not name:
        return jsonify({"error": "name 필드가 필요합니다"}), 400
    from ..workflow_engine import WorkflowEngine, WorkflowDefinition, WorkflowState, WorkflowTransition
    engine = WorkflowEngine()
    states = [WorkflowState(**s) for s in body.get("states", [])]
    transitions = [WorkflowTransition(**t) for t in body.get("transitions", [])]
    defn = WorkflowDefinition(
        name=name,
        initial_state=body.get("initial_state", states[0].name if states else ""),
        states=states,
        transitions=transitions,
        description=body.get("description", ""),
    )
    engine.register(defn)
    return jsonify(defn.to_dict()), 201


@workflow_engine_bp.get("/<name>")
def get_workflow(name: str):
    """워크플로 정의 상세 조회."""
    from ..workflow_engine import WorkflowEngine
    engine = WorkflowEngine()
    defn = engine.get_definition(name)
    if defn is None:
        return jsonify({"error": "워크플로 없음"}), 404
    return jsonify(defn.to_dict())


@workflow_engine_bp.post("/start")
def start_workflow():
    """워크플로 인스턴스 시작."""
    body = request.get_json(silent=True) or {}
    name = body.get("name", "")
    if not name:
        return jsonify({"error": "name 필드가 필요합니다"}), 400
    from ..workflow_engine import WorkflowEngine
    engine = WorkflowEngine()
    try:
        instance = engine.start(name, context=body.get("context", {}))
        return jsonify(instance.to_dict()), 201
    except KeyError as e:
        return jsonify({"error": str(e)}), 404


@workflow_engine_bp.post("/instances/<instance_id>/transition")
def transition_workflow(instance_id: str):
    """워크플로 인스턴스 상태 전환."""
    body = request.get_json(silent=True) or {}
    transition_name = body.get("transition", "")
    if not transition_name:
        return jsonify({"error": "transition 필드가 필요합니다"}), 400
    from ..workflow_engine import WorkflowEngine
    engine = WorkflowEngine()
    try:
        instance = engine.transition(
            instance_id, transition_name,
            context_updates=body.get("context", {})
        )
        return jsonify(instance.to_dict())
    except (KeyError, ValueError) as e:
        return jsonify({"error": str(e)}), 400


@workflow_engine_bp.get("/instances/<instance_id>")
def get_instance(instance_id: str):
    """워크플로 인스턴스 조회."""
    from ..workflow_engine import WorkflowEngine
    engine = WorkflowEngine()
    instance = engine.get_instance(instance_id)
    if instance is None:
        return jsonify({"error": "인스턴스 없음"}), 404
    return jsonify(instance.to_dict())


@workflow_engine_bp.get("/instances/<instance_id>/history")
def get_history(instance_id: str):
    """워크플로 실행 이력 조회."""
    from ..workflow_engine import WorkflowEngine
    engine = WorkflowEngine()
    try:
        history = engine.get_history(instance_id)
        return jsonify({"instance_id": instance_id, "history": history})
    except KeyError as e:
        return jsonify({"error": str(e)}), 404


@workflow_engine_bp.get("/instances/")
def list_instances():
    """워크플로 인스턴스 목록 조회."""
    from ..workflow_engine import WorkflowEngine
    engine = WorkflowEngine()
    return jsonify(engine.list_instances())
