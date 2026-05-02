"""src/api/forwarding_api.py — 배송대행지 API Blueprint (Phase 102).

Blueprint: /api/v1/forwarding

엔드포인트:
  POST /shipments                      — 배송 요청 생성
  GET  /shipments                      — 배송 목록
  GET  /shipments/<id>                 — 배송 상세
  GET  /shipments/<id>/tracking        — 배송 추적 정보
  POST /incoming/check                 — 입고 확인
  GET  /incoming                       — 입고 기록 목록
  GET  /incoming/<id>                  — 입고 기록 상세
  POST /consolidation                  — 합배송 그룹 생성
  GET  /consolidation                  — 합배송 그룹 목록
  POST /consolidation/<id>/execute     — 합배송 실행
  POST /estimate                       — 비용 견적
  GET  /agents                         — 에이전트 목록
  GET  /agents/<id>/recommend          — 에이전트 추천
  GET  /dashboard                      — 대시보드 데이터
"""
from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

forwarding_bp = Blueprint('forwarding', __name__, url_prefix='/api/v1/forwarding')

# 지연 초기화 서비스
_verifier = None
_consolidation_manager = None
_tracker = None
_estimator = None
_agent_manager = None
_fwd_engine = None


def _get_fwd_engine():
    global _fwd_engine
    if _fwd_engine is None:
        from ..forwarding_integration.forwarding_engine import ForwardingEngine
        _fwd_engine = ForwardingEngine()
    return _fwd_engine


def _get_verifier():
    global _verifier
    if _verifier is None:
        from ..forwarding.incoming import IncomingVerifier
        _verifier = IncomingVerifier()
    return _verifier


def _get_consolidation_manager():
    global _consolidation_manager
    if _consolidation_manager is None:
        from ..forwarding.consolidation import ConsolidationManager
        _consolidation_manager = ConsolidationManager()
    return _consolidation_manager


def _get_tracker():
    global _tracker
    if _tracker is None:
        from ..forwarding.tracker import ShipmentTracker
        _tracker = ShipmentTracker()
    return _tracker


def _get_estimator():
    global _estimator
    if _estimator is None:
        from ..forwarding.cost_estimator import CostEstimator
        _estimator = CostEstimator()
    return _estimator


def _get_agent_manager():
    global _agent_manager
    if _agent_manager is None:
        from ..forwarding.agent import ForwardingAgentManager
        _agent_manager = ForwardingAgentManager()
    return _agent_manager


def _shipment_to_dict(s) -> dict:
    return {
        'shipment_id': s.shipment_id,
        'tracking_number': s.tracking_number,
        'agent_id': s.agent_id,
        'status': s.status.value,
        'origin_country': s.origin_country,
        'destination_country': s.destination_country,
        'estimated_delivery': s.estimated_delivery.isoformat() if s.estimated_delivery else None,
        'customs_status': s.customs_status,
        'created_at': s.created_at.isoformat(),
        'delivered_at': s.delivered_at.isoformat() if s.delivered_at else None,
        'metadata': s.metadata,
    }


def _incoming_to_dict(r) -> dict:
    return {
        'record_id': r.record_id,
        'order_id': r.order_id,
        'agent_id': r.agent_id,
        'tracking_number': r.tracking_number,
        'status': r.status.value,
        'received_at': r.received_at.isoformat() if r.received_at else None,
        'weight_kg': r.weight_kg,
        'photo_urls': r.photo_urls,
        'inspection_notes': r.inspection_notes,
        'issue_type': r.issue_type,
        'metadata': r.metadata,
    }


def _group_to_dict(g) -> dict:
    return {
        'group_id': g.group_id,
        'order_ids': g.order_ids,
        'agent_id': g.agent_id,
        'status': g.status.value,
        'estimated_weight_kg': g.estimated_weight_kg,
        'estimated_cost_usd': g.estimated_cost_usd,
        'savings_usd': g.savings_usd,
        'created_at': g.created_at.isoformat(),
        'executed_at': g.executed_at.isoformat() if g.executed_at else None,
        'metadata': g.metadata,
    }


