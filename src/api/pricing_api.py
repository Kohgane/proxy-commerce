"""src/api/pricing_api.py — Phase 33: 가격 엔진 REST API Blueprint."""

import logging

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

pricing_bp = Blueprint('pricing', __name__, url_prefix='/api/pricing')


@pricing_bp.get('/status')
def pricing_status():
    """GET /api/pricing/status — 가격 엔진 상태."""
    return jsonify({'status': 'ok', 'module': 'pricing_engine'})


@pricing_bp.post('/simulate')
def simulate_price():
    """POST /api/pricing/simulate — 가격 시뮬레이션."""
    from ..pricing_engine.auto_pricer import AutoPricer
    body = request.get_json(silent=True) or {}
    sku = body.get('sku', '')
    market_data = body.get('market_data', {})
    if not sku:
        return jsonify({'error': 'sku is required'}), 400
    try:
        pricer = AutoPricer()
        result = pricer.simulate(sku, market_data)
        return jsonify(result)
    except Exception as exc:
        logger.error("가격 시뮬레이션 오류: %s", exc)
        return jsonify({'error': str(exc)}), 500


@pricing_bp.post('/run')
def run_pricer():
    """POST /api/pricing/run — 자동 가격 산정 실행."""
    from ..pricing_engine.auto_pricer import AutoPricer
    body = request.get_json(silent=True) or {}
    skus = body.get('skus')
    dry_run = body.get('dry_run', False)
    try:
        pricer = AutoPricer()
        result = pricer.run(skus=skus, dry_run=dry_run)
        return jsonify(result)
    except Exception as exc:
        logger.error("자동 가격 산정 오류: %s", exc)
        return jsonify({'error': str(exc)}), 500


@pricing_bp.get('/history/<sku>')
def price_history(sku: str):
    """GET /api/pricing/history/<sku> — 가격 이력 조회."""
    from ..pricing_engine.price_history import PriceHistory
    try:
        history = PriceHistory()
        data = history.get_history(sku)
        return jsonify({'sku': sku, 'history': data})
    except Exception as exc:
        logger.error("가격 이력 조회 오류: %s", exc)
        return jsonify({'error': str(exc)}), 500
