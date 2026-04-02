"""src/api/returns_api.py — Phase 37: 반품/교환 REST API Blueprint."""
import logging

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

returns_bp = Blueprint('returns', __name__, url_prefix='/api/v1/returns')


@returns_bp.get('/status')
def returns_status():
    """GET /api/v1/returns/status — 모듈 상태."""
    return jsonify({'status': 'ok', 'module': 'returns'})


@returns_bp.get('/')
def list_returns():
    """GET /api/v1/returns/ — 반품 요청 목록."""
    from ..returns.return_manager import ReturnManager
    status = request.args.get('status')
    order_id = request.args.get('order_id')
    try:
        manager = ReturnManager()
        return jsonify(manager.list_all(status=status, order_id=order_id))
    except Exception as exc:
        logger.error("반품 목록 조회 오류: %s", exc)
        return jsonify({'error': str(exc)}), 500


@returns_bp.post('/')
def create_return():
    """POST /api/v1/returns/ — 반품 요청 생성."""
    from ..returns.return_manager import ReturnManager
    body = request.get_json(silent=True) or {}
    try:
        manager = ReturnManager()
        record = manager.create(body)
        return jsonify(record), 201
    except Exception as exc:
        logger.error("반품 생성 오류: %s", exc)
        return jsonify({'error': str(exc)}), 500


@returns_bp.get('/<return_id>')
def get_return(return_id: str):
    """GET /api/v1/returns/<id> — 반품 요청 조회."""
    from ..returns.return_manager import ReturnManager
    try:
        manager = ReturnManager()
        record = manager.get(return_id)
        if record is None:
            return jsonify({'error': 'not found'}), 404
        return jsonify(record)
    except Exception as exc:
        logger.error("반품 조회 오류: %s", exc)
        return jsonify({'error': str(exc)}), 500


@returns_bp.post('/<return_id>/status')
def update_return_status(return_id: str):
    """POST /api/v1/returns/<id>/status — 상태 전환."""
    from ..returns.return_manager import ReturnManager
    body = request.get_json(silent=True) or {}
    new_status = body.get('status', '')
    notes = body.get('notes', '')
    if not new_status:
        return jsonify({'error': 'status is required'}), 400
    try:
        manager = ReturnManager()
        record = manager.update_status(return_id, new_status, notes)
        if record is None:
            return jsonify({'error': 'not found'}), 404
        return jsonify(record)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:
        logger.error("반품 상태 변경 오류: %s", exc)
        return jsonify({'error': str(exc)}), 500


@returns_bp.post('/<return_id>/inspect')
def inspect_return(return_id: str):
    """POST /api/v1/returns/<id>/inspect — 검수 결과 등록."""
    from ..returns.return_manager import ReturnManager
    from ..returns.inspection import InspectionService
    from ..returns.refund_calculator import RefundCalculator
    body = request.get_json(silent=True) or {}
    condition_score = body.get('condition_score', 100)
    packaging_intact = body.get('packaging_intact', True)
    functional = body.get('functional', True)
    original_amount = body.get('original_amount', 0)
    try:
        inspector = InspectionService()
        result = inspector.inspect(return_id, condition_score, packaging_intact, functional)
        grade = result['grade']

        calc = RefundCalculator()
        from decimal import Decimal
        refund_data = calc.calculate(Decimal(str(original_amount)), grade=grade)

        manager = ReturnManager()
        record = manager.set_inspection(return_id, grade, refund_data['refund_amount'])
        if record is None:
            return jsonify({'error': 'not found'}), 404
        return jsonify({'inspection': result, 'refund': refund_data, 'return': record})
    except Exception as exc:
        logger.error("검수 오류: %s", exc)
        return jsonify({'error': str(exc)}), 500


@returns_bp.post('/<return_id>/exchange')
def create_exchange(return_id: str):
    """POST /api/v1/returns/<id>/exchange — 교환 요청 생성."""
    from ..returns.exchange_handler import ExchangeHandler
    body = request.get_json(silent=True) or {}
    product_id = body.get('product_id', '')
    if not product_id:
        return jsonify({'error': 'product_id is required'}), 400
    try:
        handler = ExchangeHandler()
        exchange = handler.create_exchange(
            return_id=return_id,
            product_id=product_id,
            original_option=body.get('original_option', ''),
            new_option=body.get('new_option', ''),
            same_product=body.get('same_product', True),
        )
        return jsonify(exchange), 201
    except Exception as exc:
        logger.error("교환 생성 오류: %s", exc)
        return jsonify({'error': str(exc)}), 500


@returns_bp.post('/refund/calculate')
def calculate_refund():
    """POST /api/v1/returns/refund/calculate — 환불 금액 계산."""
    from ..returns.refund_calculator import RefundCalculator
    from decimal import Decimal
    body = request.get_json(silent=True) or {}
    original_amount = body.get('original_amount', 0)
    grade = body.get('grade', 'A')
    deduct_shipping = body.get('deduct_shipping', True)
    coupon_discount = body.get('coupon_discount', 0)
    try:
        calc = RefundCalculator()
        result = calc.calculate(
            Decimal(str(original_amount)),
            grade=grade,
            deduct_shipping=deduct_shipping,
            coupon_discount=Decimal(str(coupon_discount)),
        )
        return jsonify(result)
    except Exception as exc:
        logger.error("환불 계산 오류: %s", exc)
        return jsonify({'error': str(exc)}), 500
