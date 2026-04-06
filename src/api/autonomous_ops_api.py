"""src/api/autonomous_ops_api.py — 자율 운영 대시보드 API Blueprint (Phase 106).

Blueprint: /api/v1/autonomous-ops

엔드포인트:
  GET  /status                        — 운영 상태
  POST /mode                          — 운영 모드 변경
  GET  /revenue                       — 오늘 수익
  GET  /revenue/forecast              — 수익 예측
  GET  /revenue/breakdown             — 비용 분석
  GET  /margins                       — 마진 분석
  GET  /anomalies                     — 이상 알림 목록
  GET  /anomalies/<alert_id>          — 이상 알림 상세
  POST /anomalies/<alert_id>/acknowledge — 이상 알림 확인
  GET  /automation                    — 자동화 통계
  GET  /manual-queue                  — 수동 작업 큐
  POST /simulate                      — 시뮬레이션 실행
  GET  /simulate/<result_id>          — 시뮬레이션 결과
  GET  /dashboard                     — 통합 대시보드
  GET  /health                        — 헬스 체크
  GET  /actions                       — 자동 액션 이력
"""
from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

autonomous_ops_bp = Blueprint(
    'autonomous_ops',
    __name__,
    url_prefix='/api/v1/autonomous-ops',
)

# ── 지연 초기화 ──────────────────────────────────────────────────────────────
_engine = None
_revenue_tracker = None
_anomaly_detector = None
_autopilot = None
_intervention_tracker = None
_task_queue = None
_forecaster = None
_margin_analyzer = None
_simulation_engine = None
_dashboard = None


def _get_engine():
    global _engine
    if _engine is None:
        from ..autonomous_ops.engine import AutonomousOperationEngine
        _engine = AutonomousOperationEngine()
    return _engine


def _get_revenue_tracker():
    global _revenue_tracker
    if _revenue_tracker is None:
        from ..autonomous_ops.revenue_model import RevenueTracker
        _revenue_tracker = RevenueTracker()
    return _revenue_tracker


def _get_anomaly_detector():
    global _anomaly_detector
    if _anomaly_detector is None:
        from ..autonomous_ops.anomaly_detector import AnomalyDetector
        _anomaly_detector = AnomalyDetector()
    return _anomaly_detector


def _get_autopilot():
    global _autopilot
    if _autopilot is None:
        from ..autonomous_ops.autopilot import AutoPilotController
        _autopilot = AutoPilotController()
    return _autopilot


def _get_intervention_tracker():
    global _intervention_tracker
    if _intervention_tracker is None:
        from ..autonomous_ops.intervention import InterventionTracker
        _intervention_tracker = InterventionTracker()
    return _intervention_tracker


def _get_task_queue():
    global _task_queue
    if _task_queue is None:
        from ..autonomous_ops.intervention import ManualTaskQueue
        _task_queue = ManualTaskQueue()
    return _task_queue


def _get_forecaster():
    global _forecaster
    if _forecaster is None:
        from ..autonomous_ops.revenue_model import RevenueForecaster
        _forecaster = RevenueForecaster()
    return _forecaster


def _get_margin_analyzer():
    global _margin_analyzer
    if _margin_analyzer is None:
        from ..autonomous_ops.revenue_model import MarginAnalyzer
        _margin_analyzer = MarginAnalyzer()
    return _margin_analyzer


def _get_simulation_engine():
    global _simulation_engine
    if _simulation_engine is None:
        from ..autonomous_ops.simulation import SimulationEngine
        _simulation_engine = SimulationEngine()
    return _simulation_engine


def _get_dashboard():
    global _dashboard
    if _dashboard is None:
        from ..autonomous_ops.dashboard import UnifiedDashboard
        _dashboard = UnifiedDashboard(
            engine=_get_engine(),
            revenue_tracker=_get_revenue_tracker(),
            anomaly_detector=_get_anomaly_detector(),
            autopilot=_get_autopilot(),
            intervention_tracker=_get_intervention_tracker(),
            task_queue=_get_task_queue(),
        )
    return _dashboard


# ── 운영 상태 ─────────────────────────────────────────────────────────────────

@autonomous_ops_bp.get('/status')
def get_status():
    """GET /status — 운영 상태."""
    try:
        return jsonify(_get_engine().get_status().to_dict())
    except Exception as exc:
        logger.error("get_status 오류: %s", exc)
        return jsonify({'error': '서버 오류가 발생했습니다.'}), 500


