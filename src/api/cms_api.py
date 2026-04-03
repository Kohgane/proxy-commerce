"""src/api/cms_api.py — CMS API Blueprint (Phase 63)."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

cms_bp = Blueprint("cms", __name__, url_prefix="/api/v1/cms")

_manager = None
_versions = None
_publisher = None
_renderer = None


def _get_services():
    global _manager, _versions, _publisher, _renderer
    if _manager is None:
        from ..cms.content_manager import ContentManager
        from ..cms.content_version import ContentVersion
        from ..cms.content_publisher import ContentPublisher
        from ..cms.content_renderer import ContentRenderer
        _manager = ContentManager()
        _versions = ContentVersion()
        _publisher = ContentPublisher(manager=_manager)
        _renderer = ContentRenderer()
    return _manager, _versions, _publisher, _renderer


@cms_bp.get("/status")
def status():
    return jsonify({"status": "ok", "module": "cms"})


@cms_bp.get("/list")
def list_content():
    manager, _, _, _ = _get_services()
    return jsonify({"items": manager.list_all()})


@cms_bp.post("/create")
def create_content():
    manager, versions, _, _ = _get_services()
    data = request.get_json(force=True) or {}
    title = data.get("title", "")
    if not title:
        return jsonify({"error": "title 필요"}), 400
    item = manager.create(
        title=title,
        body=data.get("body", ""),
        content_type=data.get("content_type", "page"),
        status=data.get("status", "draft"),
    )
    versions.snapshot(item["content_id"], item)
    return jsonify(item), 201


@cms_bp.get("/<content_id>")
def get_content(content_id: str):
    manager, _, _, _ = _get_services()
    item = manager.get(content_id)
    if not item:
        return jsonify({"error": "콘텐츠 없음"}), 404
    return jsonify(item)


@cms_bp.put("/<content_id>")
def update_content(content_id: str):
    manager, versions, _, _ = _get_services()
    data = request.get_json(force=True) or {}
    try:
        updated = manager.update(content_id, **{k: v for k, v in data.items()})
        versions.snapshot(content_id, updated)
        return jsonify(updated)
    except KeyError:
        return jsonify({"error": "콘텐츠 없음"}), 404


@cms_bp.delete("/<content_id>")
def delete_content(content_id: str):
    manager, _, _, _ = _get_services()
    try:
        manager.delete(content_id)
        return jsonify({"deleted": content_id})
    except KeyError:
        return jsonify({"error": "콘텐츠 없음"}), 404


@cms_bp.post("/<content_id>/publish")
def publish_content(content_id: str):
    _, _, publisher, _ = _get_services()
    try:
        result = publisher.publish(content_id)
        return jsonify(result)
    except KeyError:
        return jsonify({"error": "콘텐츠 없음"}), 404


@cms_bp.post("/<content_id>/draft")
def draft_content(content_id: str):
    _, _, publisher, _ = _get_services()
    try:
        result = publisher.unpublish(content_id)
        return jsonify(result)
    except KeyError:
        return jsonify({"error": "콘텐츠 없음"}), 404


@cms_bp.get("/<content_id>/versions")
def get_versions(content_id: str):
    _, versions, _, _ = _get_services()
    return jsonify({"content_id": content_id, "versions": versions.get_history(content_id)})


@cms_bp.post("/render")
def render_content():
    _, _, _, renderer = _get_services()
    data = request.get_json(force=True) or {}
    markdown = data.get("markdown", "")
    html = renderer.render(markdown)
    return jsonify({"html": html})
