"""src/api/sourcing_discovery_api.py — 소싱 발굴 API Blueprint (Phase 115).

Blueprint: /api/v1/sourcing-discovery
"""
from __future__ import annotations

import dataclasses
import logging
from datetime import datetime
from typing import Any

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

sourcing_discovery_bp = Blueprint(
    'sourcing_discovery',
    __name__,
    url_prefix='/api/v1/sourcing-discovery',
)

# ── 지연 초기화 ──────────────────────────────────────────────────────────────
_trend_analyzer = None
_opportunity_finder = None
_market_gap_analyzer = None
_supplier_scout = None
_profitability_predictor = None
_discovery_pipeline = None
_alert_service = None
_dashboard = None


def _get_trend_analyzer():
    global _trend_analyzer
    if _trend_analyzer is None:
        from src.sourcing_discovery.trend_analyzer import TrendAnalyzer
        _trend_analyzer = TrendAnalyzer()
    return _trend_analyzer


def _get_opportunity_finder():
    global _opportunity_finder
    if _opportunity_finder is None:
        from src.sourcing_discovery.opportunity_finder import SourcingOpportunityFinder
        _opportunity_finder = SourcingOpportunityFinder()
    return _opportunity_finder


def _get_market_gap_analyzer():
    global _market_gap_analyzer
    if _market_gap_analyzer is None:
        from src.sourcing_discovery.market_gap_analyzer import MarketGapAnalyzer
        _market_gap_analyzer = MarketGapAnalyzer()
    return _market_gap_analyzer


def _get_supplier_scout():
    global _supplier_scout
    if _supplier_scout is None:
        from src.sourcing_discovery.supplier_scout import SupplierScout
        _supplier_scout = SupplierScout()
    return _supplier_scout


def _get_profitability_predictor():
    global _profitability_predictor
    if _profitability_predictor is None:
        from src.sourcing_discovery.profitability_predictor import ProfitabilityPredictor
        _profitability_predictor = ProfitabilityPredictor()
    return _profitability_predictor


def _get_discovery_pipeline():
    global _discovery_pipeline
    if _discovery_pipeline is None:
        from src.sourcing_discovery.discovery_pipeline import DiscoveryPipeline
        _discovery_pipeline = DiscoveryPipeline()
    return _discovery_pipeline


def _get_alert_service():
    global _alert_service
    if _alert_service is None:
        from src.sourcing_discovery.discovery_alerts import DiscoveryAlertService
        _alert_service = DiscoveryAlertService()
    return _alert_service


def _get_dashboard():
    global _dashboard
    if _dashboard is None:
        from src.sourcing_discovery.discovery_dashboard import DiscoveryDashboard
        _dashboard = DiscoveryDashboard()
    return _dashboard


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


# ── 트렌드 ────────────────────────────────────────────────────────────────────

@sourcing_discovery_bp.get('/trends')
def get_trends():
    """GET /trends — 카테고리 트렌드 분석."""
    try:
        trends = _get_trend_analyzer().analyze_category_trends(
            category=request.args.get('category'),
            platform=request.args.get('platform', 'naver'),
        )
        return jsonify([_serialize(t) for t in trends])
    except Exception as exc:
        logger.warning("get_trends 오류: %s", exc)
        return jsonify({'error': '요청을 처리하는 중 오류가 발생했습니다.'}), 500


@sourcing_discovery_bp.get('/trends/rising')
def get_rising_trends():
    """GET /trends/rising — 상승 트렌드."""
    try:
        trends = _get_trend_analyzer().get_rising_trends(
            limit=int(request.args.get('limit', 10)),
            platform=request.args.get('platform'),
        )
        return jsonify([_serialize(t) for t in trends])
    except Exception as exc:
        logger.warning("get_rising_trends 오류: %s", exc)
        return jsonify({'error': '요청을 처리하는 중 오류가 발생했습니다.'}), 500


