"""src/api/form_builder_api.py — 동적 폼 빌더 API Blueprint (Phase 74)."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

form_builder_bp = Blueprint("form_builder", __name__, url_prefix="/api/v1/forms")


@form_builder_bp.get("/")
def list_forms():
    """폼 목록 조회."""
    from ..form_builder import FormManager
    mgr = FormManager()
    return jsonify(mgr.list())


@form_builder_bp.post("/")
def create_form():
    """폼 생성."""
    body = request.get_json(silent=True) or {}
    name = body.get("name", "")
    if not name:
        return jsonify({"error": "name 필드가 필요합니다"}), 400
    from ..form_builder import FormManager
    mgr = FormManager()
    try:
        form = mgr.create(
            name=name,
            fields=body.get("fields", []),
            validation_rules=body.get("validation_rules", {}),
            description=body.get("description", ""),
        )
        return jsonify(form.to_dict()), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 409


@form_builder_bp.get("/<form_id>")
def get_form(form_id: str):
    """폼 상세 조회."""
    from ..form_builder import FormManager
    mgr = FormManager()
    form = mgr.get(form_id)
    if form is None:
        return jsonify({"error": "폼 없음"}), 404
    return jsonify(form.to_dict())


@form_builder_bp.put("/<form_id>")
def update_form(form_id: str):
    """폼 수정."""
    body = request.get_json(silent=True) or {}
    from ..form_builder import FormManager
    mgr = FormManager()
    try:
        form = mgr.update(form_id, **body)
        return jsonify(form.to_dict())
    except KeyError as e:
        return jsonify({"error": str(e)}), 404


@form_builder_bp.delete("/<form_id>")
def delete_form(form_id: str):
    """폼 삭제."""
    from ..form_builder import FormManager
    mgr = FormManager()
    try:
        mgr.delete(form_id)
        return jsonify({"deleted": form_id})
    except KeyError as e:
        return jsonify({"error": str(e)}), 404


@form_builder_bp.post("/<form_id>/submit")
def submit_form(form_id: str):
    """폼 제출."""
    body = request.get_json(silent=True) or {}
    from ..form_builder import FormManager, FormValidator, FormSubmission
    mgr = FormManager()
    form = mgr.get(form_id)
    if form is None:
        return jsonify({"error": "폼 없음"}), 404
    data = body.get("data", {})
    validator = FormValidator()
    is_valid, errors = validator.validate(form, data)
    if not is_valid:
        return jsonify({"error": "검증 실패", "details": errors}), 422
    submission_store = FormSubmission()
    record = submission_store.submit(form_id, data, body.get("submitter_id"))
    return jsonify(record), 201


@form_builder_bp.get("/<form_id>/submissions")
def form_submissions(form_id: str):
    """폼 제출 목록 조회."""
    from ..form_builder import FormSubmission
    store = FormSubmission()
    submissions = store.list_by_form(form_id)
    return jsonify({"form_id": form_id, "submissions": submissions, "count": len(submissions)})


@form_builder_bp.get("/<form_id>/render")
def render_form(form_id: str):
    """폼 HTML 렌더링."""
    from ..form_builder import FormManager, FormRenderer
    mgr = FormManager()
    form = mgr.get(form_id)
    if form is None:
        return jsonify({"error": "폼 없음"}), 404
    renderer = FormRenderer()
    html_str = renderer.render(form)
    return jsonify({"form_id": form_id, "html": html_str})


@form_builder_bp.post("/<form_id>/validate")
def validate_form(form_id: str):
    """폼 데이터 검증."""
    body = request.get_json(silent=True) or {}
    from ..form_builder import FormManager, FormValidator
    mgr = FormManager()
    form = mgr.get(form_id)
    if form is None:
        return jsonify({"error": "폼 없음"}), 404
    data = body.get("data", {})
    validator = FormValidator()
    is_valid, errors = validator.validate(form, data)
    return jsonify({"valid": is_valid, "errors": errors})
