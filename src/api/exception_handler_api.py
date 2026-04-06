"""src/api/exception_handler_api.py — 예외 처리 API Blueprint (Phase 105).

Blueprint: /api/v1/exceptions

엔드포인트:
  GET  /cases                     — 예외 케이스 목록
  GET  /cases/<id>                — 예외 케이스 상세
  POST /cases/<id>/resolve        — 수동 해결
  POST /cases/<id>/escalate       — 에스컬레이션
  POST /cases/<id>/retry          — 재시도
  POST /damage/report             — 훼손 신고
  GET  /damage/<id>               — 훼손 상세
  GET  /price-alerts              — 가격 알림 목록
  POST /price-alerts/configure    — 알림 설정
  GET  /retries                   — 재시도 이력
  GET  /retries/<id>              — 재시도 상세
  GET  /recovery/stats            — 복구 통계
  GET  /dashboard                 — 대시보드 데이터
  POST /simulate                  — 예외 시뮬레이션 (테스트용)
"""
from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

exception_handler_bp = Blueprint(
    'exception_handler',
    __name__,
    url_prefix='/api/v1/exceptions',
)

# ── 지연 초기화 ──────────────────────────────────────────────────────────────
_engine = None
_damage_handler = None
_price_detector = None
_retry_manager = None
_recovery_service = None
_delay_handler = None
_payment_handler = None
_dashboard = None


def _get_engine():
    global _engine
    if _engine is None:
        from ..exception_handler.engine import ExceptionEngine
        _engine = ExceptionEngine()
    return _engine


def _get_damage():
    global _damage_handler
    if _damage_handler is None:
        from ..exception_handler.damage_handler import DamageHandler
        _damage_handler = DamageHandler()
    return _damage_handler


def _get_price_detector():
    global _price_detector
    if _price_detector is None:
        from ..exception_handler.price_detector import PriceChangeDetector
        _price_detector = PriceChangeDetector()
    return _price_detector


def _get_retry():
    global _retry_manager
    if _retry_manager is None:
        from ..exception_handler.retry_manager import RetryManager
        _retry_manager = RetryManager()
    return _retry_manager


def _get_recovery():
    global _recovery_service
    if _recovery_service is None:
        from ..exception_handler.auto_recovery import AutoRecoveryService
        _recovery_service = AutoRecoveryService()
    return _recovery_service


def _get_delay():
    global _delay_handler
    if _delay_handler is None:
        from ..exception_handler.delay_handler import DeliveryDelayHandler
        _delay_handler = DeliveryDelayHandler()
    return _delay_handler


def _get_payment():
    global _payment_handler
    if _payment_handler is None:
        from ..exception_handler.payment_failure import PaymentFailureHandler
        _payment_handler = PaymentFailureHandler()
    return _payment_handler


def _get_dashboard():
    global _dashboard
    if _dashboard is None:
        from ..exception_handler.dashboard import ExceptionDashboard
        _dashboard = ExceptionDashboard(
            engine=_get_engine(),
            damage_handler=_get_damage(),
            price_detector=_get_price_detector(),
            retry_manager=_get_retry(),
            recovery_service=_get_recovery(),
            delay_handler=_get_delay(),
            payment_handler=_get_payment(),
        )
    return _dashboard


# ── 예외 케이스 ───────────────────────────────────────────────────────────────

@exception_handler_bp.get('/cases')
def list_cases():
    """GET /cases — 예외 케이스 목록."""
    from ..exception_handler.engine import ExceptionStatus, ExceptionType, ExceptionSeverity
    status_str = request.args.get('status')
    type_str = request.args.get('type')
    severity_str = request.args.get('severity')

    status = None
    exc_type = None
    severity = None

    if status_str:
        try:
            status = ExceptionStatus(status_str)
        except ValueError:
            return jsonify({'error': f'유효하지 않은 상태: {status_str}'}), 400
    if type_str:
        try:
            exc_type = ExceptionType(type_str)
        except ValueError:
            return jsonify({'error': f'유효하지 않은 예외 유형: {type_str}'}), 400
    if severity_str:
        try:
            severity = ExceptionSeverity(severity_str)
        except ValueError:
            return jsonify({'error': f'유효하지 않은 심각도: {severity_str}'}), 400

    cases = _get_engine().list_cases(status=status, exception_type=exc_type, severity=severity)
    return jsonify({'cases': [c.to_dict() for c in cases], 'total': len(cases)})