@sourcing_discovery_bp.get('/trends/seasonal')
def get_seasonal_trends():
    """GET /trends/seasonal — 시즌 트렌드."""
    try:
        month = request.args.get('month')
        trends = _get_trend_analyzer().get_seasonal_opportunities(month=month)
        return jsonify([_serialize(t) for t in trends])
    except Exception as exc:
        logger.warning("get_seasonal_trends 오류: %s", exc)
        return jsonify({'error': '요청을 처리하는 중 오류가 발생했습니다.'}), 500


@sourcing_discovery_bp.get('/trends/summary')
def get_trend_summary():
    """GET /trends/summary — 트렌드 요약."""
    try:
        summary = _get_trend_analyzer().get_trend_summary()
        return jsonify(_serialize(summary))
    except Exception as exc:
        logger.warning("get_trend_summary 오류: %s", exc)
        return jsonify({'error': '요청을 처리하는 중 오류가 발생했습니다.'}), 500


# ── 기회 발굴 ────────────────────────────────────────────────────────────────

@sourcing_discovery_bp.post('/opportunities/discover')
def discover_opportunities():
    """POST /opportunities/discover — 소싱 기회 발굴."""
    try:
        body = request.get_json(force=True, silent=True) or {}
        opps = _get_opportunity_finder().discover_opportunities(
            method=body.get('method'),
            category=body.get('category'),
            limit=int(body.get('limit', 20)),
        )
        return jsonify([_serialize(o) for o in opps])
    except Exception as exc:
        logger.warning("discover_opportunities 오류: %s", exc)
        return jsonify({'error': '요청을 처리하는 중 오류가 발생했습니다.'}), 500


@sourcing_discovery_bp.get('/opportunities')
def get_opportunities():
    """GET /opportunities — 기회 목록."""
    try:
        opps = _get_opportunity_finder().get_opportunities(
            status=request.args.get('status'),
            method=request.args.get('method'),
            sort_by=request.args.get('sort_by', 'opportunity_score'),
        )
        return jsonify([_serialize(o) for o in opps])
    except Exception as exc:
        logger.warning("get_opportunities 오류: %s", exc)
        return jsonify({'error': '요청을 처리하는 중 오류가 발생했습니다.'}), 500


@sourcing_discovery_bp.get('/opportunities/<opportunity_id>')
def get_opportunity(opportunity_id: str):
    """GET /opportunities/<id> — 단일 기회 조회."""
    try:
        opp = _get_opportunity_finder().get_opportunity(opportunity_id)
        if opp is None:
            return jsonify({'error': '기회를 찾을 수 없습니다.'}), 404
        return jsonify(_serialize(opp))
    except Exception as exc:
        logger.warning("get_opportunity 오류: %s", exc)
        return jsonify({'error': '요청을 처리하는 중 오류가 발생했습니다.'}), 500


@sourcing_discovery_bp.post('/opportunities/<opportunity_id>/evaluate')
def evaluate_opportunity(opportunity_id: str):
    """POST /opportunities/<id>/evaluate — 기회 평가."""
    try:
        result = _get_opportunity_finder().evaluate_opportunity(opportunity_id)
        return jsonify(_serialize(result))
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 404
    except Exception as exc:
        logger.warning("evaluate_opportunity 오류: %s", exc)
        return jsonify({'error': '요청을 처리하는 중 오류가 발생했습니다.'}), 500


@sourcing_discovery_bp.post('/opportunities/<opportunity_id>/approve')
def approve_opportunity(opportunity_id: str):
    """POST /opportunities/<id>/approve — 기회 승인."""
    try:
        opp = _get_opportunity_finder().approve_opportunity(opportunity_id)
        return jsonify(_serialize(opp))
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 404
    except Exception as exc:
        logger.warning("approve_opportunity 오류: %s", exc)
        return jsonify({'error': '요청을 처리하는 중 오류가 발생했습니다.'}), 500


