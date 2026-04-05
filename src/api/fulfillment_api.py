"""src/api/fulfillment_api.py — 풀필먼트 API Blueprint (Phase 103).

Blueprint: /api/v1/fulfillment

엔드포인트:
  POST /orders                        — 풀필먼트 주문 생성
  GET  /orders                        — 주문 목록 조회
  GET  /orders/<id>                   — 주문 상세 조회
  POST /orders/<id>/inspect           — 검수 실행
  POST /orders/<id>/pack              — 포장 실행
  POST /orders/<id>/ship              — 발송 요청
  GET  /orders/<id>/tracking          — 배송 추적
  POST /tracking/register             — 운송장 등록
  GET  /tracking/<tracking_number>    — 운송장 추적
  GET  /carriers                      — 택배사 목록
  POST /carriers/recommend            — 최적 택배사 추천
  GET  /dashboard                     — 대시보드 데이터
  GET  /stats                         — 처리량 통계
  POST /batch-ship                    — 일괄 발송
"""
from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

fulfillment_bp = Blueprint('fulfillment', __name__, url_prefix='/api/v1/fulfillment')

# 지연 초기화 서비스
_engine = None
_inspection_service = None
_packing_service = None
_shipping_manager = None
_tracking_manager = None
_delivery_tracker = None
_dashboard = None


def _get_engine():
    global _engine
    if _engine is None:
        from ..fulfillment.engine import FulfillmentEngine
        _engine = FulfillmentEngine()
    return _engine


def _get_inspection():
    global _inspection_service
    if _inspection_service is None:
        from ..fulfillment.inspection import InspectionService
        _inspection_service = InspectionService()
    return _inspection_service


def _get_packing():
    global _packing_service
    if _packing_service is None:
        from ..fulfillment.packing import PackingService
        _packing_service = PackingService()
    return _packing_service


def _get_shipping():
    global _shipping_manager
    if _shipping_manager is None:
        from ..fulfillment.shipping import DomesticShippingManager
        _shipping_manager = DomesticShippingManager()
    return _shipping_manager


def _get_tracking_manager():
    global _tracking_manager
    if _tracking_manager is None:
        from ..fulfillment.tracking import TrackingNumberManager
        _tracking_manager = TrackingNumberManager()
    return _tracking_manager


def _get_delivery_tracker():
    global _delivery_tracker
    if _delivery_tracker is None:
        from ..fulfillment.tracking import DeliveryTracker
        _delivery_tracker = DeliveryTracker()
    return _delivery_tracker


def _get_dashboard():
    global _dashboard
    if _dashboard is None:
        from ..fulfillment.dashboard import FulfillmentDashboard
        _dashboard = FulfillmentDashboard(
            engine=_get_engine(),
            inspection_service=_get_inspection(),
            packing_service=_get_packing(),
            shipping_manager=_get_shipping(),
            tracking_manager=_get_tracking_manager(),
            delivery_tracker=_get_delivery_tracker(),
        )
    return _dashboard


def _order_to_dict(o) -> dict:
    return {
        'order_id': o.order_id,
        'status': o.status.value,
        'items': o.items,
        'tracking_number': o.tracking_number,
        'carrier': o.carrier,
        'recipient': o.recipient,
        'inspection_result': o.inspection_result,
        'packing_result': o.packing_result,
        'timestamps': o.timestamps,
        'metadata': o.metadata,
    }


# ─── 주문 ────────────────────────────────────────────────────────────────────

@fulfillment_bp.post('/orders')
def create_order():
    data = request.get_json(silent=True) or {}
    items = data.get('items', [])
    recipient = data.get('recipient', {})
    metadata = data.get('metadata', {})
    engine = _get_engine()
    order = engine.create_order(items=items, recipient=recipient, metadata=metadata)
    return jsonify(_order_to_dict(order)), 201


@fulfillment_bp.get('/orders')
def list_orders():
    status_filter = request.args.get('status')
    engine = _get_engine()
    from ..fulfillment.engine import FulfillmentStatus
    status = None
    if status_filter:
        try:
            status = FulfillmentStatus(status_filter)
        except ValueError:
            return jsonify({'error': f'알 수 없는 상태: {status_filter}'}), 400
    orders = engine.list_orders(status=status)
    return jsonify([_order_to_dict(o) for o in orders])


