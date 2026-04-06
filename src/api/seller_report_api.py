"""src/api/seller_report_api.py — 셀러 성과 리포트 API Blueprint (Phase 114).

Blueprint: /api/v1/seller-report
"""
from __future__ import annotations

import dataclasses
import logging
from datetime import datetime
from typing import Any

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

seller_report_bp = Blueprint(
    'seller_report',
    __name__,
    url_prefix='/api/v1/seller-report',
)

# ── 지연 초기화 ──────────────────────────────────────────────────────────────
_metrics_engine = None
_channel_analyzer = None
_product_analyzer = None
_sourcing_analyzer = None
_hybrid_advisor = None
_report_generator = None
_alert_service = None
_goal_manager = None


def _get_metrics_engine():
    global _metrics_engine
    if _metrics_engine is None:
        from src.seller_report.metrics_engine import PerformanceMetricsEngine
        _metrics_engine = PerformanceMetricsEngine()
    return _metrics_engine


def _get_channel_analyzer():
    global _channel_analyzer
    if _channel_analyzer is None:
        from src.seller_report.channel_performance import ChannelPerformanceAnalyzer
        _channel_analyzer = ChannelPerformanceAnalyzer()
    return _channel_analyzer


def _get_product_analyzer():
    global _product_analyzer
    if _product_analyzer is None:
        from src.seller_report.product_performance import ProductPerformanceAnalyzer
        _product_analyzer = ProductPerformanceAnalyzer()
    return _product_analyzer


def _get_sourcing_analyzer():
    global _sourcing_analyzer
    if _sourcing_analyzer is None:
        from src.seller_report.sourcing_performance import SourcingPerformanceAnalyzer
        _sourcing_analyzer = SourcingPerformanceAnalyzer()
    return _sourcing_analyzer


def _get_hybrid_advisor():
    global _hybrid_advisor
    if _hybrid_advisor is None:
        from src.seller_report.hybrid_model_advisor import HybridModelAdvisor
        _hybrid_advisor = HybridModelAdvisor()
    return _hybrid_advisor


def _get_report_generator():
    global _report_generator
    if _report_generator is None:
        from src.seller_report.report_generator import PerformanceReportGenerator
        _report_generator = PerformanceReportGenerator()
    return _report_generator


def _get_alert_service():
    global _alert_service
    if _alert_service is None:
        from src.seller_report.performance_alerts import PerformanceAlertService
        _alert_service = PerformanceAlertService()
    return _alert_service


def _get_goal_manager():
    global _goal_manager
    if _goal_manager is None:
        from src.seller_report.goal_manager import PerformanceGoalManager
        _goal_manager = PerformanceGoalManager()
    return _goal_manager


