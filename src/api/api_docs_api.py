"""src/api/api_docs_api.py — API 문서 Blueprint (Phase 52)."""
from __future__ import annotations

from flask import Blueprint, current_app, jsonify

api_docs_bp = Blueprint("api_docs", __name__, url_prefix="/api/docs")

_generator = None
_renderer = None


def _get_services():
    global _generator, _renderer
    if _generator is None:
        from ..docs.api_doc_generator import APIDocGenerator
        from ..docs.doc_renderer import DocRenderer
        _generator = APIDocGenerator(
            title="Proxy Commerce API",
            version="1.0.0",
            description="Phase 1~54 API 문서",
        )
        _renderer = DocRenderer()
    return _generator, _renderer


@api_docs_bp.get("")
@api_docs_bp.get("/")
def render_docs():
    """HTML 문서 렌더링."""
    generator, renderer = _get_services()
    try:
        spec = generator.generate(current_app._get_current_object())
    except RuntimeError:
        spec = generator.generate()
    html = renderer.render_html(spec)
    return html, 200, {"Content-Type": "text/html; charset=utf-8"}


@api_docs_bp.get("/openapi.json")
def openapi_json():
    """OpenAPI JSON 스펙 반환."""
    generator, _ = _get_services()
    try:
        spec = generator.generate(current_app._get_current_object())
    except RuntimeError:
        spec = generator.generate()
    return jsonify(spec)
