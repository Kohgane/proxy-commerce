"""src/api/virtual_inventory_api.py — 가상 재고 관리 API Blueprint (Phase 113).

Blueprint: /api/v1/virtual-inventory
"""
from __future__ import annotations

import dataclasses
import logging
from datetime import datetime
from typing import Any

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

virtual_inventory_bp = Blueprint(
    'virtual_inventory',
    __name__,
    url_prefix='/api/v1/virtual-inventory',
)

# ── 지연 초기화 ──────────────────────────────────────────────────────────────
_stock_pool = None
_aggregation_engine = None
_allocator = None
_sync_bridge = None
_alert_service = None
_analytics = None
_dashboard = None


def _get_stock_pool():
    global _stock_pool
    if _stock_pool is None:
        from src.virtual_inventory.virtual_stock import VirtualStockPool
        _stock_pool = VirtualStockPool()
    return _stock_pool


def _get_aggregation_engine():
    global _aggregation_engine
    if _aggregation_engine is None:
        from src.virtual_inventory.aggregation import StockAggregationEngine
        _aggregation_engine = StockAggregationEngine()
    return _aggregation_engine


def _get_allocator():
    global _allocator
    if _allocator is None:
        from src.virtual_inventory.source_allocator import SourceAllocator
        _allocator = SourceAllocator()
        _allocator.set_stock_pool(_get_stock_pool())
    return _allocator


def _get_sync_bridge():
    global _sync_bridge
    if _sync_bridge is None:
        from src.virtual_inventory.inventory_sync_bridge import InventorySyncBridge
        _sync_bridge = InventorySyncBridge()
        _sync_bridge.set_stock_pool(_get_stock_pool())
    return _sync_bridge


def _get_alert_service():
    global _alert_service
    if _alert_service is None:
        from src.virtual_inventory.stock_alerts import VirtualStockAlertService
        _alert_service = VirtualStockAlertService()
        _alert_service.set_stock_pool(_get_stock_pool())
    return _alert_service


def _get_analytics():
    global _analytics
    if _analytics is None:
        from src.virtual_inventory.stock_analytics import VirtualStockAnalytics
        _analytics = VirtualStockAnalytics()
        _analytics.set_stock_pool(_get_stock_pool())
    return _analytics


def _get_dashboard():
    global _dashboard
    if _dashboard is None:
        from src.virtual_inventory.virtual_inventory_dashboard import VirtualInventoryDashboard
        _dashboard = VirtualInventoryDashboard()
        _dashboard.set_components(
            _get_stock_pool(),
            _get_alert_service(),
            _get_analytics(),
            _get_sync_bridge(),
            _get_allocator(),
        )
    return _dashboard


