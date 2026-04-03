"""src/api/docs_api.py — Phase 52: API 문서 Blueprint."""
import logging

from flask import Blueprint, current_app, jsonify, make_response

logger = logging.getLogger(__name__)

docs_bp = Blueprint('docs', __name__, url_prefix='/api')


@docs_bp.get('/docs')
def get_docs_html():
    from ..docs.api_doc_generator import APIDocGenerator
    from ..docs.doc_renderer import DocRenderer
    try:
        generator = APIDocGenerator()
        spec = generator.generate(current_app)
        renderer = DocRenderer()
        html = renderer.render_html(spec)
        response = make_response(html)
        response.headers['Content-Type'] = 'text/html; charset=utf-8'
        return response
    except Exception as exc:
        logger.error("API 문서 생성 오류: %s", exc)
        return make_response(f"Error: {exc}", 500)


@docs_bp.get('/docs/openapi.json')
def get_openapi_json():
    from ..docs.api_doc_generator import APIDocGenerator
    try:
        generator = APIDocGenerator()
        spec = generator.generate(current_app)
        return jsonify(spec)
    except Exception as exc:
        logger.error("OpenAPI 스펙 생성 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500