@fulfillment_bp.get('/orders/<order_id>')
def get_order(order_id: str):
    engine = _get_engine()
    order = engine.get_order(order_id)
    if not order:
        return jsonify({'error': '주문을 찾을 수 없습니다'}), 404
    return jsonify(_order_to_dict(order))


@fulfillment_bp.post('/orders/<order_id>/inspect')
def inspect_order(order_id: str):
    engine = _get_engine()
    order = engine.get_order(order_id)
    if not order:
        return jsonify({'error': '주문을 찾을 수 없습니다'}), 404
    data = request.get_json(silent=True) or {}
    items = data.get('items', order.items)
    engine.advance_to_inspecting(order_id)
    svc = _get_inspection()
    result = svc.inspect(order_id, items)
    inspection_dict = {
        'inspection_id': result.inspection_id,
        'grade': result.grade.value,
        'defect_types': result.defect_types,
        'photo_urls': result.photo_urls,
        'comment': result.comment,
        'requires_return': result.requires_return,
        'inspected_at': result.inspected_at.isoformat(),
    }
    if not result.requires_return:
        engine.advance_to_packing(order_id, inspection_dict)
    return jsonify({'order': _order_to_dict(engine.get_order(order_id)), 'inspection': inspection_dict})


@fulfillment_bp.post('/orders/<order_id>/pack')
def pack_order(order_id: str):
    engine = _get_engine()
    order = engine.get_order(order_id)
    if not order:
        return jsonify({'error': '주문을 찾을 수 없습니다'}), 404
    packing_svc = _get_packing()
    result = packing_svc.pack(order_id, order.items)
    packing_dict = {
        'packing_id': result.packing_id,
        'packing_type': result.packing_type.value,
        'weight_kg': result.weight_kg,
        'dimensions_cm': result.dimensions_cm,
        'materials_used': result.materials_used,
        'packed_at': result.packed_at.isoformat(),
    }
    engine.advance_to_ready(order_id, packing_dict)
    return jsonify({'order': _order_to_dict(engine.get_order(order_id)), 'packing': packing_dict})


@fulfillment_bp.post('/orders/<order_id>/ship')
def ship_order(order_id: str):
    engine = _get_engine()
    order = engine.get_order(order_id)
    if not order:
        return jsonify({'error': '주문을 찾을 수 없습니다'}), 404
    data = request.get_json(silent=True) or {}
    carrier_id = data.get('carrier_id')
    strategy = data.get('strategy', 'balanced')
    packing_info = order.packing_result or {}
    package_info = {
        'weight_kg': packing_info.get('weight_kg', 1.0),
        'dimensions_cm': packing_info.get('dimensions_cm', {}),
    }
    shipping_mgr = _get_shipping()
    shipment = shipping_mgr.ship(
        order_id=order_id,
        recipient=order.recipient,
        package_info=package_info,
        carrier_id=carrier_id,
        strategy=strategy,
    )
    tracking_mgr = _get_tracking_manager()
    tracking_mgr.register(
        order_id=order_id,
        tracking_number=shipment['tracking_number'],
        carrier_id=shipment['carrier_id'],
        platform=data.get('platform', 'internal'),
    )
    delivery_tracker = _get_delivery_tracker()
    delivery_tracker.start_tracking(shipment['tracking_number'], shipment['carrier_id'])
    engine.advance_to_shipped(order_id, shipment['tracking_number'], shipment['carrier_id'])
    return jsonify({'order': _order_to_dict(engine.get_order(order_id)), 'shipment': shipment})


@fulfillment_bp.get('/orders/<order_id>/tracking')
def get_order_tracking(order_id: str):
    engine = _get_engine()
    order = engine.get_order(order_id)
    if not order:
        return jsonify({'error': '주문을 찾을 수 없습니다'}), 404
    if not order.tracking_number:
        return jsonify({'error': '운송장이 없습니다'}), 404
    delivery_tracker = _get_delivery_tracker()
    tracking = delivery_tracker.get_status(order.tracking_number)
    return jsonify(tracking)


# ─── 운송장 ──────────────────────────────────────────────────────────────────

