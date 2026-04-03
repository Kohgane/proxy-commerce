"""src/api/feature_flags_api.py — 피처 플래그 고도화 API Blueprint (Phase 78)."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

feature_flags_bp = Blueprint("feature_flags_advanced", __name__,
                              url_prefix="/api/v1/feature-flags")


@feature_flags_bp.get("/")
def list_flags():
    """플래그 목록 조회."""
    from ..feature_flags import FeatureFlagManager
    mgr = FeatureFlagManager()
    return jsonify(mgr.list_flags())


@feature_flags_bp.post("/")
def create_flag():
    """플래그 생성."""
    body = request.get_json(silent=True) or {}
    name = body.get("name", "")
    if not name:
        return jsonify({"error": "name 필드가 필요합니다"}), 400
    from ..feature_flags import FeatureFlagManager, FlagHistory
    mgr = FeatureFlagManager()
    history = FlagHistory()
    try:
        flag = mgr.create_flag(name=name, enabled=body.get("enabled", False),
                                description=body.get("description", ""))
        history.record(name, "created")
        return jsonify(flag), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 409


@feature_flags_bp.get("/<name>")
def get_flag(name: str):
    """플래그 상세 조회."""
    from ..feature_flags import FeatureFlagManager
    mgr = FeatureFlagManager()
    flag = mgr.get_flag(name)
    if flag is None:
        return jsonify({"error": "플래그 없음"}), 404
    return jsonify(flag)


@feature_flags_bp.put("/<name>")
def update_flag(name: str):
    """플래그 수정."""
    body = request.get_json(silent=True) or {}
    from ..feature_flags import FeatureFlagManager, FlagHistory
    mgr = FeatureFlagManager()
    history = FlagHistory()
    try:
        flag = mgr.update_flag(name, **body)
        history.record(name, "updated", changes=body)
        return jsonify(flag)
    except KeyError as e:
        return jsonify({"error": str(e)}), 404


@feature_flags_bp.delete("/<name>")
def delete_flag(name: str):
    """플래그 삭제."""
    from ..feature_flags import FeatureFlagManager, FlagHistory
    mgr = FeatureFlagManager()
    history = FlagHistory()
    try:
        mgr.delete_flag(name)
        history.record(name, "deleted")
        return jsonify({"deleted": name})
    except KeyError as e:
        return jsonify({"error": str(e)}), 404


@feature_flags_bp.post("/<name>/evaluate")
def evaluate_flag(name: str):
    """플래그 평가."""
    body = request.get_json(silent=True) or {}
    user_id = body.get("user_id", "")
    context = body.get("context", {})
    environment = body.get("environment", "")
    from ..feature_flags import FeatureFlagManager, FeatureFlag, TargetingRule, Variant, FlagEvaluatorAdvanced
    mgr = FeatureFlagManager()
    flag_data = mgr.get_flag(name)
    if flag_data is None:
        return jsonify({"error": "플래그 없음"}), 404
    # FeatureFlag 데이터클래스로 변환
    rules = [TargetingRule(**r) for r in flag_data.get("rules", [])]
    flag = FeatureFlag(
        name=flag_data["name"],
        enabled=flag_data.get("enabled", False),
        description=flag_data.get("description", ""),
        rules=rules,
        rollout_percentage=flag_data.get("rollout_percentage", 100.0),
    )
    evaluator = FlagEvaluatorAdvanced()
    result = evaluator.evaluate(flag, user_id=user_id, context=context,
                                environment=environment)
    return jsonify(result)


@feature_flags_bp.post("/<name>/toggle")
def toggle_flag(name: str):
    """플래그 토글."""
    from ..feature_flags import FeatureFlagManager, FlagHistory
    mgr = FeatureFlagManager()
    history = FlagHistory()
    flag = mgr.get_flag(name)
    if flag is None:
        return jsonify({"error": "플래그 없음"}), 404
    new_enabled = not flag["enabled"]
    updated = mgr.update_flag(name, enabled=new_enabled)
    history.record(name, "toggled", changes={"enabled": new_enabled})
    return jsonify(updated)


@feature_flags_bp.post("/<name>/rollout")
def set_rollout(name: str):
    """점진적 롤아웃 설정."""
    body = request.get_json(silent=True) or {}
    percentage = body.get("percentage", 100.0)
    from ..feature_flags import FeatureFlagManager
    mgr = FeatureFlagManager()
    flag = mgr.get_flag(name)
    if flag is None:
        return jsonify({"error": "플래그 없음"}), 404
    updated = mgr.update_flag(name, rollout_percentage=percentage)
    return jsonify(updated)


@feature_flags_bp.get("/<name>/history")
def flag_history(name: str):
    """플래그 변경 이력 조회."""
    from ..feature_flags import FlagHistory
    history = FlagHistory()
    return jsonify({"flag_name": name, "history": history.get_flag_history(name)})


@feature_flags_bp.get("/<name>/overrides")
def list_overrides(name: str):
    """플래그 오버라이드 목록."""
    from ..feature_flags import FlagOverride
    override = FlagOverride()
    all_overrides = [o for o in override.list_overrides() if o.get("flag_name") == name]
    return jsonify({"flag_name": name, "overrides": all_overrides})


@feature_flags_bp.post("/<name>/overrides")
def set_override(name: str):
    """플래그 오버라이드 설정."""
    body = request.get_json(silent=True) or {}
    user_id = body.get("user_id", "")
    environment = body.get("environment", "")
    value = body.get("value", True)
    from ..feature_flags import FlagOverride
    override = FlagOverride()
    if user_id:
        record = override.set_user_override(name, user_id, value)
    elif environment:
        record = override.set_env_override(name, environment, value)
    else:
        return jsonify({"error": "user_id 또는 environment 필드가 필요합니다"}), 400
    return jsonify(record), 201
