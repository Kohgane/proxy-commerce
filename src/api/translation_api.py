"""src/api/translation_api.py — Phase 32: 번역 관리 REST API Blueprint."""

import logging

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

translation_bp = Blueprint('translation', __name__, url_prefix='/api/translation')


@translation_bp.get('/requests')
def list_requests():
    """GET /api/translation/requests — 번역 요청 목록."""
    from ..translation.translator import TranslationManager
    try:
        manager = TranslationManager()
        return jsonify(manager.get_all())
    except Exception as exc:
        logger.error("번역 요청 목록 조회 오류: %s", exc)
        return jsonify({'error': str(exc)}), 500


@translation_bp.post('/requests')
def create_request():
    """POST /api/translation/requests — 번역 요청 생성."""
    from ..translation.translator import TranslationManager
    body = request.get_json(silent=True) or {}
    product_id = body.get('product_id', '')
    text = body.get('text', '')
    src_lang = body.get('src_lang', 'en')
    tgt_lang = body.get('tgt_lang', 'ko')
    if not text:
        return jsonify({'error': 'text is required'}), 400
    try:
        manager = TranslationManager()
        req = manager.create_request(product_id, text, src_lang, tgt_lang)
        return jsonify(req), 201
    except Exception as exc:
        logger.error("번역 요청 생성 오류: %s", exc)
        return jsonify({'error': str(exc)}), 500


@translation_bp.get('/requests/<request_id>')
def get_request(request_id: str):
    """GET /api/translation/requests/<id> — 번역 요청 상태."""
    from ..translation.translator import TranslationManager
    try:
        manager = TranslationManager()
        req = manager.get_status(request_id)
        if req is None:
            return jsonify({'error': 'not found'}), 404
        return jsonify(req)
    except Exception as exc:
        logger.error("번역 요청 조회 오류: %s", exc)
        return jsonify({'error': str(exc)}), 500


@translation_bp.post('/requests/<request_id>/approve')
def approve_request(request_id: str):
    """POST /api/translation/requests/<id>/approve — 번역 승인."""
    from ..translation.translator import TranslationManager
    try:
        manager = TranslationManager()
        ok = manager.approve(request_id)
        if not ok:
            return jsonify({'error': 'not found'}), 404
        return jsonify({'status': 'approved'})
    except Exception as exc:
        logger.error("번역 승인 오류: %s", exc)
        return jsonify({'error': str(exc)}), 500


@translation_bp.get('/status')
def translation_status():
    """GET /api/translation/status — 번역 모듈 상태."""
    return jsonify({'status': 'ok', 'module': 'translation'})