# ---------------------------------------------------------------------------
# POST /shipments
# ---------------------------------------------------------------------------

@forwarding_bp.post('/shipments')
def create_shipment():
    """배송 요청을 생성한다."""
    data = request.get_json(force=True, silent=True) or {}
    tracking_number = data.get('tracking_number', '')
    agent_id = data.get('agent_id', 'moltail')
    origin_country = data.get('origin_country', 'US')

    if not tracking_number:
        return jsonify({'error': 'tracking_number is required'}), 400

    try:
        tracker = _get_tracker()
        record = tracker.create_shipment(tracking_number, agent_id, origin_country)
        return jsonify(_shipment_to_dict(record)), 201
    except Exception as exc:
        logger.error('create_shipment error: %s', exc)
        return jsonify({'error': 'Internal server error'}), 500


# ---------------------------------------------------------------------------
# GET /shipments
# ---------------------------------------------------------------------------

@forwarding_bp.get('/shipments')
def list_shipments():
    """배송 목록을 반환한다."""
    try:
        from ..forwarding.tracker import ShipmentStatus
        status_param = request.args.get('status')
        status = ShipmentStatus(status_param) if status_param else None
        tracker = _get_tracker()
        shipments = tracker.list_shipments(status=status)
        return jsonify([_shipment_to_dict(s) for s in shipments])
    except Exception as exc:
        logger.error('list_shipments error: %s', exc)
        return jsonify({'error': 'Internal server error'}), 500


# ---------------------------------------------------------------------------
# GET /shipments/<id>
# ---------------------------------------------------------------------------

@forwarding_bp.get('/shipments/<shipment_id>')
def get_shipment(shipment_id: str):
    """배송 상세를 반환한다."""
    try:
        tracker = _get_tracker()
        record = tracker.get_shipment(shipment_id)
        return jsonify(_shipment_to_dict(record))
    except KeyError:
        return jsonify({'error': 'Shipment not found'}), 404
    except Exception as exc:
        logger.error('get_shipment error: %s', exc)
        return jsonify({'error': 'Internal server error'}), 500


# ---------------------------------------------------------------------------
# GET /shipments/<id>/tracking
# ---------------------------------------------------------------------------

@forwarding_bp.get('/shipments/<shipment_id>/tracking')
def get_shipment_tracking(shipment_id: str):
    """배송 추적 정보를 반환한다."""
    try:
        tracker = _get_tracker()
        record = tracker.update_tracking(shipment_id)
        events = [
            {
                'timestamp': ev.timestamp.isoformat(),
                'status': ev.status.value,
                'location': ev.location,
                'description': ev.description,
            }
            for ev in record.events
        ]
        return jsonify({
            'shipment_id': record.shipment_id,
            'status': record.status.value,
            'customs_status': record.customs_status,
            'events': events,
        })
    except KeyError:
        return jsonify({'error': 'Shipment not found'}), 404
    except Exception as exc:
        logger.error('get_shipment_tracking error: %s', exc)
        return jsonify({'error': 'Internal server error'}), 500


# ---------------------------------------------------------------------------
# POST /incoming/check
# ---------------------------------------------------------------------------

@forwarding_bp.post('/incoming/check')
def check_incoming():
    """입고를 확인한다."""
    data = request.get_json(force=True, silent=True) or {}
    order_id = data.get('order_id', '')
    tracking_number = data.get('tracking_number', '')
    agent_id = data.get('agent_id', 'moltail')

    if not tracking_number:
        return jsonify({'error': 'tracking_number is required'}), 400

    try:
        verifier = _get_verifier()
        record = verifier.verify(order_id=order_id, tracking_number=tracking_number, agent_id=agent_id)
        return jsonify(_incoming_to_dict(record)), 201
    except Exception as exc:
        logger.error('check_incoming error: %s', exc)
        return jsonify({'error': 'Internal server error'}), 500


