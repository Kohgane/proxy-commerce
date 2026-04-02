"""src/api/inventory_sync_api.py — Phase 31: 재고 동기화 REST API Blueprint."""

import logging

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

inventory_sync_bp = Blueprint('inventory_sync', __name__, url_prefix='/api/inventory')


@inventory_sync_bp.get('/sync')
def get_sync_status():
    """GET /api/inventory/sync — 동기화 상태 조회."""
    from ..inventory_sync.sync_manager import InventorySyncManager
    try:
        manager = InventorySyncManager()
        status = manager.get_sync_status()
        return jsonify(status)
    except Exception as exc:
        logger.error("재고 동기화 상태 조회 오류: %s", exc)
        return jsonify({'error': str(exc)}), 500


@inventory_sync_bp.post('/sync')
def trigger_sync():
    """POST /api/inventory/sync — 재고 동기화 실행."""
    from ..inventory_sync.sync_manager import InventorySyncManager
    body = request.get_json(silent=True) or {}
    sku = body.get('sku')
    try:
        manager = InventorySyncManager()
        if sku:
            result = manager.sync_sku(sku)
        else:
            result = manager.sync_all_channels()
        return jsonify(result)
    except Exception as exc:
        logger.error("재고 동기화 실행 오류: %s", exc)
        return jsonify({'error': str(exc)}), 500


@inventory_sync_bp.get('/status')
def inventory_status():
    """GET /api/inventory/status — 인벤토리 상태."""
    from ..inventory_sync.sync_manager import InventorySyncManager
    try:
        manager = InventorySyncManager()
        status = manager.get_sync_status()
        return jsonify({'status': 'ok', 'sync_status': status})
    except Exception as exc:
        logger.error("인벤토리 상태 조회 오류: %s", exc)
        return jsonify({'error': str(exc)}), 500
