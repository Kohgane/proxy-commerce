"""src/api/wishlist_api.py — Phase 43: 위시리스트 REST API Blueprint."""
import logging

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

wishlist_bp = Blueprint('wishlist', __name__, url_prefix='/api/v1/wishlist')


@wishlist_bp.get('/status')
def wishlist_status():
    return jsonify({'status': 'ok', 'module': 'wishlist'})


@wishlist_bp.post('/lists')
def create_wishlist():
    """POST /api/v1/wishlist/lists — 위시리스트 생성."""
    from ..wishlist.wishlist_manager import WishlistManager
    body = request.get_json(silent=True) or {}
    user_id = body.get('user_id', '')
    name = body.get('name', '기본')
    if not user_id:
        return jsonify({'error': 'user_id required'}), 400
    try:
        mgr = WishlistManager()
        wl = mgr.create_wishlist(user_id, name)
        return jsonify(wl), 201
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:
        logger.error("위시리스트 생성 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


@wishlist_bp.get('/lists/<user_id>')
def list_wishlists(user_id: str):
    """GET /api/v1/wishlist/lists/<user_id>."""
    from ..wishlist.wishlist_manager import WishlistManager
    try:
        mgr = WishlistManager()
        return jsonify(mgr.list_wishlists(user_id))
    except Exception as exc:
        logger.error("위시리스트 목록 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


@wishlist_bp.post('/items')
def add_item():
    """POST /api/v1/wishlist/items — 아이템 추가."""
    from ..wishlist.wishlist_manager import WishlistManager
    body = request.get_json(silent=True) or {}
    wishlist_id = body.get('wishlist_id', '')
    product_id = body.get('product_id', '')
    if not wishlist_id or not product_id:
        return jsonify({'error': 'wishlist_id and product_id required'}), 400
    try:
        mgr = WishlistManager()
        item = mgr.add_item(wishlist_id, product_id, **body)
        return jsonify(item), 201
    except (KeyError, ValueError) as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:
        logger.error("아이템 추가 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


@wishlist_bp.get('/share/<token>')
def get_shared_wishlist(token: str):
    """GET /api/v1/wishlist/share/<token> — 공유 위시리스트 조회."""
    from ..wishlist.share import WishlistShare
    try:
        share = WishlistShare()
        if not share.is_valid(token):
            return jsonify({'error': 'invalid or expired token'}), 404
        record = share.get_share(token)
        return jsonify(record)
    except Exception as exc:
        logger.error("공유 조회 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500