# ---------------------------------------------------------------------------
# GET /incoming
# ---------------------------------------------------------------------------

@forwarding_bp.get('/incoming')
def list_incoming():
    """입고 기록 목록을 반환한다."""
    try:
        from ..forwarding.incoming import IncomingStatus
        status_param = request.args.get('status')
        status = IncomingStatus(status_param) if status_param else None
        verifier = _get_verifier()
        records = verifier.list_records(status=status)
        return jsonify([_incoming_to_dict(r) for r in records])
    except Exception as exc:
        logger.error('list_incoming error: %s', exc)
        return jsonify({'error': 'Internal server error'}), 500


# ---------------------------------------------------------------------------
# GET /incoming/<id>
# ---------------------------------------------------------------------------

@forwarding_bp.get('/incoming/<record_id>')
def get_incoming(record_id: str):
    """입고 기록 상세를 반환한다."""
    try:
        verifier = _get_verifier()
        record = verifier.check_status(record_id)
        return jsonify(_incoming_to_dict(record))
    except KeyError:
        return jsonify({'error': 'Incoming record not found'}), 404
    except Exception as exc:
        logger.error('get_incoming error: %s', exc)
        return jsonify({'error': 'Internal server error'}), 500


# ---------------------------------------------------------------------------
# POST /consolidation
# ---------------------------------------------------------------------------

@forwarding_bp.post('/consolidation')
def create_consolidation():
    """합배송 그룹을 생성한다."""
    data = request.get_json(force=True, silent=True) or {}
    order_ids = data.get('order_ids', [])
    agent_id = data.get('agent_id', 'moltail')
    estimated_weight_kg = float(data.get('estimated_weight_kg', 0.0))

    if not order_ids:
        return jsonify({'error': 'order_ids is required'}), 400

    try:
        manager = _get_consolidation_manager()
        group = manager.create_group(order_ids, agent_id, estimated_weight_kg)
        return jsonify(_group_to_dict(group)), 201
    except Exception as exc:
        logger.error('create_consolidation error: %s', exc)
        return jsonify({'error': 'Internal server error'}), 500


# ---------------------------------------------------------------------------
# GET /consolidation
# ---------------------------------------------------------------------------

@forwarding_bp.get('/consolidation')
def list_consolidation():
    """합배송 그룹 목록을 반환한다."""
    try:
        from ..forwarding.consolidation import ConsolidationStatus
        status_param = request.args.get('status')
        status = ConsolidationStatus(status_param) if status_param else None
        manager = _get_consolidation_manager()
        groups = manager.list_groups(status=status)
        return jsonify([_group_to_dict(g) for g in groups])
    except Exception as exc:
        logger.error('list_consolidation error: %s', exc)
        return jsonify({'error': 'Internal server error'}), 500


# ---------------------------------------------------------------------------
# POST /consolidation/<id>/execute
# ---------------------------------------------------------------------------

@forwarding_bp.post('/consolidation/<group_id>/execute')
def execute_consolidation(group_id: str):
    """합배송 그룹을 실행한다."""
    try:
        manager = _get_consolidation_manager()
        group = manager.execute_group(group_id)
        return jsonify(_group_to_dict(group))
    except KeyError:
        return jsonify({'error': 'Consolidation group not found'}), 404
    except ValueError:
        return jsonify({'error': 'Invalid operation for current group status'}), 400
    except Exception as exc:
        logger.error('execute_consolidation error: %s', exc)
        return jsonify({'error': 'Internal server error'}), 500


# ---------------------------------------------------------------------------
# POST /estimate
# ---------------------------------------------------------------------------

