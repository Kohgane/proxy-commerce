"""src/api/categories_api.py — Phase 39: 카테고리/태그 REST API Blueprint."""
import logging

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

categories_bp = Blueprint('categories', __name__, url_prefix='/api/v1/categories')


@categories_bp.get('/status')
def categories_status():
    return jsonify({'status': 'ok', 'module': 'categories'})


@categories_bp.get('/')
def list_categories():
    """GET /api/v1/categories/ — 카테고리 목록."""
    from ..categories.category_manager import CategoryManager
    parent_id = request.args.get('parent_id')
    top_level = request.args.get('top_level', 'false').lower() == 'true'
    try:
        manager = CategoryManager()
        if top_level:
            return jsonify(manager.list_top_level())
        if parent_id:
            return jsonify(manager.list_children(parent_id))
        return jsonify(manager.list_all())
    except Exception as exc:
        logger.error("오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


@categories_bp.post('/')
def create_category():
    """POST /api/v1/categories/ — 카테고리 생성."""
    from ..categories.category_manager import CategoryManager
    body = request.get_json(silent=True) or {}
    try:
        manager = CategoryManager()
        cat = manager.create(body)
        return jsonify(cat), 201
    except ValueError as exc:
        logger.warning("입력 오류: %s", exc)
        return jsonify({'error': 'Invalid request'}), 400
    except Exception as exc:
        logger.error("오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


@categories_bp.get('/<cat_id>')
def get_category(cat_id: str):
    from ..categories.category_manager import CategoryManager
    try:
        manager = CategoryManager()
        cat = manager.get(cat_id)
        if cat is None:
            return jsonify({'error': 'not found'}), 404
        return jsonify(cat)
    except Exception as exc:
        logger.error("오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


@categories_bp.get('/<cat_id>/breadcrumb')
def get_breadcrumb(cat_id: str):
    """GET /api/v1/categories/<id>/breadcrumb — 브레드크럼."""
    from ..categories.category_manager import CategoryManager
    from ..categories.breadcrumb import BreadcrumbGenerator
    try:
        manager = CategoryManager()
        gen = BreadcrumbGenerator()
        path = gen.build(cat_id, manager)
        if not path:
            return jsonify({'error': 'not found'}), 404
        return jsonify({'id': cat_id, 'breadcrumb': path})
    except Exception as exc:
        logger.error("오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


@categories_bp.get('/tags/')
def list_tags():
    """GET /api/v1/categories/tags/ — 태그 목록."""
    from ..categories.tag_manager import TagManager
    query = request.args.get('q', '')
    try:
        manager = TagManager()
        if query:
            return jsonify(manager.search_tags(query))
        return jsonify(manager.list_tags())
    except Exception as exc:
        logger.error("오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


@categories_bp.post('/tags/')
def create_tag():
    """POST /api/v1/categories/tags/ — 태그 생성."""
    from ..categories.tag_manager import TagManager
    body = request.get_json(silent=True) or {}
    name = body.get('name', '')
    if not name:
        return jsonify({'error': 'name is required'}), 400
    try:
        manager = TagManager()
        tag = manager.create_tag(name, body.get('color', ''))
        return jsonify(tag), 201
    except Exception as exc:
        logger.error("오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


@categories_bp.post('/tags/<product_id>')
def add_product_tag(product_id: str):
    """POST /api/v1/categories/tags/<product_id> — 상품 태그 추가."""
    from ..categories.tag_manager import TagManager
    body = request.get_json(silent=True) or {}
    tag_id = body.get('tag_id', '')
    if not tag_id:
        return jsonify({'error': 'tag_id is required'}), 400
    try:
        manager = TagManager()
        manager.add_tag_to_product(product_id, tag_id)
        return jsonify({'product_id': product_id, 'tag_id': tag_id, 'added': True})
    except ValueError as exc:
        logger.warning("입력 오류: %s", exc)
        return jsonify({'error': 'Invalid request'}), 400
    except Exception as exc:
        logger.error("오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500
