"""src/api/review_analytics_api.py — 리뷰 분석 API (Phase 79)."""
from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

review_analytics_bp = Blueprint("review_analytics", __name__, url_prefix="/api/v1/review-analytics")


def _get_analyzer():
    from ..review_analytics import ReviewAnalyzer
    return ReviewAnalyzer()


def _get_sentiment():
    from ..review_analytics import SentimentAnalyzer
    return SentimentAnalyzer()


def _get_summary():
    from ..review_analytics import ReviewSummary
    return ReviewSummary()


def _get_flag_mgr():
    from ..review_analytics import ReviewFlagManager
    return ReviewFlagManager()


def _get_response():
    from ..review_analytics import ReviewResponse
    return ReviewResponse()


@review_analytics_bp.get("/analyze")
@review_analytics_bp.post("/analyze")
def analyze():
    """리뷰를 분석한다."""
    data = request.get_json(silent=True) or request.args
    product_id = data.get('product_id', 'p001')
    analyzer = _get_analyzer()
    return jsonify(analyzer.analyze(product_id))


@review_analytics_bp.get("/sentiment")
@review_analytics_bp.post("/sentiment")
def sentiment():
    """감성을 분석한다."""
    data = request.get_json(silent=True) or request.args
    text = data.get('text', '')
    sa = _get_sentiment()
    return jsonify(sa.analyze_text(text))


@review_analytics_bp.get("/summary")
@review_analytics_bp.post("/summary")
def summary():
    """리뷰 요약을 반환한다."""
    data = request.get_json(silent=True) or {}
    reviews = data.get('reviews', [])
    sm = _get_summary()
    return jsonify({
        'keyword_frequency': sm.keyword_frequency(reviews),
        'pros_cons': sm.extract_pros_cons(reviews),
    })


@review_analytics_bp.post("/flag")
def flag():
    """리뷰를 신고한다."""
    data = request.get_json(silent=True) or {}
    mgr = _get_flag_mgr()
    result = mgr.flag(
        data.get('review_id', ''),
        data.get('flag_type', 'spam'),
        data.get('flagged_by', ''),
    )
    return jsonify(result)


@review_analytics_bp.post("/respond")
def respond():
    """응답 제안을 반환한다."""
    data = request.get_json(silent=True) or {}
    resp = _get_response()
    suggestion = resp.suggest(
        rating=int(data.get('rating', 3)),
        sentiment=data.get('sentiment', 'neutral'),
    )
    return jsonify({'suggestion': suggestion})