@sourcing_discovery_bp.post('/opportunities/<opportunity_id>/reject')
def reject_opportunity(opportunity_id: str):
    """POST /opportunities/<id>/reject — 기회 거절."""
    try:
        body = request.get_json(force=True, silent=True) or {}
        opp = _get_opportunity_finder().reject_opportunity(
            opportunity_id, reason=body.get('reason', '')
        )
        return jsonify(_serialize(opp))
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 404
    except Exception as exc:
        logger.warning("reject_opportunity 오류: %s", exc)
        return jsonify({'error': '요청을 처리하는 중 오류가 발생했습니다.'}), 500


# ── 마켓 갭 ──────────────────────────────────────────────────────────────────

@sourcing_discovery_bp.get('/market-gaps')
def get_market_gaps():
    """GET /market-gaps — 마켓 갭 분석."""
    try:
        gaps = _get_market_gap_analyzer().analyze_gaps(
            category=request.args.get('category')
        )
        return jsonify([_serialize(g) for g in gaps])
    except Exception as exc:
        logger.warning("get_market_gaps 오류: %s", exc)
        return jsonify({'error': '요청을 처리하는 중 오류가 발생했습니다.'}), 500


@sourcing_discovery_bp.get('/market-gaps/top')
def get_top_gaps():
    """GET /market-gaps/top — 상위 마켓 갭."""
    try:
        limit = int(request.args.get('limit', 5))
        gaps = _get_market_gap_analyzer().get_top_gaps(limit=limit)
        return jsonify([_serialize(g) for g in gaps])
    except Exception as exc:
        logger.warning("get_top_gaps 오류: %s", exc)
        return jsonify({'error': '요청을 처리하는 중 오류가 발생했습니다.'}), 500


@sourcing_discovery_bp.get('/market-gaps/by-category')
def get_gaps_by_category():
    """GET /market-gaps/by-category — 카테고리별 마켓 갭."""
    try:
        result = _get_market_gap_analyzer().get_gap_by_category()
        return jsonify({k: [_serialize(g) for g in v] for k, v in result.items()})
    except Exception as exc:
        logger.warning("get_gaps_by_category 오류: %s", exc)
        return jsonify({'error': '요청을 처리하는 중 오류가 발생했습니다.'}), 500


# ── 공급사 탐색 ───────────────────────────────────────────────────────────────

@sourcing_discovery_bp.post('/suppliers/scout')
def scout_suppliers():
    """POST /suppliers/scout — 공급사 탐색."""
    try:
        body = request.get_json(force=True, silent=True) or {}
        candidates = _get_supplier_scout().scout_suppliers(
            category=body.get('category'),
            platform=body.get('platform'),
            region=body.get('region'),
        )
        return jsonify([_serialize(c) for c in candidates])
    except Exception as exc:
        logger.warning("scout_suppliers 오류: %s", exc)
        return jsonify({'error': '요청을 처리하는 중 오류가 발생했습니다.'}), 500


@sourcing_discovery_bp.get('/suppliers/candidates')
def get_supplier_candidates():
    """GET /suppliers/candidates — 후보 공급사 목록."""
    try:
        candidates = _get_supplier_scout().get_candidates(
            status=request.args.get('status'),
            platform=request.args.get('platform'),
        )
        return jsonify([_serialize(c) for c in candidates])
    except Exception as exc:
        logger.warning("get_supplier_candidates 오류: %s", exc)
        return jsonify({'error': '요청을 처리하는 중 오류가 발생했습니다.'}), 500


@sourcing_discovery_bp.get('/suppliers/candidates/<candidate_id>')
def get_supplier_candidate(candidate_id: str):
    """GET /suppliers/candidates/<id> — 단일 후보 공급사."""
    try:
        scout = _get_supplier_scout()
        candidates = scout.get_candidates()
        candidate = next((c for c in candidates if c.candidate_id == candidate_id), None)
        if candidate is None:
            return jsonify({'error': '후보 공급사를 찾을 수 없습니다.'}), 404
        return jsonify(_serialize(candidate))
    except Exception as exc:
        logger.warning("get_supplier_candidate 오류: %s", exc)
        return jsonify({'error': '요청을 처리하는 중 오류가 발생했습니다.'}), 500


