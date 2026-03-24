"""src/api/reviews_api.py — 리뷰 관리 API.

Flask Blueprint 기반 리뷰 관리 API.

엔드포인트:
  GET  /api/reviews              — 리뷰 목록 (필터: rating, status, product_sku)
  GET  /api/reviews/summary      — 리뷰 요약 통계
  PATCH /api/reviews/<id>/status — 리뷰 상태 변경 (approve/reject)

환경변수:
  DASHBOARD_API_KEY           — API 인증 키
  REVIEW_COLLECTION_ENABLED   — 수집 활성화 여부
"""

import logging

from flask import Blueprint, jsonify, request

from .auth_middleware import require_api_key

logger = logging.getLogger(__name__)

reviews_bp = Blueprint("reviews", __name__, url_prefix="/api/reviews")


def _get_collector():
    """ReviewCollector 인스턴스를 반환한다."""
    from ..reviews.collector import ReviewCollector
    return ReviewCollector()


def _get_analyzer():
    """ReviewAnalyzer 인스턴스를 반환한다."""
    from ..reviews.analyzer import ReviewAnalyzer
    return ReviewAnalyzer()


@reviews_bp.get("")
@require_api_key
def list_reviews():
    """리뷰 목록을 반환한다.

    쿼리 파라미터:
      rating     — 평점 필터 (1-5)
      status     — 상태 필터 (pending/approved/rejected)
      product_sku — 제품 SKU 필터
    """
    collector = _get_collector()

    rating_raw = request.args.get("rating")
    status = request.args.get("status")
    product_sku = request.args.get("product_sku")

    rating = None
    if rating_raw is not None:
        try:
            rating = int(rating_raw)
        except (ValueError, TypeError):
            return jsonify({"error": "rating must be an integer between 1 and 5"}), 400

    try:
        reviews = collector.get_reviews(
            rating=rating,
            status=status,
            product_sku=product_sku,
        )
    except Exception as exc:
        logger.warning("리뷰 목록 조회 실패: %s", exc)
        reviews = []

    return jsonify({
        "reviews": reviews,
        "count": len(reviews),
        "filters": {
            "rating": rating,
            "status": status,
            "product_sku": product_sku,
        },
    })


@reviews_bp.get("/summary")
@require_api_key
def review_summary():
    """리뷰 요약 통계를 반환한다.

    쿼리 파라미터:
      days — 분석 기간 (기본 30)
    """
    try:
        days = int(request.args.get("days", 30))
    except (ValueError, TypeError):
        days = 30

    collector = _get_collector()
    analyzer = _get_analyzer()

    try:
        reviews = collector.get_reviews()
        summary = analyzer.generate_review_summary(reviews=reviews, days=days)
    except Exception as exc:
        logger.warning("리뷰 요약 생성 실패: %s", exc)
        summary = {
            "period_days": days,
            "total_reviews": 0,
            "average_rating": 0.0,
            "by_rating": {i: 0 for i in range(1, 6)},
            "negative_count": 0,
            "top_keywords": [],
            "avg_by_sku": {},
        }

    return jsonify(summary)


@reviews_bp.patch("/<review_id>/status")
@require_api_key
def update_review_status(review_id: str):
    """리뷰 상태를 변경한다.

    요청 바디:
      {"status": "approved" | "rejected" | "pending"}
    """
    data = request.get_json(silent=True) or {}
    new_status = data.get("status", "")

    valid_statuses = ("approved", "rejected", "pending")
    if new_status not in valid_statuses:
        return jsonify({
            "error": f"Invalid status. Must be one of: {valid_statuses}",
        }), 400

    collector = _get_collector()
    try:
        success = collector.update_status(review_id, new_status)
    except Exception as exc:
        logger.error("리뷰 상태 업데이트 실패: %s", exc)
        return jsonify({"error": str(exc)}), 500

    if success:
        return jsonify({"review_id": review_id, "status": new_status, "ok": True})
    return jsonify({"error": "Review not found", "review_id": review_id}), 404
