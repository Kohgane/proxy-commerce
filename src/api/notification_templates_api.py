"""src/api/notification_templates_api.py — 알림 템플릿 엔진 API (Phase 81)."""
from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

notification_templates_bp = Blueprint(
    "notification_templates", __name__, url_prefix="/api/v1/notification-templates"
)


def _mgr():
    from ..notification_templates import TemplateManager
    return TemplateManager()


@notification_templates_bp.get("/")
def list_templates():
    """템플릿 목록을 반환한다."""
    return jsonify(_mgr().list())


@notification_templates_bp.post("/")
def create_template():
    """템플릿을 생성한다."""
    data = request.get_json(silent=True) or {}
    mgr = _mgr()
    result = mgr.create(
        name=data.get('name', ''),
        channel=data.get('channel', 'email'),
        subject=data.get('subject', ''),
        body=data.get('body', ''),
        variables=data.get('variables'),
        locale=data.get('locale', 'ko'),
    )
    return jsonify(result), 201


@notification_templates_bp.get("/<name>")
def get_template(name: str):
    """템플릿을 반환한다."""
    tmpl = _mgr().get(name)
    if tmpl is None:
        return jsonify({'error': 'not found'}), 404
    return jsonify(tmpl)


@notification_templates_bp.post("/render")
def render_template():
    """템플릿을 렌더링한다."""
    from ..notification_templates import TemplateEngine
    data = request.get_json(silent=True) or {}
    engine = TemplateEngine()
    result = engine.render(data.get('template', ''), data.get('variables', {}))
    return jsonify({'result': result})


@notification_templates_bp.post("/preview")
def preview_template():
    """템플릿 미리보기를 반환한다."""
    from ..notification_templates import TemplatePreview
    data = request.get_json(silent=True) or {}
    preview = TemplatePreview()
    return jsonify(preview.preview(data))


@notification_templates_bp.get("/locales/list")
def list_locales():
    """지원 언어 목록을 반환한다."""
    from ..notification_templates import TemplateLocalization
    return jsonify(TemplateLocalization().supported_locales())