def _serialize(obj: Any) -> Any:
    """dataclass / Enum / date 직렬화."""
    import dataclasses as dc
    from datetime import date, datetime
    from enum import Enum

    if dc.is_dataclass(obj) and not isinstance(obj, type):
        return {k: _serialize(v) for k, v in dc.asdict(obj).items()}
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if isinstance(obj, list):
        return [_serialize(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    return obj


# ── 메트릭 ────────────────────────────────────────────────────────────────────

@seller_report_bp.get('/metrics')
def get_metrics():
    """GET /metrics — 핵심 KPI."""
    period = request.args.get('period', 'daily')
    engine = _get_metrics_engine()
    try:
        metrics = engine.calculate_metrics(period)
        return jsonify(_serialize(metrics))
    except Exception as exc:
        logger.warning("get_metrics 오류: %s", exc)
        return jsonify({'error': '요청을 처리하는 중 오류가 발생했습니다.'}), 500


@seller_report_bp.get('/metrics/summary')
def get_metrics_summary():
    """GET /metrics/summary — KPI 요약."""
    engine = _get_metrics_engine()
    try:
        summary = engine.get_kpi_summary()
        return jsonify(_serialize(summary))
    except Exception as exc:
        logger.warning("get_metrics_summary 오류: %s", exc)
        return jsonify({'error': '요청을 처리하는 중 오류가 발생했습니다.'}), 500


@seller_report_bp.get('/metrics/compare')
def compare_metrics():
    """GET /metrics/compare — 기간 비교."""
    period1 = request.args.get('period1', 'weekly')
    period2 = request.args.get('period2', 'monthly')
    engine = _get_metrics_engine()
    try:
        result = engine.compare_periods(period1, period2)
        return jsonify(_serialize(result))
    except Exception as exc:
        logger.warning("compare_metrics 오류: %s", exc)
        return jsonify({'error': '요청을 처리하는 중 오류가 발생했습니다.'}), 500


@seller_report_bp.get('/metrics/trend/<metric_name>')
def get_metric_trend(metric_name: str):
    """GET /metrics/trend/<metric_name> — 메트릭 추이."""
    period = request.args.get('period', 'daily')
    interval = int(request.args.get('interval', 7))
    engine = _get_metrics_engine()
    try:
        trend = engine.get_metric_trend(metric_name, period=period, interval=interval)
        return jsonify({'metric_name': metric_name, 'trend': trend})
    except Exception as exc:
        logger.warning("get_metric_trend 오류: %s", exc)
        return jsonify({'error': '요청을 처리하는 중 오류가 발생했습니다.'}), 500


# ── 채널 성과 ─────────────────────────────────────────────────────────────────

@seller_report_bp.get('/channel')
def get_channels():
    """GET /channel — 채널별 성과."""
    period = request.args.get('period', 'monthly')
    analyzer = _get_channel_analyzer()
    try:
        channels = analyzer.compare_channels(period)
        return jsonify([_serialize(c) for c in channels])
    except Exception as exc:
        logger.warning("get_channels 오류: %s", exc)
        return jsonify({'error': '요청을 처리하는 중 오류가 발생했습니다.'}), 500


@seller_report_bp.get('/channel/compare')
def compare_channels():
    """GET /channel/compare — 채널 비교."""
    period = request.args.get('period', 'monthly')
    analyzer = _get_channel_analyzer()
    try:
        channels = analyzer.compare_channels(period)
        return jsonify([_serialize(c) for c in channels])
    except Exception as exc:
        logger.warning("compare_channels 오류: %s", exc)
        return jsonify({'error': '요청을 처리하는 중 오류가 발생했습니다.'}), 500


@seller_report_bp.get('/channel/recommendations')
def get_channel_recommendations():
    """GET /channel/recommendations — 채널 개선 제안."""
    analyzer = _get_channel_analyzer()
    try:
        recs = analyzer.get_channel_recommendations()
        return jsonify(recs)
    except Exception as exc:
        logger.warning("get_channel_recommendations 오류: %s", exc)
        return jsonify({'error': '요청을 처리하는 중 오류가 발생했습니다.'}), 500


@seller_report_bp.get('/channel/<channel>')
def get_channel(channel: str):
    """GET /channel/<channel> — 특정 채널 성과."""
    analyzer = _get_channel_analyzer()
    try:
        perf = analyzer.analyze_channel(channel)
        return jsonify(_serialize(perf))
    except Exception as exc:
        logger.warning("get_channel 오류: %s", exc)
        return jsonify({'error': '요청을 처리하는 중 오류가 발생했습니다.'}), 500


# ── 상품 성과 ─────────────────────────────────────────────────────────────────

@seller_report_bp.get('/product/ranking')
def get_product_ranking():
    """GET /product/ranking — 상품 순위."""
    sort_by = request.args.get('sort_by', 'revenue')
    limit = int(request.args.get('limit', 20))
    channel = request.args.get('channel')
    analyzer = _get_product_analyzer()
    try:
        ranking = analyzer.get_product_ranking(sort_by=sort_by, limit=limit, channel=channel)
        return jsonify([_serialize(p) for p in ranking])
    except Exception as exc:
        logger.warning("get_product_ranking 오류: %s", exc)
        return jsonify({'error': '요청을 처리하는 중 오류가 발생했습니다.'}), 500


@seller_report_bp.get('/product/grades')
def get_product_grades():
    """GET /product/grades — 상품 등급."""
    analyzer = _get_product_analyzer()
    try:
        grades = analyzer.get_product_grades()
        return jsonify({k: [_serialize(p) for p in v] for k, v in grades.items()})
    except Exception as exc:
        logger.warning("get_product_grades 오류: %s", exc)
        return jsonify({'error': '요청을 처리하는 중 오류가 발생했습니다.'}), 500


@seller_report_bp.get('/product/matrix')
def get_product_matrix():
    """GET /product/matrix — 수익성 매트릭스."""
    analyzer = _get_product_analyzer()
    try:
        matrix = analyzer.get_profitability_matrix()
        return jsonify({k: [_serialize(p) for p in v] for k, v in matrix.items()})
    except Exception as exc:
        logger.warning("get_product_matrix 오류: %s", exc)
        return jsonify({'error': '요청을 처리하는 중 오류가 발생했습니다.'}), 500


@seller_report_bp.get('/product/dead-stock')
def get_dead_stock():
    """GET /product/dead-stock — 장기 미판매."""
    days = int(request.args.get('days', 30))
    analyzer = _get_product_analyzer()
    try:
        dead = analyzer.get_dead_stock(days_threshold=days)
        return jsonify([_serialize(p) for p in dead])
    except Exception as exc:
        logger.warning("get_dead_stock 오류: %s", exc)
        return jsonify({'error': '요청을 처리하는 중 오류가 발생했습니다.'}), 500


@seller_report_bp.get('/product/trending')
def get_trending_products():
    """GET /product/trending — 급상승 상품."""
    limit = int(request.args.get('limit', 10))
    analyzer = _get_product_analyzer()
    try:
        trending = analyzer.get_trending_products(limit=limit)
        return jsonify([_serialize(p) for p in trending])
    except Exception as exc:
        logger.warning("get_trending_products 오류: %s", exc)
        return jsonify({'error': '요청을 처리하는 중 오류가 발생했습니다.'}), 500


@seller_report_bp.get('/product/<product_id>')
def get_product(product_id: str):
    """GET /product/<product_id> — 상품 성과."""
    analyzer = _get_product_analyzer()
    try:
        perf = analyzer.analyze_product(product_id)
        if perf is None:
            return jsonify({'error': f'상품 {product_id}를 찾을 수 없습니다.'}), 404
        return jsonify(_serialize(perf))
    except Exception as exc:
        logger.warning("get_product 오류: %s", exc)
        return jsonify({'error': '요청을 처리하는 중 오류가 발생했습니다.'}), 500


# ── 소싱처 성과 ───────────────────────────────────────────────────────────────

@seller_report_bp.get('/sourcing')
def get_sourcing():
    """GET /sourcing — 소싱처 성과."""
    analyzer = _get_sourcing_analyzer()
    try:
        sources = analyzer.compare_sources()
        return jsonify([_serialize(s) for s in sources])
    except Exception as exc:
        logger.warning("get_sourcing 오류: %s", exc)
        return jsonify({'error': '요청을 처리하는 중 오류가 발생했습니다.'}), 500


@seller_report_bp.get('/sourcing/ranking')
def get_sourcing_ranking():
    """GET /sourcing/ranking — 소싱처 순위."""
    analyzer = _get_sourcing_analyzer()
    try:
        ranking = analyzer.get_source_ranking()
        return jsonify([_serialize(s) for s in ranking])
    except Exception as exc:
        logger.warning("get_sourcing_ranking 오류: %s", exc)
        return jsonify({'error': '요청을 처리하는 중 오류가 발생했습니다.'}), 500


@seller_report_bp.get('/sourcing/problematic')
def get_problematic_sources():
    """GET /sourcing/problematic — 문제 소싱처."""
    analyzer = _get_sourcing_analyzer()
    try:
        sources = analyzer.get_problematic_sources()
        return jsonify([_serialize(s) for s in sources])
    except Exception as exc:
        logger.warning("get_problematic_sources 오류: %s", exc)
        return jsonify({'error': '요청을 처리하는 중 오류가 발생했습니다.'}), 500


@seller_report_bp.get('/sourcing/recommendations')
def get_sourcing_recommendations():
    """GET /sourcing/recommendations — 소싱처 개선 제안."""
    analyzer = _get_sourcing_analyzer()
    try:
        recs = analyzer.get_source_recommendations()
        return jsonify(recs)
    except Exception as exc:
        logger.warning("get_sourcing_recommendations 오류: %s", exc)
        return jsonify({'error': '요청을 처리하는 중 오류가 발생했습니다.'}), 500


@seller_report_bp.get('/sourcing/<source_id>')
def get_source(source_id: str):
    """GET /sourcing/<source_id> — 소싱처 상세."""
    analyzer = _get_sourcing_analyzer()
    try:
        perf = analyzer.analyze_source(source_id)
        if perf is None:
            return jsonify({'error': f'소싱처 {source_id}를 찾을 수 없습니다.'}), 404
        return jsonify(_serialize(perf))
    except Exception as exc:
        logger.warning("get_source 오류: %s", exc)
        return jsonify({'error': '요청을 처리하는 중 오류가 발생했습니다.'}), 500


# ── 하이브리드 모델 ────────────────────────────────────────────────────────────

@seller_report_bp.get('/hybrid/analysis')
def get_hybrid_analysis():
    """GET /hybrid/analysis — 전체 전환 분석."""
    advisor = _get_hybrid_advisor()
    try:
        recs = advisor.analyze_all_products()
        return jsonify([_serialize(r) for r in recs])
    except Exception as exc:
        logger.warning("get_hybrid_analysis 오류: %s", exc)
        return jsonify({'error': '요청을 처리하는 중 오류가 발생했습니다.'}), 500


@seller_report_bp.get('/hybrid/recommendations')
def get_hybrid_recommendations():
    """GET /hybrid/recommendations — 사입 전환 추천."""
    advisor = _get_hybrid_advisor()
    try:
        recs = advisor.get_stock_recommendations()
        return jsonify([_serialize(r) for r in recs])
    except Exception as exc:
        logger.warning("get_hybrid_recommendations 오류: %s", exc)
        return jsonify({'error': '요청을 처리하는 중 오류가 발생했습니다.'}), 500


@seller_report_bp.get('/hybrid/investment')
def get_hybrid_investment():
    """GET /hybrid/investment — 투자금 추정."""
    advisor = _get_hybrid_advisor()
    try:
        estimate = advisor.get_investment_estimate()
        return jsonify(_serialize(estimate))
    except Exception as exc:
        logger.warning("get_hybrid_investment 오류: %s", exc)
        return jsonify({'error': '요청을 처리하는 중 오류가 발생했습니다.'}), 500


@seller_report_bp.get('/hybrid/delivery-improvement')
def get_delivery_improvement():
    """GET /hybrid/delivery-improvement — 배송 개선 예측."""
    advisor = _get_hybrid_advisor()
    try:
        result = advisor.get_delivery_improvement_estimate()
        return jsonify(_serialize(result))
    except Exception as exc:
        logger.warning("get_delivery_improvement 오류: %s", exc)
        return jsonify({'error': '요청을 처리하는 중 오류가 발생했습니다.'}), 500


@seller_report_bp.get('/hybrid/summary')
def get_hybrid_summary():
    """GET /hybrid/summary — 하이브리드 요약."""
    advisor = _get_hybrid_advisor()
    try:
        summary = advisor.get_hybrid_summary()
        return jsonify(_serialize(summary))
    except Exception as exc:
        logger.warning("get_hybrid_summary 오류: %s", exc)
        return jsonify({'error': '요청을 처리하는 중 오류가 발생했습니다.'}), 500


@seller_report_bp.post('/hybrid/simulate')
def simulate_model_change():
    """POST /hybrid/simulate — 모델 변경 시뮬레이션."""
    data = request.get_json(force=True, silent=True) or {}
    product_id = data.get('product_id', '')
    new_model = data.get('new_model', '')
    if not product_id or not new_model:
        return jsonify({'error': 'product_id와 new_model이 필요합니다.'}), 400
    advisor = _get_hybrid_advisor()
    try:
        result = advisor.simulate_model_change(product_id, new_model)
        return jsonify(_serialize(result))
    except Exception as exc:
        logger.warning("simulate_model_change 오류: %s", exc)
        return jsonify({'error': '요청을 처리하는 중 오류가 발생했습니다.'}), 500


# ── 리포트 ────────────────────────────────────────────────────────────────────

@seller_report_bp.post('/report/daily')
def generate_daily_report():
    """POST /report/daily — 일간 리포트 생성."""
    generator = _get_report_generator()
    try:
        report = generator.generate_daily_report()
        return jsonify(_serialize(report))
    except Exception as exc:
        logger.warning("generate_daily_report 오류: %s", exc)
        return jsonify({'error': '요청을 처리하는 중 오류가 발생했습니다.'}), 500


@seller_report_bp.post('/report/weekly')
def generate_weekly_report():
    """POST /report/weekly — 주간 리포트 생성."""
    generator = _get_report_generator()
    try:
        report = generator.generate_weekly_report()
        return jsonify(_serialize(report))
    except Exception as exc:
        logger.warning("generate_weekly_report 오류: %s", exc)
        return jsonify({'error': '요청을 처리하는 중 오류가 발생했습니다.'}), 500


@seller_report_bp.post('/report/monthly')
def generate_monthly_report():
    """POST /report/monthly — 월간 리포트 생성."""
    generator = _get_report_generator()
    try:
        report = generator.generate_monthly_report()
        return jsonify(_serialize(report))
    except Exception as exc:
        logger.warning("generate_monthly_report 오류: %s", exc)
        return jsonify({'error': '요청을 처리하는 중 오류가 발생했습니다.'}), 500


@seller_report_bp.get('/report/history')
def get_report_history():
    """GET /report/history — 리포트 이력."""
    report_type = request.args.get('type')
    limit = int(request.args.get('limit', 10))
    generator = _get_report_generator()
    try:
        history = generator.get_report_history(report_type=report_type, limit=limit)
        return jsonify(_serialize(history))
    except Exception as exc:
        logger.warning("get_report_history 오류: %s", exc)
        return jsonify({'error': '요청을 처리하는 중 오류가 발생했습니다.'}), 500


# ── 알림 ──────────────────────────────────────────────────────────────────────

@seller_report_bp.get('/alerts')
def get_alerts():
    """GET /alerts — 알림 목록."""
    severity = request.args.get('severity')
    acknowledged = request.args.get('acknowledged')
    if acknowledged is not None:
        acknowledged = acknowledged.lower() == 'true'
    svc = _get_alert_service()
    try:
        alerts = svc.get_alerts(severity=severity, acknowledged=acknowledged)
        return jsonify([_serialize(a) for a in alerts])
    except Exception as exc:
        logger.warning("get_alerts 오류: %s", exc)
        return jsonify({'error': '요청을 처리하는 중 오류가 발생했습니다.'}), 500


@seller_report_bp.get('/alerts/summary')
def get_alert_summary():
    """GET /alerts/summary — 알림 요약."""
    svc = _get_alert_service()
    try:
        summary = svc.get_alert_summary()
        return jsonify(_serialize(summary))
    except Exception as exc:
        logger.warning("get_alert_summary 오류: %s", exc)
        return jsonify({'error': '요청을 처리하는 중 오류가 발생했습니다.'}), 500


@seller_report_bp.post('/alerts/<alert_id>/acknowledge')
def acknowledge_alert(alert_id: str):
    """POST /alerts/<alert_id>/acknowledge — 알림 확인."""
    svc = _get_alert_service()
    try:
        ok = svc.acknowledge_alert(alert_id)
        if not ok:
            return jsonify({'error': f'알림 {alert_id}를 찾을 수 없습니다.'}), 404
        return jsonify({'acknowledged': True, 'alert_id': alert_id})
    except Exception as exc:
        logger.warning("acknowledge_alert 오류: %s", exc)
        return jsonify({'error': '요청을 처리하는 중 오류가 발생했습니다.'}), 500


# ── 목표 ──────────────────────────────────────────────────────────────────────

@seller_report_bp.post('/goals')
def set_goal():
    """POST /goals — 목표 설정."""
    data = request.get_json(force=True, silent=True) or {}
    metric_name = data.get('metric_name', '')
    target_value = data.get('target_value')
    period = data.get('period', 'monthly')
    if not metric_name or target_value is None:
        return jsonify({'error': 'metric_name과 target_value가 필요합니다.'}), 400
    mgr = _get_goal_manager()
    try:
        goal = mgr.set_goal(metric_name, float(target_value), period)
        return jsonify(_serialize(goal)), 201
    except Exception as exc:
        logger.warning("set_goal 오류: %s", exc)
        return jsonify({'error': '요청을 처리하는 중 오류가 발생했습니다.'}), 500


@seller_report_bp.get('/goals')
def get_goals():
    """GET /goals — 목표 목록."""
    status = request.args.get('status')
    period = request.args.get('period')
    mgr = _get_goal_manager()
    try:
        goals = mgr.get_goals(status=status, period=period)
        return jsonify([_serialize(g) for g in goals])
    except Exception as exc:
        logger.warning("get_goals 오류: %s", exc)
        return jsonify({'error': '요청을 처리하는 중 오류가 발생했습니다.'}), 500


@seller_report_bp.get('/goals/dashboard')
def get_goal_dashboard():
    """GET /goals/dashboard — 목표 대시보드."""
    mgr = _get_goal_manager()
    try:
        dashboard = mgr.get_goal_dashboard()
        return jsonify(_serialize(dashboard))
    except Exception as exc:
        logger.warning("get_goal_dashboard 오류: %s", exc)
        return jsonify({'error': '요청을 처리하는 중 오류가 발생했습니다.'}), 500


@seller_report_bp.post('/goals/update-progress')
def update_goal_progress():
    """POST /goals/update-progress — 진행률 업데이트."""
    mgr = _get_goal_manager()
    try:
        updated = mgr.update_progress()
        return jsonify([_serialize(g) for g in updated])
    except Exception as exc:
        logger.warning("update_goal_progress 오류: %s", exc)
        return jsonify({'error': '요청을 처리하는 중 오류가 발생했습니다.'}), 500


# ── 대시보드 ──────────────────────────────────────────────────────────────────

@seller_report_bp.get('/dashboard')
def get_dashboard():
    """GET /dashboard — 종합 대시보드."""
    try:
        engine = _get_metrics_engine()
        metrics = engine.calculate_metrics('daily')
        kpi = engine.get_kpi_summary()

        channel_analyzer = _get_channel_analyzer()
        best_channel = channel_analyzer.get_best_channel()

        product_analyzer = _get_product_analyzer()
        top_products = product_analyzer.get_product_ranking(limit=5)

        hybrid_advisor = _get_hybrid_advisor()
        hybrid_summary = hybrid_advisor.get_hybrid_summary()

        alert_svc = _get_alert_service()
        alert_summary = alert_svc.get_alert_summary()

        return jsonify({
            'today_metrics': _serialize(metrics),
            'kpi_changes': _serialize(kpi),
            'best_channel': _serialize(best_channel),
            'top_products': [_serialize(p) for p in top_products],
            'hybrid_summary': _serialize(hybrid_summary),
            'alert_summary': _serialize(alert_summary),
            'generated_at': datetime.now().isoformat(),
        })
    except Exception as exc:
        logger.warning("get_dashboard 오류: %s", exc)
        return jsonify({'error': '요청을 처리하는 중 오류가 발생했습니다.'}), 500
