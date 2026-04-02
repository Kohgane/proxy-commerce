"""src/api/multicurrency_api.py — Phase 45: 멀티통화 REST API Blueprint."""
import logging

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

multicurrency_bp = Blueprint('multicurrency', __name__, url_prefix='/api/v1/currency')


@multicurrency_bp.get('/status')
def currency_status():
    return jsonify({'status': 'ok', 'module': 'multicurrency'})


@multicurrency_bp.get('/')
def list_currencies():
    """GET /api/v1/currency/ — 지원 통화 목록."""
    from ..multicurrency.currency_manager import CurrencyManager
    try:
        mgr = CurrencyManager()
        return jsonify(mgr.list_all())
    except Exception as exc:
        logger.error("통화 목록 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


@multicurrency_bp.get('/convert')
def convert_currency():
    """GET /api/v1/currency/convert?amount=&from=&to=."""
    from ..multicurrency.conversion import CurrencyConverter
    try:
        amount = float(request.args.get('amount', 0))
        from_currency = request.args.get('from', 'KRW')
        to_currency = request.args.get('to', 'USD')
        converter = CurrencyConverter()
        result = converter.convert(amount, from_currency, to_currency)
        return jsonify({
            'amount': amount,
            'from': from_currency,
            'to': to_currency,
            'result': result,
        })
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:
        logger.error("통화 변환 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


@multicurrency_bp.get('/format')
def format_currency():
    """GET /api/v1/currency/format?amount=&currency=."""
    from ..multicurrency.display import CurrencyDisplay
    try:
        amount = float(request.args.get('amount', 0))
        currency = request.args.get('currency', 'KRW')
        display = CurrencyDisplay()
        return jsonify({'formatted': display.format(amount, currency)})
    except Exception as exc:
        logger.error("통화 포맷 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500