@exception_handler_bp.get('/cases/<case_id>')
def get_case(case_id: str):
    """GET /cases/<id> — 예외 케이스 상세."""
    case = _get_engine().get_case(case_id)
    if not case:
        return jsonify({'error': f'예외 케이스를 찾을 수 없습니다: {case_id}'}), 404
    return jsonify(case.to_dict())


@exception_handler_bp.post('/cases/<case_id>/resolve')
def resolve_case(case_id: str):
    """POST /cases/<id>/resolve — 수동 해결."""
    data = request.get_json(silent=True) or {}
    resolution = data.get('resolution', '수동 해결')
    try:
        case = _get_engine().resolve(case_id, resolution)
        return jsonify(case.to_dict())
    except KeyError:
        return jsonify({'error': f'예외 케이스를 찾을 수 없습니다: {case_id}'}), 404


@exception_handler_bp.post('/cases/<case_id>/escalate')
def escalate_case(case_id: str):
    """POST /cases/<id>/escalate — 에스컬레이션."""
    data = request.get_json(silent=True) or {}
    reason = data.get('reason', '수동 에스컬레이션')
    try:
        case = _get_engine().escalate(case_id, reason)
        return jsonify(case.to_dict())
    except KeyError:
        return jsonify({'error': f'예외 케이스를 찾을 수 없습니다: {case_id}'}), 404


@exception_handler_bp.post('/cases/<case_id>/retry')
def retry_case(case_id: str):
    """POST /cases/<id>/retry — 재시도."""
    try:
        case = _get_engine().increment_retry(case_id)
        return jsonify(case.to_dict())
    except KeyError:
        return jsonify({'error': f'예외 케이스를 찾을 수 없습니다: {case_id}'}), 404


# ── 훼손 신고 ─────────────────────────────────────────────────────────────────

@exception_handler_bp.post('/damage/report')
def report_damage():
    """POST /damage/report — 훼손 신고."""
    from ..exception_handler.damage_handler import DamageType, DamageGrade
    data = request.get_json(silent=True) or {}
    order_id = data.get('order_id', '').strip()
    damage_type_str = data.get('damage_type', '').strip()
    grade_str = data.get('grade', '').strip()

    if not order_id:
        return jsonify({'error': 'order_id 필드가 필요합니다.'}), 400
    if not damage_type_str:
        return jsonify({'error': 'damage_type 필드가 필요합니다.'}), 400
    if not grade_str:
        return jsonify({'error': 'grade 필드가 필요합니다.'}), 400

    try:
        damage_type = DamageType(damage_type_str)
    except ValueError:
        return jsonify({'error': f'유효하지 않은 훼손 유형: {damage_type_str}'}), 400
    try:
        grade = DamageGrade(grade_str)
    except ValueError:
        return jsonify({'error': f'유효하지 않은 등급: {grade_str}'}), 400

    handler = _get_damage()
    report = handler.report_damage(
        order_id=order_id,
        damage_type=damage_type,
        grade=grade,
        photos=data.get('photos', []),
        description=data.get('description', ''),
    )
    item_price = float(data.get('item_price', 0.0))
    action = handler.determine_action(report.report_id, item_price)
    return jsonify({'report': report.to_dict(), 'action': action}), 201


@exception_handler_bp.get('/damage/<report_id>')
def get_damage_report(report_id: str):
    """GET /damage/<id> — 훼손 상세."""
    report = _get_damage().get_report(report_id)
    if not report:
        return jsonify({'error': f'훼손 보고를 찾을 수 없습니다: {report_id}'}), 404
    return jsonify(report.to_dict())