@fulfillment_bp.post('/tracking/register')
def register_tracking():
    data = request.get_json(silent=True) or {}
    order_id = data.get('order_id', '')
    tracking_number = data.get('tracking_number', '')
    carrier_id = data.get('carrier_id', '')
    platform = data.get('platform', 'internal')
    if not order_id or not tracking_number or not carrier_id:
        return jsonify({'error': 'order_id, tracking_number, carrier_id 필수'}), 400
    tracking_mgr = _get_tracking_manager()
    record = tracking_mgr.register(order_id, tracking_number, carrier_id, platform)
    return jsonify({
        'tracking_id': record.tracking_id,
        'order_id': record.order_id,
        'tracking_number': record.tracking_number,
        'carrier_id': record.carrier_id,
        'platform': record.platform,
        'registration_success': record.registration_success,
        'registered_at': record.registered_at.isoformat(),
    }), 201


@fulfillment_bp.get('/tracking/<tracking_number>')
def get_tracking(tracking_number: str):
    delivery_tracker = _get_delivery_tracker()
    tracking = delivery_tracker.get_status(tracking_number)
    return jsonify(tracking)


# ─── 택배사 ──────────────────────────────────────────────────────────────────

@fulfillment_bp.get('/carriers')
def list_carriers():
    from ..fulfillment.shipping import CarrierSelector
    selector = CarrierSelector()
    return jsonify(selector.list_carriers())


@fulfillment_bp.post('/carriers/recommend')
def recommend_carrier():
    data = request.get_json(silent=True) or {}
    weight_kg = float(data.get('weight_kg', 1.0))
    region = data.get('region', '')
    strategy = data.get('strategy', 'balanced')
    from ..fulfillment.shipping import CarrierSelector
    selector = CarrierSelector()
    carrier = selector.recommend(weight_kg=weight_kg, region=region, strategy=strategy)
    return jsonify({
        'carrier_id': carrier.carrier_id,
        'name': carrier.name,
        'base_cost_krw': carrier.base_cost_krw,
        'avg_delivery_days': carrier.avg_delivery_days,
    })


# ─── 대시보드 / 통계 ──────────────────────────────────────────────────────────

@fulfillment_bp.get('/dashboard')
def get_dashboard():
    dashboard = _get_dashboard()
    return jsonify(dashboard.get_summary())


@fulfillment_bp.get('/stats')
def get_stats():
    engine = _get_engine()
    return jsonify(engine.get_stats())


# ─── 일괄 발송 ───────────────────────────────────────────────────────────────

@fulfillment_bp.post('/batch-ship')
def batch_ship():
    data = request.get_json(silent=True) or {}
    order_ids = data.get('order_ids', [])
    carrier_id = data.get('carrier_id')
    strategy = data.get('strategy', 'balanced')
    if not order_ids:
        return jsonify({'error': 'order_ids 필수'}), 400

    engine = _get_engine()
    shipping_mgr = _get_shipping()
    tracking_mgr = _get_tracking_manager()
    delivery_tracker = _get_delivery_tracker()

    results = []
    errors = []
    for oid in order_ids:
        order = engine.get_order(oid)
        if not order:
            errors.append({'order_id': oid, 'error': '주문을 찾을 수 없습니다'})
            continue
        try:
            packing_info = order.packing_result or {}
            package_info = {
                'weight_kg': packing_info.get('weight_kg', 1.0),
                'dimensions_cm': packing_info.get('dimensions_cm', {}),
            }
            shipment = shipping_mgr.ship(
                order_id=oid,
                recipient=order.recipient,
                package_info=package_info,
                carrier_id=carrier_id,
                strategy=strategy,
            )
            tracking_mgr.register(
                order_id=oid,
                tracking_number=shipment['tracking_number'],
                carrier_id=shipment['carrier_id'],
                platform='internal',
            )
            delivery_tracker.start_tracking(shipment['tracking_number'], shipment['carrier_id'])
            engine.advance_to_shipped(oid, shipment['tracking_number'], shipment['carrier_id'])
            results.append({'order_id': oid, 'tracking_number': shipment['tracking_number'], 'status': 'shipped'})
        except Exception as exc:
            logger.error("batch-ship 오류 order=%s: %s", oid, exc)
            errors.append({'order_id': oid, 'error': '발송 처리 중 오류가 발생했습니다'})
    return jsonify({'results': results, 'errors': errors, 'total': len(order_ids), 'success': len(results)})
