"""src/api/payment_api.py — Phase 45: 결제 게이트웨이 REST API Blueprint."""
import logging

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

payment_bp = Blueprint('payment', __name__, url_prefix='/api/v1/payments')


@payment_bp.get('/status')
def payment_status():
    return jsonify({'status': 'ok', 'module': 'payment_gateway'})


@payment_bp.post('/initiate')
def initiate_payment():
    """POST /api/v1/payments/initiate — 결제 요청."""
    from ..payment_gateway.toss import TossPaymentsGateway
    from ..payment_gateway.stripe import StripeGateway
    from ..payment_gateway.paypal import PayPalGateway
    from ..payment_gateway.gateway_manager import GatewayManager
    body = request.get_json(silent=True) or {}
    try:
        mgr = GatewayManager()
        mgr.register('toss', TossPaymentsGateway())
        mgr.register('stripe', StripeGateway())
        mgr.register('paypal', PayPalGateway())
        currency = body.get('currency', 'KRW')
        gateway = mgr.route(currency)
        if gateway is None:
            return jsonify({'error': 'No gateway available'}), 400
        result = gateway.initiate_payment(
            amount=float(body.get('amount', 0)),
            currency=currency,
            order_id=body.get('order_id', ''),
        )
        return jsonify(result), 201
    except Exception as exc:
        logger.error("결제 요청 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


@payment_bp.get('/<payment_id>/status')
def get_payment_status(payment_id: str):
    """GET /api/v1/payments/<id>/status."""
    return jsonify({'payment_id': payment_id, 'status': 'unknown', 'note': 'use gateway directly'})
