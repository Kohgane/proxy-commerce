"""src/api/order_matching_api.py — 주문 소싱처 자동 매칭 API Blueprint (Phase 112).

Blueprint: /api/v1/order-matching
"""
from __future__ import annotations

import dataclasses
import logging
from typing import Any

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

order_matching_bp = Blueprint(
    'order_matching',
    __name__,
    url_prefix='/api/v1/order-matching',
)

# ── 지연 초기화 ──────────────────────────────────────────────────────────────
_matcher = None
_fulfillment_checker = None
_priority_manager = None
_risk_assessor = None
_sla_tracker = None
_dashboard = None


def _get_matcher():
    global _matcher
    if _matcher is None:
        from src.order_matching.matcher import OrderSourceMatcher
        _matcher = OrderSourceMatcher()
    return _matcher


def _get_fulfillment_checker():
    global _fulfillment_checker
    if _fulfillment_checker is None:
        from src.order_matching.fulfillment_checker import FulfillmentChecker
        _fulfillment_checker = FulfillmentChecker()
    return _fulfillment_checker


def _get_priority_manager():
    global _priority_manager
    if _priority_manager is None:
        from src.order_matching.source_priority import SourcePriorityManager
        _priority_manager = SourcePriorityManager()
    return _priority_manager


def _get_risk_assessor():
    global _risk_assessor
    if _risk_assessor is None:
        from src.order_matching.risk_assessor import OrderRiskAssessor
        _risk_assessor = OrderRiskAssessor()
    return _risk_assessor


def _get_sla_tracker():
    global _sla_tracker
    if _sla_tracker is None:
        from src.order_matching.sla_tracker import FulfillmentSLATracker
        _sla_tracker = FulfillmentSLATracker()
    return _sla_tracker


def _get_dashboard():
    global _dashboard
    if _dashboard is None:
        from src.order_matching.order_matching_dashboard import OrderMatchingDashboard
        _dashboard = OrderMatchingDashboard(
            matcher=_get_matcher(),
            fulfillment_checker=_get_fulfillment_checker(),
            risk_assessor=_get_risk_assessor(),
            sla_tracker=_get_sla_tracker(),
        )
    return _dashboard


