"""src/api/bundles_api.py — Phase 44: 번들 REST API Blueprint."""
import logging

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

bundles_bp = Blueprint('bundles', __name__, url_prefix='/api/v1/bundles')


@bundles_bp.get('/status')
def bundles_status():
    return jsonify({'status': 'ok', 'module': 'bundles'})


@bundles_bp.get('/')
def list_bundles():
    """GET /api/v1/bundles/ — 번들 목록."""
    from ..bundles.bundle_manager import BundleManager
    status = request.args.get('status')
    try:
        mgr = BundleManager()
        return jsonify(mgr.list_all(status=status))
    except Exception as exc:
        logger.error("번들 목록 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


@bundles_bp.post('/')
def create_bundle():
    """POST /api/v1/bundles/ — 번들 생성."""
    from ..bundles.bundle_manager import BundleManager
    body = request.get_json(silent=True) or {}
    try:
        mgr = BundleManager()
        bundle = mgr.create(body)
        return jsonify(bundle), 201
    except ValueError:
        return jsonify({'error': 'Invalid request'}), 400
    except Exception as exc:
        logger.error("번들 생성 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


@bundles_bp.get('/<bundle_id>')
def get_bundle(bundle_id: str):
    """GET /api/v1/bundles/<id>."""
    from ..bundles.bundle_manager import BundleManager
    try:
        mgr = BundleManager()
        bundle = mgr.get(bundle_id)
        if bundle is None:
            return jsonify({'error': 'not found'}), 404
        return jsonify(bundle)
    except Exception as exc:
        logger.error("번들 조회 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


@bundles_bp.post('/<bundle_id>/price')
def get_bundle_price(bundle_id: str):
    """POST /api/v1/bundles/<id>/price — 번들 가격 계산."""
    from ..bundles.bundle_manager import BundleManager
    from ..bundles.pricing import BundlePricing
    body = request.get_json(silent=True) or {}
    try:
        mgr = BundleManager()
        bundle = mgr.get(bundle_id)
        if bundle is None:
            return jsonify({'error': 'not found'}), 404
        pricing = BundlePricing()
        price_catalog = body.get('price_catalog', {})
        strategy = body.get('strategy', 'sum_discount')
        result = pricing.calculate_from_bundle(bundle, price_catalog, strategy=strategy,
                                               discount_pct=body.get('discount_pct', 0),
                                               fixed_price=body.get('fixed_price'))
        return jsonify(result)
    except ValueError:
        return jsonify({'error': 'Invalid request'}), 400
    except Exception as exc:
        logger.error("번들 가격 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500
