"""src/api/images_api.py — Phase 46: 이미지 관리 REST API Blueprint."""
import logging

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

images_bp = Blueprint('images', __name__, url_prefix='/api/v1/images')


@images_bp.get('/status')
def images_status():
    return jsonify({'status': 'ok', 'module': 'images'})


@images_bp.get('/')
def list_images():
    """GET /api/v1/images/?product_id=<id>."""
    from ..images.image_manager import ImageManager
    product_id = request.args.get('product_id')
    try:
        mgr = ImageManager()
        return jsonify(mgr.list_all(product_id=product_id))
    except Exception as exc:
        logger.error("이미지 목록 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


@images_bp.post('/')
def register_image():
    """POST /api/v1/images/ — 이미지 등록."""
    from ..images.image_manager import ImageManager
    body = request.get_json(silent=True) or {}
    url = body.get('url', '')
    if not url:
        return jsonify({'error': 'url required'}), 400
    try:
        mgr = ImageManager()
        image = mgr.register(url, **body)
        return jsonify(image), 201
    except Exception as exc:
        logger.error("이미지 등록 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


@images_bp.get('/<image_id>')
def get_image(image_id: str):
    """GET /api/v1/images/<id>."""
    from ..images.image_manager import ImageManager
    try:
        mgr = ImageManager()
        image = mgr.get(image_id)
        if image is None:
            return jsonify({'error': 'not found'}), 404
        return jsonify(image)
    except Exception as exc:
        logger.error("이미지 조회 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


@images_bp.delete('/<image_id>')
def delete_image(image_id: str):
    """DELETE /api/v1/images/<id>."""
    from ..images.image_manager import ImageManager
    try:
        mgr = ImageManager()
        deleted = mgr.delete(image_id)
        if not deleted:
            return jsonify({'error': 'not found'}), 404
        return jsonify({'deleted': True})
    except Exception as exc:
        logger.error("이미지 삭제 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500