def _to_dict(obj: Any) -> Any:
    """dataclass 또는 일반 객체를 dict 로 변환."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        raw = dataclasses.asdict(obj)
        return {k: (v.value if hasattr(v, 'value') else v) for k, v in raw.items()}
    if isinstance(obj, list):
        return [_to_dict(item) for item in obj]
    if isinstance(obj, dict):
        return {k: _to_dict(v) for k, v in obj.items()}
    if hasattr(obj, 'value'):
        return obj.value
    return obj


# ── 주문 매칭 엔드포인트 ─────────────────────────────────────────────────────

@order_matching_bp.post('/match/<order_id>')
def match_order(order_id: str):
    """주문 소싱처 매칭."""
    body = request.get_json(force=True, silent=True) or {}
    items = body.get('items')
    matcher = _get_matcher()
    if items:
        matcher.register_order(order_id, items)
    results = matcher.match_order(order_id)
    return jsonify([_to_dict(r) for r in results]), 200


@order_matching_bp.post('/match/product')
def match_product():
    """단일 상품 소싱처 매칭."""
    body = request.get_json(force=True, silent=True) or {}
    product_id = body.get('product_id', '')
    quantity = int(body.get('quantity', 1))
    if not product_id:
        return jsonify({'error': 'product_id 필수'}), 400
    result = _get_matcher().match_product(product_id, quantity)
    return jsonify(_to_dict(result)), 200


@order_matching_bp.post('/match/bulk')
def match_bulk():
    """일괄 주문 매칭."""
    body = request.get_json(force=True, silent=True) or {}
    order_ids = body.get('order_ids', [])
    if not order_ids:
        return jsonify({'error': 'order_ids 필수'}), 400
    results = _get_matcher().match_bulk_orders(order_ids)
    return jsonify({oid: [_to_dict(r) for r in res] for oid, res in results.items()}), 200


@order_matching_bp.get('/match/<order_id>')
def get_match_result(order_id: str):
    """매칭 결과 조회."""
    results = _get_matcher().get_match_result(order_id)
    if results is None:
        return jsonify({'error': '매칭 결과 없음'}), 404
    return jsonify([_to_dict(r) for r in results]), 200


@order_matching_bp.get('/match/history')
def get_match_history():
    """매칭 이력."""
    order_id = request.args.get('order_id')
    product_id = request.args.get('product_id')
    limit = int(request.args.get('limit', 50))
    results = _get_matcher().get_match_history(order_id=order_id, product_id=product_id, limit=limit)
    return jsonify([_to_dict(r) for r in results]), 200


@order_matching_bp.get('/match/stats')
def get_match_stats():
    """매칭 통계."""
    return jsonify(_get_matcher().get_match_stats()), 200


# ── 이행 확인 엔드포인트 ─────────────────────────────────────────────────────

@order_matching_bp.post('/fulfillment/check/<order_id>')
def check_fulfillment(order_id: str):
    """이행 가능성 확인."""
    body = request.get_json(force=True, silent=True) or {}
    source_id = body.get('source_id')
    checker = _get_fulfillment_checker()
    items = body.get('items')
    if items:
        checker.register_order(order_id, items)
    results = checker.check_fulfillment(order_id, source_id=source_id)
    return jsonify([_to_dict(r) for r in results]), 200


@order_matching_bp.post('/fulfillment/check/product')
def check_product_fulfillment():
    """상품 이행 확인."""
    body = request.get_json(force=True, silent=True) or {}
    product_id = body.get('product_id', '')
    quantity = int(body.get('quantity', 1))
    source_id = body.get('source_id')
    selling_price = float(body.get('selling_price', 0.0))
    if not product_id:
        return jsonify({'error': 'product_id 필수'}), 400
    result = _get_fulfillment_checker().check_product_fulfillment(
        product_id, quantity, source_id, selling_price=selling_price
    )
    return jsonify(_to_dict(result)), 200


@order_matching_bp.post('/fulfillment/handle-unfulfillable')
def handle_unfulfillable():
    """이행 불가 대응."""
    body = request.get_json(force=True, silent=True) or {}
    order_id = body.get('order_id', '')
    product_id = body.get('product_id', '')
    reason = body.get('reason', '')
    if not (order_id and product_id and reason):
        return jsonify({'error': 'order_id, product_id, reason 필수'}), 400
    action = _get_fulfillment_checker().handle_unfulfillable(order_id, product_id, reason)
    return jsonify(action), 200


# ── 소싱처 우선순위 엔드포인트 ───────────────────────────────────────────────

@order_matching_bp.get('/priorities/<product_id>')
def get_priorities(product_id: str):
    """우선순위 목록."""
    priorities = _get_priority_manager().get_priorities(product_id)
    return jsonify([_to_dict(p) for p in priorities]), 200


@order_matching_bp.post('/priorities/<product_id>')
def set_priority(product_id: str):
    """우선순위 설정."""
    body = request.get_json(force=True, silent=True) or {}
    source_id = body.get('source_id', '')
    priority_rank = int(body.get('priority_rank', 1))
    if not source_id:
        return jsonify({'error': 'source_id 필수'}), 400
    priority = _get_priority_manager().set_priority(product_id, source_id, priority_rank)
    return jsonify(_to_dict(priority)), 200


@order_matching_bp.post('/priorities/<product_id>/auto-rank')
def auto_rank(product_id: str):
    """자동 순위 산정."""
    priorities = _get_priority_manager().auto_rank_sources(product_id)
    return jsonify([_to_dict(p) for p in priorities]), 200


@order_matching_bp.post('/priorities/<product_id>/promote/<source_id>')
def promote_source(product_id: str, source_id: str):
    """소싱처 승격."""
    priority = _get_priority_manager().promote_backup(product_id, source_id)
    if priority is None:
        return jsonify({'error': '소싱처 없음'}), 404
    return jsonify(_to_dict(priority)), 200


@order_matching_bp.post('/priorities/<product_id>/demote/<source_id>')
def demote_source(product_id: str, source_id: str):
    """소싱처 강등."""
    body = request.get_json(force=True, silent=True) or {}
    reason = body.get('reason', 'manual')
    priority = _get_priority_manager().demote_source(product_id, source_id, reason)
    if priority is None:
        return jsonify({'error': '소싱처 없음'}), 404
    return jsonify(_to_dict(priority)), 200


# ── 리스크 평가 엔드포인트 ───────────────────────────────────────────────────

@order_matching_bp.get('/risk/<order_id>')
def get_order_risk(order_id: str):
    """주문 리스크 평가."""
    assessment = _get_risk_assessor().assess_order_risk(order_id)
    return jsonify(_to_dict(assessment)), 200


@order_matching_bp.get('/risk/product/<product_id>')
def get_product_risk(product_id: str):
    """상품 리스크 평가."""
    source_id = request.args.get('source_id')
    assessment = _get_risk_assessor().assess_product_risk(product_id, source_id=source_id)
    return jsonify(_to_dict(assessment)), 200


@order_matching_bp.get('/risk/high-risk')
def get_high_risk_orders():
    """고위험 주문 목록."""
    assessments = _get_risk_assessor().get_high_risk_orders()
    return jsonify([_to_dict(a) for a in assessments]), 200


@order_matching_bp.get('/risk/summary')
def get_risk_summary():
    """리스크 요약."""
    return jsonify(_get_risk_assessor().get_risk_summary()), 200


# ── SLA 추적 엔드포인트 ───────────────────────────────────────────────────────

@order_matching_bp.post('/sla/start/<order_id>')
def sla_start(order_id: str):
    """SLA 추적 시작."""
    status = _get_sla_tracker().start_tracking(order_id)
    return jsonify(_to_dict(status)), 200


@order_matching_bp.post('/sla/update/<order_id>')
def sla_update(order_id: str):
    """단계 업데이트."""
    from src.order_matching.sla_tracker import FulfillmentStage
    body = request.get_json(force=True, silent=True) or {}
    stage_str = body.get('stage', '')
    try:
        stage = FulfillmentStage(stage_str)
    except ValueError:
        return jsonify({'error': f'알 수 없는 단계: {stage_str}'}), 400
    status = _get_sla_tracker().update_stage(order_id, stage)
    if status is None:
        return jsonify({'error': 'SLA 추적 없음'}), 404
    return jsonify(_to_dict(status)), 200


@order_matching_bp.get('/sla/<order_id>')
def get_sla_status(order_id: str):
    """SLA 현황."""
    status = _get_sla_tracker().get_sla_status(order_id)
    if status is None:
        return jsonify({'error': 'SLA 추적 없음'}), 404
    return jsonify(_to_dict(status)), 200


@order_matching_bp.get('/sla/overdue')
def get_overdue():
    """SLA 초과 주문."""
    overdue = _get_sla_tracker().get_overdue_orders()
    return jsonify([_to_dict(s) for s in overdue]), 200


@order_matching_bp.get('/sla/performance')
def get_sla_performance():
    """SLA 달성률."""
    return jsonify(_get_sla_tracker().get_sla_performance()), 200


@order_matching_bp.get('/sla/stage-stats')
def get_stage_stats():
    """단계별 통계."""
    return jsonify(_get_sla_tracker().get_stage_duration_stats()), 200


# ── 대시보드 엔드포인트 ───────────────────────────────────────────────────────

@order_matching_bp.get('/dashboard')
def get_dashboard():
    """매칭 대시보드."""
    return jsonify(_get_dashboard().get_dashboard_data()), 200


@order_matching_bp.get('/dashboard/daily')
def get_daily_stats():
    """일별 통계."""
    date = request.args.get('date')
    return jsonify(_get_dashboard().get_daily_stats(date)), 200


@order_matching_bp.get('/dashboard/unfulfillable')
def get_unfulfillable_summary():
    """이행 불가 요약."""
    return jsonify(_get_dashboard().get_unfulfillable_summary()), 200