def _serialize(obj: Any) -> Any:
    """dataclasses 및 datetime 직렬화."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        d = dataclasses.asdict(obj)
        return _serialize(d)
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialize(v) for v in obj]
    if isinstance(obj, datetime):
        return obj.isoformat()
    return obj


# ── 가상 재고 엔드포인트 ──────────────────────────────────────────────────────

@virtual_inventory_bp.get('/stock')
def list_stocks():
    """전체 가상 재고 목록."""
    pool = _get_stock_pool()
    stocks = pool.get_all_virtual_stocks()
    return jsonify(_serialize(stocks)), 200


@virtual_inventory_bp.get('/stock/<product_id>')
def get_stock(product_id: str):
    """단일 상품 가상 재고."""
    pool = _get_stock_pool()
    vs = pool.get_virtual_stock(product_id)
    if vs is None:
        return jsonify({'error': '상품을 찾을 수 없습니다'}), 404
    return jsonify(_serialize(vs)), 200


@virtual_inventory_bp.post('/stock/<product_id>/sources')
def add_source(product_id: str):
    """소싱처 재고 추가."""
    pool = _get_stock_pool()
    body = request.get_json(force=True, silent=True) or {}
    try:
        from src.virtual_inventory.virtual_stock import SourceStock
        from datetime import datetime, timezone
        last_checked_raw = body.get('last_checked_at')
        if last_checked_raw:
            try:
                last_checked = datetime.fromisoformat(last_checked_raw)
            except Exception:
                last_checked = datetime.now(timezone.utc)
        else:
            last_checked = datetime.now(timezone.utc)
        src = SourceStock(
            source_id=body['source_id'],
            source_name=body.get('source_name', ''),
            platform=body.get('platform', ''),
            available_qty=int(body.get('available_qty', 0)),
            price=float(body.get('price', 0)),
            currency=body.get('currency', 'KRW'),
            lead_time_days=int(body.get('lead_time_days', 0)),
            reliability_score=float(body.get('reliability_score', 1.0)),
            is_active=bool(body.get('is_active', True)),
            last_checked_at=last_checked,
        )
        pool.add_source_stock(product_id, src)
        return jsonify({'ok': True, 'source_id': src.source_id}), 201
    except KeyError as exc:
        return jsonify({'error': f'필수 필드 누락: {exc}'}), 400


@virtual_inventory_bp.get('/stock/<product_id>/sources')
def list_sources(product_id: str):
    """소싱처 재고 목록."""
    pool = _get_stock_pool()
    sources = pool.get_source_stocks(product_id)
    return jsonify(_serialize(sources)), 200


@virtual_inventory_bp.patch('/stock/<product_id>/sources/<source_id>')
def update_source(product_id: str, source_id: str):
    """소싱처 재고 업데이트."""
    pool = _get_stock_pool()
    body = request.get_json(force=True, silent=True) or {}
    ok = pool.update_source_stock(product_id, source_id, body)
    if not ok:
        return jsonify({'error': '소싱처를 찾을 수 없습니다'}), 404
    return jsonify({'ok': True}), 200


@virtual_inventory_bp.delete('/stock/<product_id>/sources/<source_id>')
def remove_source(product_id: str, source_id: str):
    """소싱처 제거."""
    pool = _get_stock_pool()
    ok = pool.remove_source_stock(product_id, source_id)
    if not ok:
        return jsonify({'error': '소싱처를 찾을 수 없습니다'}), 404
    return jsonify({'ok': True}), 200


# ── 예약 엔드포인트 ───────────────────────────────────────────────────────────

@virtual_inventory_bp.post('/stock/<product_id>/reserve')
def reserve(product_id: str):
    """재고 예약."""
    pool = _get_stock_pool()
    body = request.get_json(force=True, silent=True) or {}
    try:
        qty = int(body.get('quantity', 1))
        source_id = body.get('source_id')
        reservation = pool.reserve_stock(product_id, qty, source_id=source_id)
        return jsonify(_serialize(reservation)), 201
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400


@virtual_inventory_bp.get('/reservations')
def list_reservations():
    """전체 예약 목록."""
    pool = _get_stock_pool()
    product_id = request.args.get('product_id')
    reservations = pool.get_reservations(product_id=product_id)
    return jsonify(_serialize(reservations)), 200


@virtual_inventory_bp.get('/reservations/<reservation_id>')
def get_reservation(reservation_id: str):
    """단일 예약 조회."""
    pool = _get_stock_pool()
    reservations = pool.get_reservations()
    for r in reservations:
        if r.reservation_id == reservation_id:
            return jsonify(_serialize(r)), 200
    return jsonify({'error': '예약을 찾을 수 없습니다'}), 404


@virtual_inventory_bp.post('/reservations/<reservation_id>/release')
def release_reservation(reservation_id: str):
    """예약 해제."""
    pool = _get_stock_pool()
    ok = pool.release_reservation(reservation_id)
    if not ok:
        return jsonify({'error': '예약을 찾을 수 없습니다'}), 404
    return jsonify({'ok': True}), 200


@virtual_inventory_bp.post('/reservations/<reservation_id>/confirm')
def confirm_reservation(reservation_id: str):
    """예약 확정."""
    pool = _get_stock_pool()
    ok = pool.confirm_reservation(reservation_id)
    if not ok:
        return jsonify({'error': '예약을 찾을 수 없습니다'}), 404
    return jsonify({'ok': True}), 200


# ── 할당 엔드포인트 ───────────────────────────────────────────────────────────

@virtual_inventory_bp.post('/allocate')
def allocate():
    """소싱처 할당."""
    body = request.get_json(force=True, silent=True) or {}
    try:
        from src.virtual_inventory.source_allocator import AllocationStrategy
        product_id = body['product_id']
        qty = int(body['quantity'])
        strategy_str = body.get('strategy', AllocationStrategy.cheapest_first.value)
        strategy = AllocationStrategy(strategy_str)
        allocator = _get_allocator()
        result = allocator.allocate(product_id, qty, strategy)
        return jsonify(_serialize(result)), 201
    except KeyError as exc:
        return jsonify({'error': f'필수 필드 누락: {exc}'}), 400
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400


@virtual_inventory_bp.get('/allocations')
def list_allocations():
    """할당 히스토리."""
    allocator = _get_allocator()
    product_id = request.args.get('product_id')
    limit = int(request.args.get('limit', 50))
    results = allocator.get_allocation_history(product_id=product_id, limit=limit)
    return jsonify(_serialize(results)), 200


@virtual_inventory_bp.get('/allocations/<allocation_id>')
def get_allocation(allocation_id: str):
    """단일 할당 조회."""
    allocator = _get_allocator()
    result = allocator.get_allocation(allocation_id)
    if result is None:
        return jsonify({'error': '할당을 찾을 수 없습니다'}), 404
    return jsonify(_serialize(result)), 200


@virtual_inventory_bp.post('/allocations/<allocation_id>/cancel')
def cancel_allocation(allocation_id: str):
    """할당 취소."""
    allocator = _get_allocator()
    ok = allocator.cancel_allocation(allocation_id)
    if not ok:
        return jsonify({'error': '할당을 찾을 수 없습니다'}), 404
    return jsonify({'ok': True}), 200


# ── 집계 엔드포인트 ───────────────────────────────────────────────────────────

@virtual_inventory_bp.post('/aggregate')
def aggregate():
    """소싱처 재고 집계."""
    body = request.get_json(force=True, silent=True) or {}
    try:
        from src.virtual_inventory.aggregation import AggregationStrategy
        product_id = body.get('product_id', '')
        strategy_str = body.get('strategy', 'sum_active')
        strategy = AggregationStrategy(strategy_str)
        pool = _get_stock_pool()
        sources = pool.get_source_stocks(product_id)
        engine = _get_aggregation_engine()
        qty = engine.aggregate(sources, strategy)
        safety = engine.calculate_safety_stock(product_id, sources)
        return jsonify({'product_id': product_id, 'aggregated_qty': qty, 'safety_stock': safety}), 200
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400


# ── 동기화 엔드포인트 ─────────────────────────────────────────────────────────

@virtual_inventory_bp.post('/sync')
def sync_channels():
    """채널 동기화."""
    body = request.get_json(force=True, silent=True) or {}
    product_id = body.get('product_id')
    bridge = _get_sync_bridge()
    result = bridge.sync_to_channels(product_id=product_id)
    return jsonify(result), 200


@virtual_inventory_bp.get('/sync/status')
def sync_status():
    """동기화 상태."""
    bridge = _get_sync_bridge()
    return jsonify(bridge.get_sync_status()), 200


@virtual_inventory_bp.get('/sync/channels/<product_id>')
def channel_stock_map(product_id: str):
    """채널별 재고 맵."""
    bridge = _get_sync_bridge()
    return jsonify(bridge.get_channel_stock_map(product_id)), 200


@virtual_inventory_bp.get('/sync/discrepancies')
def stock_discrepancies():
    """채널 재고 불일치 목록."""
    bridge = _get_sync_bridge()
    return jsonify(bridge.get_stock_discrepancies()), 200


# ── 알림 엔드포인트 ───────────────────────────────────────────────────────────

@virtual_inventory_bp.post('/alerts/check')
def check_alerts():
    """알림 검사."""
    body = request.get_json(force=True, silent=True) or {}
    product_id = body.get('product_id')
    svc = _get_alert_service()
    alerts = svc.check_alerts(product_id=product_id)
    return jsonify(_serialize(alerts)), 200


@virtual_inventory_bp.get('/alerts')
def list_alerts():
    """알림 목록."""
    svc = _get_alert_service()
    severity = request.args.get('severity')
    alert_type = request.args.get('alert_type')
    ack_param = request.args.get('acknowledged')
    acknowledged = None if ack_param is None else ack_param.lower() == 'true'
    alerts = svc.get_alerts(severity=severity, alert_type=alert_type, acknowledged=acknowledged)
    return jsonify(_serialize(alerts)), 200


@virtual_inventory_bp.post('/alerts/<alert_id>/acknowledge')
def acknowledge_alert(alert_id: str):
    """알림 확인."""
    svc = _get_alert_service()
    ok = svc.acknowledge_alert(alert_id)
    if not ok:
        return jsonify({'error': '알림을 찾을 수 없습니다'}), 404
    return jsonify({'ok': True}), 200


@virtual_inventory_bp.get('/alerts/summary')
def alert_summary():
    """알림 요약."""
    svc = _get_alert_service()
    return jsonify(svc.get_alert_summary()), 200


# ── 분석 엔드포인트 ───────────────────────────────────────────────────────────

@virtual_inventory_bp.get('/analytics/summary')
def analytics_summary():
    """재고 요약 통계."""
    return jsonify(_get_analytics().get_stock_summary()), 200


@virtual_inventory_bp.get('/analytics/source-distribution')
def source_distribution():
    """소싱처 분포."""
    return jsonify(_get_analytics().get_source_distribution()), 200


@virtual_inventory_bp.get('/analytics/health')
def stock_health():
    """재고 건강도."""
    return jsonify(_get_analytics().get_stock_health()), 200


@virtual_inventory_bp.get('/analytics/turnover')
def turnover():
    """재고 회전율."""
    product_id = request.args.get('product_id')
    return jsonify(_get_analytics().get_turnover_analysis(product_id=product_id)), 200


@virtual_inventory_bp.get('/analytics/single-source')
def single_source_products():
    """단일 소싱처 상품 목록."""
    return jsonify(_get_analytics().get_single_source_products()), 200


@virtual_inventory_bp.get('/analytics/value')
def stock_value():
    """재고 가치."""
    product_id = request.args.get('product_id')
    currency = request.args.get('currency', 'KRW')
    return jsonify(_get_analytics().get_stock_value(product_id=product_id, currency=currency)), 200


# ── 대시보드 ──────────────────────────────────────────────────────────────────

@virtual_inventory_bp.get('/dashboard')
def dashboard():
    """통합 대시보드."""
    return jsonify(_get_dashboard().get_dashboard_data()), 200