@sourcing_discovery_bp.post('/suppliers/candidates/<candidate_id>/approve')
def approve_supplier(candidate_id: str):
    """POST /suppliers/candidates/<id>/approve — 공급사 승인."""
    try:
        candidate = _get_supplier_scout().approve_supplier(candidate_id)
        return jsonify(_serialize(candidate))
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 404
    except Exception as exc:
        logger.warning("approve_supplier 오류: %s", exc)
        return jsonify({'error': '요청을 처리하는 중 오류가 발생했습니다.'}), 500


@sourcing_discovery_bp.post('/suppliers/candidates/<candidate_id>/reject')
def reject_supplier(candidate_id: str):
    """POST /suppliers/candidates/<id>/reject — 공급사 거절."""
    try:
        body = request.get_json(force=True, silent=True) or {}
        candidate = _get_supplier_scout().reject_supplier(
            candidate_id, reason=body.get('reason', '')
        )
        return jsonify(_serialize(candidate))
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 404
    except Exception as exc:
        logger.warning("reject_supplier 오류: %s", exc)
        return jsonify({'error': '요청을 처리하는 중 오류가 발생했습니다.'}), 500


# ── 수익성 예측 ───────────────────────────────────────────────────────────────

@sourcing_discovery_bp.post('/predict/profitability')
def predict_profitability():
    """POST /predict/profitability — 수익성 예측."""
    try:
        product_info = request.get_json(force=True, silent=True) or {}
        prediction = _get_profitability_predictor().predict_profitability(product_info)
        return jsonify(_serialize(prediction))
    except Exception as exc:
        logger.warning("predict_profitability 오류: %s", exc)
        return jsonify({'error': '요청을 처리하는 중 오류가 발생했습니다.'}), 500


@sourcing_discovery_bp.post('/predict/demand')
def predict_demand():
    """POST /predict/demand — 수요 예측."""
    try:
        product_info = request.get_json(force=True, silent=True) or {}
        result = _get_profitability_predictor().predict_demand(product_info)
        return jsonify(_serialize(result))
    except Exception as exc:
        logger.warning("predict_demand 오류: %s", exc)
        return jsonify({'error': '요청을 처리하는 중 오류가 발생했습니다.'}), 500


@sourcing_discovery_bp.post('/predict/sourcing-model')
def predict_sourcing_model():
    """POST /predict/sourcing-model — 소싱 모델 추천."""
    try:
        product_info = request.get_json(force=True, silent=True) or {}
        result = _get_profitability_predictor().recommend_sourcing_model(product_info)
        return jsonify(_serialize(result))
    except Exception as exc:
        logger.warning("predict_sourcing_model 오류: %s", exc)
        return jsonify({'error': '요청을 처리하는 중 오류가 발생했습니다.'}), 500


@sourcing_discovery_bp.post('/predict/batch')
def predict_batch():
    """POST /predict/batch — 일괄 수익성 예측."""
    try:
        body = request.get_json(force=True, silent=True) or {}
        products = body.get('products', [])
        predictions = _get_profitability_predictor().batch_predict(products)
        return jsonify([_serialize(p) for p in predictions])
    except Exception as exc:
        logger.warning("predict_batch 오류: %s", exc)
        return jsonify({'error': '요청을 처리하는 중 오류가 발생했습니다.'}), 500


# ── 파이프라인 ────────────────────────────────────────────────────────────────

@sourcing_discovery_bp.post('/pipeline/run')
def run_pipeline():
    """POST /pipeline/run — 파이프라인 실행."""
    try:
        run = _get_discovery_pipeline().run_pipeline()
        return jsonify(_serialize(run))
    except Exception as exc:
        logger.warning("run_pipeline 오류: %s", exc)
        return jsonify({'error': '요청을 처리하는 중 오류가 발생했습니다.'}), 500


