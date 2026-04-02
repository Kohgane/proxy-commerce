"""src/api/coupons_api.py — Phase 38: 쿠폰 REST API Blueprint."""
import logging

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

coupons_bp = Blueprint('coupons', __name__, url_prefix='/api/v1/coupons')


@coupons_bp.get('/status')
def coupons_status():
    return jsonify({'status': 'ok', 'module': 'coupons'})


@coupons_bp.get('/')
def list_coupons():
    """GET /api/v1/coupons/ — 쿠폰 목록."""
    from ..coupons.coupon_manager import CouponManager
    active_only = request.args.get('active_only', 'false').lower() == 'true'
    try:
        manager = CouponManager()
        return jsonify(manager.list_all(active_only=active_only))
    except Exception as exc:
        logger.error("쿠폰 목록 오류: %s", exc)
        return jsonify({'error': str(exc)}), 500


@coupons_bp.post('/')
def create_coupon():
    """POST /api/v1/coupons/ — 쿠폰 생성."""
    from ..coupons.coupon_manager import CouponManager
    body = request.get_json(silent=True) or {}
    try:
        manager = CouponManager()
        coupon = manager.create(body)
        return jsonify(coupon), 201
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:
        logger.error("쿠폰 생성 오류: %s", exc)
        return jsonify({'error': str(exc)}), 500


@coupons_bp.get('/<coupon_id>')
def get_coupon(coupon_id: str):
    """GET /api/v1/coupons/<id>."""
    from ..coupons.coupon_manager import CouponManager
    try:
        manager = CouponManager()
        coupon = manager.get(coupon_id)
        if coupon is None:
            return jsonify({'error': 'not found'}), 404
        return jsonify(coupon)
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500


@coupons_bp.post('/validate')
def validate_coupon():
    """POST /api/v1/coupons/validate — 쿠폰 유효성 검증."""
    from ..coupons.coupon_manager import CouponManager
    from decimal import Decimal
    body = request.get_json(silent=True) or {}
    code = body.get('code', '')
    order_amount = body.get('order_amount', 0)
    if not code:
        return jsonify({'error': 'code is required'}), 400
    try:
        manager = CouponManager()
        result = manager.validate(code, Decimal(str(order_amount)))
        return jsonify(result)
    except Exception as exc:
        logger.error("쿠폰 검증 오류: %s", exc)
        return jsonify({'error': str(exc)}), 500


@coupons_bp.post('/generate')
def generate_codes():
    """POST /api/v1/coupons/generate — 코드 일괄 생성."""
    from ..coupons.code_generator import CodeGenerator
    body = request.get_json(silent=True) or {}
    count = int(body.get('count', 1))
    prefix = body.get('prefix')
    length = int(body.get('length', 8))
    try:
        gen = CodeGenerator(length=length)
        codes = gen.generate_batch(count, prefix=prefix)
        return jsonify({'codes': codes, 'count': len(codes)})
    except Exception as exc:
        logger.error("코드 생성 오류: %s", exc)
        return jsonify({'error': str(exc)}), 500


@coupons_bp.post('/redeem')
def redeem_coupon():
    """POST /api/v1/coupons/redeem — 쿠폰 사용."""
    from ..coupons.redemption import RedemptionService
    from decimal import Decimal
    body = request.get_json(silent=True) or {}
    coupon_id = body.get('coupon_id', '')
    order_id = body.get('order_id', '')
    user_id = body.get('user_id', '')
    discount_amount = body.get('discount_amount', 0)
    if not coupon_id or not order_id:
        return jsonify({'error': 'coupon_id and order_id are required'}), 400
    try:
        service = RedemptionService()
        record = service.redeem(coupon_id, order_id, user_id, Decimal(str(discount_amount)))
        return jsonify(record), 201
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:
        logger.error("쿠폰 사용 오류: %s", exc)
        return jsonify({'error': str(exc)}), 500