@autonomous_ops_bp.post('/mode')
def set_mode():
    """POST /mode — 운영 모드 변경."""
    from ..autonomous_ops.engine import OperationMode
    data = request.get_json(silent=True) or {}
    mode_str = data.get('mode', '').strip()
    if not mode_str:
        return jsonify({'error': 'mode 필드가 필요합니다.'}), 400
    try:
        mode = OperationMode(mode_str)
    except ValueError:
        return jsonify({'error': f'유효하지 않은 모드: {mode_str}'}), 400
    try:
        return jsonify(_get_engine().set_mode(mode).to_dict())
    except Exception as exc:
        logger.error("set_mode 오류: %s", exc)
        return jsonify({'error': '서버 오류가 발생했습니다.'}), 500


# ── 수익 ──────────────────────────────────────────────────────────────────────

@autonomous_ops_bp.get('/revenue')
def get_revenue():
    """GET /revenue — 오늘 수익."""
    try:
        date_str = request.args.get('date')
        return jsonify(_get_revenue_tracker().get_daily_revenue(date_str))
    except Exception as exc:
        logger.error("get_revenue 오류: %s", exc)
        return jsonify({'error': '서버 오류가 발생했습니다.'}), 500


@autonomous_ops_bp.get('/revenue/forecast')
def get_revenue_forecast():
    """GET /revenue/forecast — 수익 예측."""
    try:
        periods = int(request.args.get('periods', 7))
        tracker = _get_revenue_tracker()
        records = tracker.list_records(limit=30)
        daily_revenues = [r['amount'] for r in records]
        forecast = _get_forecaster().forecast_next_period(daily_revenues, periods)
        return jsonify({'forecast': forecast, 'periods': periods})
    except Exception as exc:
        logger.error("get_revenue_forecast 오류: %s", exc)
        return jsonify({'error': '서버 오류가 발생했습니다.'}), 500


@autonomous_ops_bp.get('/revenue/breakdown')
def get_revenue_breakdown():
    """GET /revenue/breakdown — 비용 분석."""
    try:
        from ..autonomous_ops.revenue_model import CostBreakdown
        data = request.args
        breakdown = CostBreakdown(
            product_cost=float(data.get('product_cost', 0)),
            shipping=float(data.get('shipping', 0)),
            customs=float(data.get('customs', 0)),
            commission=float(data.get('commission', 0)),
            operation=float(data.get('operation', 0)),
            fx_loss=float(data.get('fx_loss', 0)),
        )
        return jsonify(breakdown.to_dict())
    except Exception as exc:
        logger.error("get_revenue_breakdown 오류: %s", exc)
        return jsonify({'error': '요청 파라미터가 유효하지 않습니다.'}), 400


# ── 마진 ──────────────────────────────────────────────────────────────────────

@autonomous_ops_bp.get('/margins')
def get_margins():
    """GET /margins — 마진 분석."""
    try:
        return jsonify(_get_margin_analyzer().analyze_by_stream([]))
    except Exception as exc:
        logger.error("get_margins 오류: %s", exc)
        return jsonify({'error': '서버 오류가 발생했습니다.'}), 500


# ── 이상 알림 ─────────────────────────────────────────────────────────────────

@autonomous_ops_bp.get('/anomalies')
def list_anomalies():
    """GET /anomalies — 이상 알림 목록."""
    try:
        ack_str = request.args.get('acknowledged')
        acknowledged = None
        if ack_str is not None:
            acknowledged = ack_str.lower() == 'true'
        alerts = _get_anomaly_detector().list_alerts(acknowledged=acknowledged)
        return jsonify({'alerts': alerts, 'total': len(alerts)})
    except Exception as exc:
        logger.error("list_anomalies 오류: %s", exc)
        return jsonify({'error': '서버 오류가 발생했습니다.'}), 500


@autonomous_ops_bp.get('/anomalies/<alert_id>')
def get_anomaly(alert_id: str):
    """GET /anomalies/<alert_id> — 이상 알림 상세."""
    try:
        detector = _get_anomaly_detector()
        alerts = detector.list_alerts()
        for a in alerts:
            if a['alert_id'] == alert_id:
                return jsonify(a)
        return jsonify({'error': f'알림을 찾을 수 없습니다: {alert_id}'}), 404
    except Exception as exc:
        logger.error("get_anomaly 오류: %s", exc)
        return jsonify({'error': '서버 오류가 발생했습니다.'}), 500