# ── 가격 알림 ─────────────────────────────────────────────────────────────────

@exception_handler_bp.get('/price-alerts')
def list_price_alerts():
    """GET /price-alerts — 가격 알림 목록."""
    product_id = request.args.get('product_id')
    ack_str = request.args.get('acknowledged')
    acknowledged = None
    if ack_str is not None:
        acknowledged = ack_str.lower() == 'true'
    alerts = _get_price_detector().list_alerts(product_id=product_id, acknowledged=acknowledged)
    return jsonify({'alerts': [a.to_dict() for a in alerts], 'total': len(alerts)})


@exception_handler_bp.post('/price-alerts/configure')
def configure_price_alerts():
    """POST /price-alerts/configure — 알림 설정."""
    data = request.get_json(silent=True) or {}
    drop = float(data.get('drop_threshold_pct', -10.0))
    surge = float(data.get('surge_threshold_pct', 10.0))
    _get_price_detector().configure(drop, surge)
    return jsonify({'drop_threshold_pct': drop, 'surge_threshold_pct': surge})


# ── 재시도 이력 ───────────────────────────────────────────────────────────────

@exception_handler_bp.get('/retries')
def list_retries():
    """GET /retries — 재시도 이력."""
    task_type = request.args.get('task_type')
    records = _get_retry().list_records(task_type=task_type)
    return jsonify({'retries': [r.to_dict() for r in records], 'total': len(records)})


@exception_handler_bp.get('/retries/<record_id>')
def get_retry(record_id: str):
    """GET /retries/<id> — 재시도 상세."""
    record = _get_retry().get_record(record_id)
    if not record:
        return jsonify({'error': f'재시도 레코드를 찾을 수 없습니다: {record_id}'}), 404
    return jsonify(record.to_dict())


# ── 복구 통계 ─────────────────────────────────────────────────────────────────

@exception_handler_bp.get('/recovery/stats')
def get_recovery_stats():
    """GET /recovery/stats — 복구 통계."""
    return jsonify(_get_recovery().get_stats())


# ── 대시보드 ─────────────────────────────────────────────────────────────────

@exception_handler_bp.get('/dashboard')
def get_dashboard():
    """GET /dashboard — 대시보드 데이터."""
    dashboard = _get_dashboard()
    return jsonify({
        'summary': dashboard.get_summary(),
        'trend': dashboard.get_exception_trend(),
        'cost_impact': dashboard.get_cost_impact(),
        'resolution_metrics': dashboard.get_resolution_metrics(),
    })


# ── 시뮬레이션 ────────────────────────────────────────────────────────────────

@exception_handler_bp.post('/simulate')
def simulate_exception():
    """POST /simulate — 예외 시뮬레이션 (테스트용)."""
    from ..exception_handler.engine import ExceptionType, ExceptionSeverity
    data = request.get_json(silent=True) or {}
    type_str = data.get('type', 'payment_failure')
    severity_str = data.get('severity')
    order_id = data.get('order_id', 'ORDER_SIM_001')

    try:
        exc_type = ExceptionType(type_str)
    except ValueError:
        return jsonify({'error': f'유효하지 않은 예외 유형: {type_str}'}), 400

    severity = None
    if severity_str:
        try:
            severity = ExceptionSeverity(severity_str)
        except ValueError:
            return jsonify({'error': f'유효하지 않은 심각도: {severity_str}'}), 400

    engine = _get_engine()
    case = engine.detect(
        exception_type=exc_type,
        order_id=order_id,
        severity=severity,
        metadata={'simulated': True},
        notes='시뮬레이션 케이스',
    )
    engine.analyze(case.case_id)
    engine.take_action(case.case_id, '자동 대응 시뮬레이션')

    return jsonify({'simulated': True, 'case': case.to_dict()}), 201