@forwarding_bp.post('/estimate')
def estimate_cost():
    """배송 비용을 견적한다."""
    data = request.get_json(force=True, silent=True) or {}
    weight_kg = float(data.get('weight_kg', 0))
    country = data.get('country', 'KR')
    agent_id = data.get('agent_id', 'moltail')
    product_value_usd = float(data.get('product_value_usd', 0.0))
    category = data.get('category', 'default')
    service = data.get('service', 'standard')

    if weight_kg <= 0:
        return jsonify({'error': 'weight_kg must be positive'}), 400

    try:
        estimator = _get_estimator()
        cb = estimator.estimate(weight_kg, country, agent_id, product_value_usd, category, service)
        return jsonify({
            'base_shipping_usd': cb.base_shipping_usd,
            'fuel_surcharge_usd': cb.fuel_surcharge_usd,
            'insurance_usd': cb.insurance_usd,
            'agent_fee_usd': cb.agent_fee_usd,
            'customs_duty_usd': cb.customs_duty_usd,
            'vat_usd': cb.vat_usd,
            'total_usd': cb.total_usd,
            'currency': cb.currency,
        })
    except Exception as exc:
        logger.error('estimate_cost error: %s', exc)
        return jsonify({'error': 'Internal server error'}), 500


# ---------------------------------------------------------------------------
# GET /agents
# ---------------------------------------------------------------------------

@forwarding_bp.get('/agents')
def list_agents():
    """에이전트 목록을 반환한다."""
    try:
        manager = _get_agent_manager()
        return jsonify(manager.list_agents())
    except Exception as exc:
        logger.error('list_agents error: %s', exc)
        return jsonify({'error': 'Internal server error'}), 500


# ---------------------------------------------------------------------------
# GET /agents/<id>/recommend
# ---------------------------------------------------------------------------

@forwarding_bp.get('/agents/<agent_id>/recommend')
def recommend_agent(agent_id: str):  # noqa: ARG001 — path param kept for API consistency
    """에이전트를 추천한다."""
    priority = request.args.get('priority', 'balanced')
    try:
        manager = _get_agent_manager()
        agent = manager.recommend_agent(priority=priority)
        return jsonify({
            'agent_id': agent.agent_id,
            'name': agent.name,
            'reliability': agent.reliability_score,
            'priority_used': priority,
        })
    except Exception as exc:
        logger.error('recommend_agent error: %s', exc)
        return jsonify({'error': 'Internal server error'}), 500


# ---------------------------------------------------------------------------
# GET /dashboard
# ---------------------------------------------------------------------------

@forwarding_bp.get('/dashboard')
def get_dashboard():
    """대시보드 데이터를 반환한다."""
    try:
        from ..forwarding.dashboard import ForwardingDashboard
        dashboard = ForwardingDashboard(
            verifier=_get_verifier(),
            manager=_get_consolidation_manager(),
            tracker=_get_tracker(),
            estimator=_get_estimator(),
            agent_manager=_get_agent_manager(),
        )
        summary = dashboard.get_summary()
        agent_stats = dashboard.get_agent_stats()
        return jsonify({
            'summary': summary,
            'agent_stats': agent_stats,
        })
    except Exception as exc:
        logger.error('get_dashboard error: %s', exc)
        return jsonify({'error': 'Internal server error'}), 500


# ---------------------------------------------------------------------------
# Phase 83: 배송대행 통합 자동화 엔드포인트
# ---------------------------------------------------------------------------