@autonomous_ops_bp.post('/anomalies/<alert_id>/acknowledge')
def acknowledge_anomaly(alert_id: str):
    """POST /anomalies/<alert_id>/acknowledge — 이상 알림 확인."""
    try:
        ok = _get_anomaly_detector().acknowledge(alert_id)
        if not ok:
            return jsonify({'error': f'알림을 찾을 수 없습니다: {alert_id}'}), 404
        return jsonify({'acknowledged': True, 'alert_id': alert_id})
    except Exception as exc:
        logger.error("acknowledge_anomaly 오류: %s", exc)
        return jsonify({'error': '서버 오류가 발생했습니다.'}), 500


# ── 자동화 ────────────────────────────────────────────────────────────────────

@autonomous_ops_bp.get('/automation')
def get_automation():
    """GET /automation — 자동화 통계."""
    try:
        return jsonify(_get_intervention_tracker().get_stats())
    except Exception as exc:
        logger.error("get_automation 오류: %s", exc)
        return jsonify({'error': '서버 오류가 발생했습니다.'}), 500


# ── 수동 작업 큐 ──────────────────────────────────────────────────────────────

@autonomous_ops_bp.get('/manual-queue')
def get_manual_queue():
    """GET /manual-queue — 수동 작업 큐."""
    try:
        limit = int(request.args.get('limit', 20))
        tasks = _get_task_queue().list_pending(limit=limit)
        return jsonify({'tasks': tasks, 'total': len(tasks)})
    except Exception as exc:
        logger.error("get_manual_queue 오류: %s", exc)
        return jsonify({'error': '서버 오류가 발생했습니다.'}), 500


# ── 시뮬레이션 ────────────────────────────────────────────────────────────────

@autonomous_ops_bp.post('/simulate')
def run_simulation():
    """POST /simulate — 시뮬레이션 실행."""
    from ..autonomous_ops.simulation import ScenarioType
    data = request.get_json(silent=True) or {}
    name = data.get('name', '시뮬레이션')
    type_str = data.get('type', 'price_crash')
    parameters = data.get('parameters', {})
    duration_hours = float(data.get('duration_hours', 24.0))
    base_metrics = data.get('base_metrics', {})

    try:
        scenario_type = ScenarioType(type_str)
    except ValueError:
        return jsonify({'error': f'유효하지 않은 시나리오 유형: {type_str}'}), 400

    try:
        sim = _get_simulation_engine()
        scenario = sim.create_scenario(name, scenario_type, parameters, duration_hours)
        result = sim.run_simulation(scenario.scenario_id, base_metrics)
        return jsonify({'scenario': scenario.to_dict(), 'result': result.to_dict()}), 201
    except Exception as exc:
        logger.error("run_simulation 오류: %s", exc)
        return jsonify({'error': '서버 오류가 발생했습니다.'}), 500


@autonomous_ops_bp.get('/simulate/<result_id>')
def get_simulation_result(result_id: str):
    """GET /simulate/<result_id> — 시뮬레이션 결과."""
    try:
        result = _get_simulation_engine().get_result(result_id)
        if not result:
            return jsonify({'error': f'결과를 찾을 수 없습니다: {result_id}'}), 404
        return jsonify(result.to_dict())
    except Exception as exc:
        logger.error("get_simulation_result 오류: %s", exc)
        return jsonify({'error': '서버 오류가 발생했습니다.'}), 500


# ── 통합 대시보드 ─────────────────────────────────────────────────────────────

@autonomous_ops_bp.get('/dashboard')
def get_dashboard():
    """GET /dashboard — 통합 대시보드."""
    try:
        return jsonify(_get_dashboard().get_full_dashboard())
    except Exception as exc:
        logger.error("get_dashboard 오류: %s", exc)
        return jsonify({'error': '서버 오류가 발생했습니다.'}), 500


# ── 헬스 체크 ─────────────────────────────────────────────────────────────────

@autonomous_ops_bp.get('/health')
def get_health():
    """GET /health — 헬스 체크."""
    try:
        return jsonify(_get_engine().run_health_check())
    except Exception as exc:
        logger.error("get_health 오류: %s", exc)
        return jsonify({'error': '서버 오류가 발생했습니다.'}), 500


# ── 자동 액션 이력 ────────────────────────────────────────────────────────────

@autonomous_ops_bp.get('/actions')
def get_actions():
    """GET /actions — 자동 액션 이력."""
    try:
        limit = int(request.args.get('limit', 50))
        history = _get_autopilot().get_history(limit=limit)
        return jsonify({'actions': history, 'total': len(history)})
    except Exception as exc:
        logger.error("get_actions 오류: %s", exc)
        return jsonify({'error': '서버 오류가 발생했습니다.'}), 500
