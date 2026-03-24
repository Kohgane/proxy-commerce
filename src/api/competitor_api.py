"""src/api/competitor_api.py — 경쟁사 분석 API.

Flask Blueprint 기반 경쟁사 가격 비교 및 분석 API.

엔드포인트:
  GET /api/competitor/prices              — 경쟁사 가격 비교 목록
  GET /api/competitor/prices/<sku>        — 특정 SKU 경쟁사 가격 비교
  GET /api/competitor/opportunities       — 가격 조정 기회
  GET /api/competitor/alerts              — 최근 가격 변동 알림

환경변수:
  DASHBOARD_API_KEY — API 인증 키
"""

import logging

from flask import Blueprint, jsonify, request

from .auth_middleware import require_api_key

logger = logging.getLogger(__name__)

competitor_bp = Blueprint("competitor", __name__, url_prefix="/api/competitor")


def _get_tracker():
    from ..competitor.price_tracker import CompetitorPriceTracker
    return CompetitorPriceTracker()


def _get_analyzer():
    from ..competitor.market_analyzer import MarketAnalyzer
    return MarketAnalyzer()


def _get_alert():
    from ..competitor.price_alert import PriceAlert
    return PriceAlert()


@competitor_bp.get("/prices")
@require_api_key
def list_prices():
    """경쟁사 가격 비교 목록을 반환한다."""
    tracker = _get_tracker()
    try:
        rows = tracker._get_all_rows()
        # SKU별로 그룹화
        from collections import defaultdict
        by_sku = defaultdict(list)
        for row in rows:
            sku = str(row.get('our_sku', ''))
            by_sku[sku].append(row)

        comparisons = []
        for sku, entries in by_sku.items():
            if sku:
                comparison = tracker.get_price_comparison(sku)
                comparisons.append(comparison)
    except Exception as exc:
        logger.warning("경쟁사 가격 목록 조회 실패: %s", exc)
        comparisons = []

    return jsonify({"comparisons": comparisons, "count": len(comparisons)})


@competitor_bp.get("/prices/<sku>")
@require_api_key
def get_price(sku: str):
    """특정 SKU의 경쟁사 가격 비교를 반환한다."""
    tracker = _get_tracker()
    try:
        comparison = tracker.get_price_comparison(sku)
    except Exception as exc:
        logger.warning("SKU 가격 비교 조회 실패 (%s): %s", sku, exc)
        return jsonify({"error": str(exc)}), 500

    return jsonify(comparison)


@competitor_bp.get("/opportunities")
@require_api_key
def get_opportunities():
    """가격 조정 기회 목록을 반환한다."""
    threshold_pct = float(request.args.get("threshold_pct", 10))
    analyzer = _get_analyzer()
    try:
        opportunities = analyzer.get_pricing_opportunities()
        # 임계값 필터링
        opportunities = [o for o in opportunities if abs(o['price_diff_pct']) >= threshold_pct]
    except Exception as exc:
        logger.warning("가격 조정 기회 조회 실패: %s", exc)
        opportunities = []

    return jsonify({"opportunities": opportunities, "count": len(opportunities)})


@competitor_bp.get("/alerts")
@require_api_key
def get_alerts():
    """최근 가격 변동 알림 목록을 반환한다."""
    alert = _get_alert()
    try:
        changes = alert.check_price_changes()
    except Exception as exc:
        logger.warning("가격 변동 알림 조회 실패: %s", exc)
        changes = []

    return jsonify({"alerts": changes, "count": len(changes)})
