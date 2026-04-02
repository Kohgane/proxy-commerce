"""src/api/users_api.py — Phase 47: 사용자 프로필 REST API Blueprint."""
import logging

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

users_bp = Blueprint('users', __name__, url_prefix='/api/v1/users')


@users_bp.get('/status')
def users_status():
    return jsonify({'status': 'ok', 'module': 'users'})


@users_bp.post('/')
def create_user():
    """POST /api/v1/users/ — 사용자 생성."""
    from ..users.user_manager import UserManager
    body = request.get_json(silent=True) or {}
    try:
        mgr = UserManager()
        user = mgr.create(body)
        return jsonify(user), 201
    except ValueError:
        return jsonify({'error': 'Invalid request'}), 400
    except Exception as exc:
        logger.error("사용자 생성 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


@users_bp.get('/<user_id>')
def get_user(user_id: str):
    """GET /api/v1/users/<id>."""
    from ..users.user_manager import UserManager
    try:
        mgr = UserManager()
        user = mgr.get(user_id)
        if user is None:
            return jsonify({'error': 'not found'}), 404
        return jsonify(user)
    except Exception as exc:
        logger.error("사용자 조회 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


@users_bp.post('/<user_id>/addresses')
def add_address(user_id: str):
    """POST /api/v1/users/<id>/addresses — 배송지 추가."""
    from ..users.address_book import AddressBook
    body = request.get_json(silent=True) or {}
    try:
        book = AddressBook()
        address = book.add(user_id, body)
        return jsonify(address), 201
    except ValueError:
        return jsonify({'error': 'Invalid request'}), 400
    except Exception as exc:
        logger.error("배송지 추가 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


@users_bp.get('/<user_id>/addresses')
def list_addresses(user_id: str):
    """GET /api/v1/users/<id>/addresses."""
    from ..users.address_book import AddressBook
    try:
        book = AddressBook()
        return jsonify(book.list_by_user(user_id))
    except Exception as exc:
        logger.error("배송지 목록 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


@users_bp.get('/<user_id>/activity')
def get_activity(user_id: str):
    """GET /api/v1/users/<id>/activity."""
    from ..users.activity_log import ActivityLog
    n = int(request.args.get('n', 10))
    try:
        log = ActivityLog()
        return jsonify(log.get_recent(user_id, n=n))
    except Exception as exc:
        logger.error("활동 로그 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500
