"""src/api/suppliers_api.py — Phase 34: 공급자 관리 REST API Blueprint."""

import logging

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

suppliers_bp = Blueprint('suppliers', __name__, url_prefix='/api/suppliers')


@suppliers_bp.get('/')
def list_suppliers():
    """GET /api/suppliers/ — 공급자 목록."""
    from ..suppliers.supplier_manager import SupplierManager
    active_only = request.args.get('active_only', 'false').lower() == 'true'
    try:
        manager = SupplierManager()
        return jsonify(manager.list_all(active_only=active_only))
    except Exception as exc:
        logger.error("공급자 목록 조회 오류: %s", exc)
        return jsonify({'error': str(exc)}), 500


@suppliers_bp.post('/')
def add_supplier():
    """POST /api/suppliers/ — 공급자 추가."""
    from ..suppliers.supplier_manager import SupplierManager
    body = request.get_json(silent=True) or {}
    try:
        manager = SupplierManager()
        supplier = manager.add(body)
        return jsonify(supplier), 201
    except Exception as exc:
        logger.error("공급자 추가 오류: %s", exc)
        return jsonify({'error': str(exc)}), 500


@suppliers_bp.get('/<supplier_id>')
def get_supplier(supplier_id: str):
    """GET /api/suppliers/<id> — 공급자 조회."""
    from ..suppliers.supplier_manager import SupplierManager
    try:
        manager = SupplierManager()
        supplier = manager.get(supplier_id)
        if supplier is None:
            return jsonify({'error': 'not found'}), 404
        return jsonify(supplier)
    except Exception as exc:
        logger.error("공급자 조회 오류: %s", exc)
        return jsonify({'error': str(exc)}), 500


@suppliers_bp.put('/<supplier_id>')
def update_supplier(supplier_id: str):
    """PUT /api/suppliers/<id> — 공급자 업데이트."""
    from ..suppliers.supplier_manager import SupplierManager
    body = request.get_json(silent=True) or {}
    try:
        manager = SupplierManager()
        supplier = manager.update(supplier_id, body)
        if supplier is None:
            return jsonify({'error': 'not found'}), 404
        return jsonify(supplier)
    except Exception as exc:
        logger.error("공급자 업데이트 오류: %s", exc)
        return jsonify({'error': str(exc)}), 500


@suppliers_bp.delete('/<supplier_id>')
def deactivate_supplier(supplier_id: str):
    """DELETE /api/suppliers/<id> — 공급자 비활성화."""
    from ..suppliers.supplier_manager import SupplierManager
    try:
        manager = SupplierManager()
        ok = manager.deactivate(supplier_id)
        if not ok:
            return jsonify({'error': 'not found'}), 404
        return jsonify({'status': 'deactivated'})
    except Exception as exc:
        logger.error("공급자 비활성화 오류: %s", exc)
        return jsonify({'error': str(exc)}), 500


@suppliers_bp.get('/status')
def suppliers_status():
    """GET /api/suppliers/status — 공급자 모듈 상태."""
    return jsonify({'status': 'ok', 'module': 'suppliers'})


@suppliers_bp.post('/score')
def calculate_score():
    """POST /api/suppliers/score — 공급자 점수 계산."""
    from ..suppliers.scoring import SupplierScoring
    body = request.get_json(silent=True) or {}
    quality = body.get('quality', 0)
    delivery = body.get('delivery', 0)
    price = body.get('price', 0)
    try:
        scoring = SupplierScoring()
        score = scoring.calculate_score(quality, delivery, price)
        grade = scoring.get_grade(score)
        return jsonify({'score': score, 'grade': grade})
    except Exception as exc:
        logger.error("점수 계산 오류: %s", exc)
        return jsonify({'error': str(exc)}), 500


@suppliers_bp.get('/orders')
def list_orders():
    """GET /api/suppliers/orders — 발주서 목록."""
    from ..suppliers.purchase_order import PurchaseOrderManager
    try:
        manager = PurchaseOrderManager()
        return jsonify(manager.list_all())
    except Exception as exc:
        logger.error("발주서 목록 조회 오류: %s", exc)
        return jsonify({'error': str(exc)}), 500


@suppliers_bp.post('/orders')
def create_order():
    """POST /api/suppliers/orders — 발주서 생성."""
    from ..suppliers.purchase_order import PurchaseOrderManager
    body = request.get_json(silent=True) or {}
    supplier_id = body.get('supplier_id', '')
    sku = body.get('sku', '')
    qty = body.get('qty', 0)
    if not supplier_id or not sku or not qty:
        return jsonify({'error': 'supplier_id, sku, qty are required'}), 400
    try:
        manager = PurchaseOrderManager()
        order = manager.create(supplier_id, sku, qty)
        return jsonify(order), 201
    except Exception as exc:
        logger.error("발주서 생성 오류: %s", exc)
        return jsonify({'error': str(exc)}), 500