# POST /inbound/register
@forwarding_bp.post('/inbound/register')
def inbound_register():
    """해외 구매 주문에서 입고를 등록한다."""
    data = request.get_json(force=True, silent=True) or {}
    purchase_order_id = data.get('purchase_order_id', '')
    product_name = data.get('product_name', '')
    provider = data.get('provider', 'malltail')

    if not purchase_order_id or not product_name:
        return jsonify({'error': 'purchase_order_id and product_name are required'}), 400

    try:
        engine = _get_fwd_engine()
        registration = engine.register_inbound_from_purchase(
            purchase_order_id=purchase_order_id,
            product_name=product_name,
            provider=provider,
            quantity=int(data.get('quantity', 1)),
            weight_kg=float(data.get('weight_kg', 0.0)),
            customer_order_id=data.get('customer_order_id', ''),
            origin_country=data.get('origin_country', 'US'),
            destination_country=data.get('destination_country', 'KR'),
        )
        return jsonify(registration.to_dict()), 201
    except KeyError as exc:
        return jsonify({'error': str(exc)}), 404
    except Exception as exc:
        logger.error('inbound_register error: %s', exc)
        return jsonify({'error': 'Internal server error'}), 500


# POST /arrival/confirm
@forwarding_bp.post('/arrival/confirm')
def arrival_confirm():
    """패키지 도착 이벤트를 확인한다."""
    data = request.get_json(force=True, silent=True) or {}
    package_id = data.get('package_id', '')
    registration_id = data.get('registration_id', '')

    if not package_id or not registration_id:
        return jsonify({'error': 'package_id and registration_id are required'}), 400

    try:
        engine = _get_fwd_engine()
        registration = engine.confirm_arrival(package_id, registration_id)
        return jsonify(registration.to_dict())
    except KeyError as exc:
        return jsonify({'error': str(exc)}), 404
    except Exception as exc:
        logger.error('arrival_confirm error: %s', exc)
        return jsonify({'error': 'Internal server error'}), 500


# POST /consolidate
@forwarding_bp.post('/consolidate')
def consolidate():
    """다중 패키지 합배송을 요청한다."""
    data = request.get_json(force=True, silent=True) or {}
    package_ids = data.get('package_ids', [])
    provider = data.get('provider', 'malltail')
    destination_country = data.get('destination_country', 'KR')

    if not package_ids:
        return jsonify({'error': 'package_ids is required'}), 400

    try:
        engine = _get_fwd_engine()
        req = engine.request_consolidation(
            package_ids=package_ids,
            provider=provider,
            destination_country=destination_country,
        )
        return jsonify(req.to_dict()), 201
    except KeyError as exc:
        return jsonify({'error': str(exc)}), 404
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:
        logger.error('consolidate error: %s', exc)
        return jsonify({'error': 'Internal server error'}), 500


# POST /outbound/request
@forwarding_bp.post('/outbound/request')
def outbound_request():
    """출고 배송을 요청한다."""
    data = request.get_json(force=True, silent=True) or {}
    package_ids = data.get('package_ids', [])
    provider = data.get('provider', 'malltail')
    destination_country = data.get('destination_country', 'KR')
    recipient_name = data.get('recipient_name', '')
    recipient_address = data.get('recipient_address', '')

    if not package_ids:
        return jsonify({'error': 'package_ids is required'}), 400
    if not recipient_name or not recipient_address:
        return jsonify({'error': 'recipient_name and recipient_address are required'}), 400

    try:
        engine = _get_fwd_engine()
        req = engine.request_outbound(
            package_ids=package_ids,
            provider=provider,
            destination_country=destination_country,
            recipient_name=recipient_name,
            recipient_address=recipient_address,
        )
        return jsonify(req.to_dict()), 201
    except KeyError as exc:
        return jsonify({'error': str(exc)}), 404
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:
        logger.error('outbound_request error: %s', exc)
        return jsonify({'error': 'Internal server error'}), 500


# GET /status/<package_id>
@forwarding_bp.get('/status/<package_id>')
def get_forwarding_status(package_id: str):
    """배송대행 패키지 상태를 조회한다."""
    try:
        engine = _get_fwd_engine()
        status = engine.sync_status(package_id)
        return jsonify(status.to_dict())
    except KeyError:
        return jsonify({'error': 'Package not found'}), 404
    except Exception as exc:
        logger.error('get_forwarding_status error: %s', exc)
        return jsonify({'error': 'Internal server error'}), 500
