"""src/api/forecast_api.py — 수요 예측 API.

Flask Blueprint 기반 재고 수요 예측 API.

엔드포인트:
  GET /api/forecast/demand/<sku>  — SKU별 수요 예측
  GET /api/forecast/stockout-risk — 재고 소진 위험 상품
  GET /api/forecast/trends        — 상품 트렌드 분석
  GET /api/forecast/optimization  — 재고 최적화 권장 사항

환경변수:
  DASHBOARD_API_KEY — API 인증 키
"""

import logging

from flask import Blueprint, jsonify, request

from .auth_middleware import require_api_key

logger = logging.getLogger(__name__)

forecast_bp = Blueprint("forecast", __name__, url_prefix="/api/forecast")


def _get_predictor():
    from ..forecasting.demand_predictor import DemandPredictor
    return DemandPredictor()


def _get_optimizer():
    from ..forecasting.stock_optimizer import StockOptimizer
    return StockOptimizer()


def _get_trend_analyzer():
    from ..forecasting.trend_analyzer import TrendAnalyzer
    return TrendAnalyzer()


@forecast_bp.get("/demand/<sku>")
@require_api_key
def get_demand(sku: str):
    """SKU별 수요 예측 결과를 반환한다."""
    days_ahead = int(request.args.get("days_ahead", 30))
    predictor = _get_predictor()
    try:
        result = predictor.predict_demand(sku, days_ahead=days_ahead)
        seasonal = predictor.get_seasonal_pattern(sku)
        result['seasonal_pattern'] = seasonal
    except Exception as exc:
        logger.warning("수요 예측 실패 (%s): %s", sku, exc)
        return jsonify({"error": str(exc)}), 500

    return jsonify(result)


@forecast_bp.get("/stockout-risk")
@require_api_key
def get_stockout_risk():
    """재고 소진 위험 상품 목록을 반환한다."""
    days_horizon = int(request.args.get("days_horizon", 14))
    optimizer = _get_optimizer()
    try:
        at_risk = optimizer.get_stockout_risk(days_horizon=days_horizon)
    except Exception as exc:
        logger.warning("재고 소진 위험 조회 실패: %s", exc)
        at_risk = []

    return jsonify({"at_risk": at_risk, "count": len(at_risk),
                    "days_horizon": days_horizon})


@forecast_bp.get("/trends")
@require_api_key
def get_trends():
    """상품 트렌드 분석 결과를 반환한다."""
    period_days = int(request.args.get("period_days", 30))
    grade = request.args.get("grade")  # 선택적 등급 필터
    analyzer = _get_trend_analyzer()

    try:
        trends = analyzer.analyze_trends(period_days=period_days)
        if grade:
            trends = [t for t in trends if t.get('grade') == grade]
    except Exception as exc:
        logger.warning("트렌드 분석 실패: %s", exc)
        trends = []

    return jsonify({"trends": trends, "count": len(trends),
                    "period_days": period_days})


@forecast_bp.get("/optimization")
@require_api_key
def get_optimization():
    """재고 최적화 권장 사항을 반환한다."""
    optimizer = _get_optimizer()
    try:
        levels = optimizer.optimize_stock_levels()
        # reorder_needed인 항목만 또는 전체
        reorder_only = request.args.get("reorder_only", "0") == "1"
        if reorder_only:
            levels = [item for item in levels if item.get('reorder_needed')]
    except Exception as exc:
        logger.warning("재고 최적화 조회 실패: %s", exc)
        levels = []

    return jsonify({"recommendations": levels, "count": len(levels)})