@sourcing_discovery_bp.get('/pipeline/history')
def get_pipeline_history():
    """GET /pipeline/history — 파이프라인 이력."""
    try:
        limit = int(request.args.get('limit', 10))
        runs = _get_discovery_pipeline().get_pipeline_history(limit=limit)
        return jsonify([_serialize(r) for r in runs])
    except Exception as exc:
        logger.warning("get_pipeline_history 오류: %s", exc)
        return jsonify({'error': '요청을 처리하는 중 오류가 발생했습니다.'}), 500


@sourcing_discovery_bp.get('/pipeline/config')
def get_pipeline_config():
    """GET /pipeline/config — 파이프라인 설정."""
    try:
        config = _get_discovery_pipeline().get_pipeline_config()
        return jsonify(_serialize(config))
    except Exception as exc:
        logger.warning("get_pipeline_config 오류: %s", exc)
        return jsonify({'error': '요청을 처리하는 중 오류가 발생했습니다.'}), 500


@sourcing_discovery_bp.put('/pipeline/config')
def update_pipeline_config():
    """PUT /pipeline/config — 파이프라인 설정 업데이트."""
    try:
        updates = request.get_json(force=True, silent=True) or {}
        config = _get_discovery_pipeline().update_pipeline_config(updates)
        return jsonify(_serialize(config))
    except Exception as exc:
        logger.warning("update_pipeline_config 오류: %s", exc)
        return jsonify({'error': '요청을 처리하는 중 오류가 발생했습니다.'}), 500


# ── 알림 ─────────────────────────────────────────────────────────────────────

@sourcing_discovery_bp.get('/alerts')
def get_alerts():
    """GET /alerts — 알림 목록."""
    try:
        ack = request.args.get('acknowledged')
        acknowledged = None if ack is None else (ack.lower() == 'true')
        alerts = _get_alert_service().get_alerts(
            severity=request.args.get('severity'),
            alert_type=request.args.get('alert_type'),
            acknowledged=acknowledged,
        )
        return jsonify([_serialize(a) for a in alerts])
    except Exception as exc:
        logger.warning("get_alerts 오류: %s", exc)
        return jsonify({'error': '요청을 처리하는 중 오류가 발생했습니다.'}), 500


@sourcing_discovery_bp.get('/alerts/summary')
def get_alert_summary():
    """GET /alerts/summary — 알림 요약."""
    try:
        summary = _get_alert_service().get_alert_summary()
        return jsonify(_serialize(summary))
    except Exception as exc:
        logger.warning("get_alert_summary 오류: %s", exc)
        return jsonify({'error': '요청을 처리하는 중 오류가 발생했습니다.'}), 500


@sourcing_discovery_bp.post('/alerts/<alert_id>/acknowledge')
def acknowledge_alert(alert_id: str):
    """POST /alerts/<id>/acknowledge — 알림 확인."""
    try:
        alert = _get_alert_service().acknowledge_alert(alert_id)
        return jsonify(_serialize(alert))
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 404
    except Exception as exc:
        logger.warning("acknowledge_alert 오류: %s", exc)
        return jsonify({'error': '요청을 처리하는 중 오류가 발생했습니다.'}), 500


# ── 대시보드 ──────────────────────────────────────────────────────────────────

@sourcing_discovery_bp.get('/dashboard')
def get_dashboard():
    """GET /dashboard — 대시보드 데이터."""
    try:
        data = _get_dashboard().get_dashboard_data()
        return jsonify(_serialize(data))
    except Exception as exc:
        logger.warning("get_dashboard 오류: %s", exc)
        return jsonify({'error': '요청을 처리하는 중 오류가 발생했습니다.'}), 500


@sourcing_discovery_bp.get('/dashboard/weekly-report')
def get_weekly_report():
    """GET /dashboard/weekly-report — 주간 리포트."""
    try:
        report = _get_dashboard().get_weekly_discovery_report()
        return jsonify(_serialize(report))
    except Exception as exc:
        logger.warning("get_weekly_report 오류: %s", exc)
        return jsonify({'error': '요청을 처리하는 중 오류가 발생했습니다.'}), 500
