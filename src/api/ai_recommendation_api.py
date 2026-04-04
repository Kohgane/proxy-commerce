"""src/api/ai_recommendation_api.py — Phase 94: AI 추천 REST API Blueprint."""
from __future__ import annotations

import logging
import uuid

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

ai_recommendation_bp = Blueprint(
    "ai_recommendation",
    __name__,
    url_prefix="/api/v1/ai-recommend",
)

# 싱글턴 엔진 인스턴스
_engine = None
_auto = None


def _get_engine():
    global _engine
    if _engine is None:
        from ..ai_recommendation import AIRecommendationEngine
        _engine = AIRecommendationEngine()
    return _engine


def _get_auto():
    global _auto
    if _auto is None:
        from ..ai_recommendation import AutoRecommender
        _auto = AutoRecommender(engine=_get_engine())
    return _auto


@ai_recommendation_bp.get("/status")
def ai_recommend_status():
    return jsonify({"status": "ok", "module": "ai_recommendation"})


@ai_recommendation_bp.get("/<user_id>")
def personalized_recommend(user_id: str):
    """GET /api/v1/ai-recommend/<user_id> — 개인화 추천.

    Query params:
        strategy: ensemble | collaborative | content | trending | personalized (default: ensemble)
        top_n: int (default: 10)
    """
    strategy = request.args.get("strategy", "ensemble")
    top_n = int(request.args.get("top_n", 10))
    try:
        engine = _get_engine()
        results = engine.recommend(user_id, top_n=top_n, strategy=strategy)
        return jsonify({
            "user_id": user_id,
            "strategy": strategy,
            "recommendations": [r.to_dict() for r in results],
            "count": len(results),
        })
    except Exception as exc:
        logger.error("AI 추천 오류: %s", exc)
        return jsonify({"error": "Internal server error"}), 500


@ai_recommendation_bp.get("/<user_id>/cross-sell")
def cross_sell_recommend(user_id: str):
    """GET /api/v1/ai-recommend/<user_id>/cross-sell — 크로스셀 추천.

    Query params:
        product_ids: comma-separated product IDs
        top_n: int (default: 5)
    """
    raw = request.args.get("product_ids", "")
    product_ids = [p.strip() for p in raw.split(",") if p.strip()]
    top_n = int(request.args.get("top_n", 5))
    if not product_ids:
        return jsonify({"error": "product_ids parameter required"}), 400
    try:
        engine = _get_engine()
        results = engine.get_cross_sell(product_ids, top_n=top_n)
        return jsonify({
            "user_id": user_id,
            "product_ids": product_ids,
            "recommendations": [r.to_dict() for r in results],
            "count": len(results),
        })
    except Exception as exc:
        logger.error("크로스셀 추천 오류: %s", exc)
        return jsonify({"error": "Internal server error"}), 500


@ai_recommendation_bp.get("/trending")
def trending():
    """GET /api/v1/ai-recommend/trending — 트렌딩 상품."""
    top_n = int(request.args.get("top_n", 10))
    try:
        engine = _get_engine()
        results = engine.get_trending(top_n=top_n)
        return jsonify({
            "recommendations": [r.to_dict() for r in results],
            "count": len(results),
        })
    except Exception as exc:
        logger.error("트렌딩 조회 오류: %s", exc)
        return jsonify({"error": "Internal server error"}), 500


@ai_recommendation_bp.get("/trending/<category>")
def trending_by_category(category: str):
    """GET /api/v1/ai-recommend/trending/<category> — 카테고리별 트렌딩."""
    top_n = int(request.args.get("top_n", 10))
    try:
        engine = _get_engine()
        results = engine.get_trending(top_n=top_n, category=category)
        return jsonify({
            "category": category,
            "recommendations": [r.to_dict() for r in results],
            "count": len(results),
        })
    except Exception as exc:
        logger.error("카테고리 트렌딩 조회 오류: %s", exc)
        return jsonify({"error": "Internal server error"}), 500


@ai_recommendation_bp.post("/event")
def record_event():
    """POST /api/v1/ai-recommend/event — 사용자 이벤트 기록.

    Body:
        user_id: str
        event_type: view | purchase | cart | wishlist | search
        product_id: str
        metadata: dict (optional)
    """
    body = request.get_json(silent=True) or {}
    user_id = body.get("user_id", "").strip()
    event_type = body.get("event_type", "").strip()
    product_id = body.get("product_id", "").strip()
    if not user_id or not event_type or not product_id:
        return jsonify({"error": "user_id, event_type, product_id are required"}), 400
    try:
        from ..ai_recommendation.recommendation_model import EventType, UserEvent
        et = EventType(event_type)
        event = UserEvent(
            user_id=user_id,
            event_type=et,
            product_id=product_id,
            metadata=body.get("metadata", {}),
        )
        engine = _get_engine()
        engine.record_event(event)
        return jsonify({"status": "recorded", "event_type": event_type}), 201
    except ValueError:
        return jsonify({"error": f"Invalid event_type: {event_type}"}), 400
    except Exception as exc:
        logger.error("이벤트 기록 오류: %s", exc)
        return jsonify({"error": "Internal server error"}), 500


@ai_recommendation_bp.get("/metrics")
def get_metrics():
    """GET /api/v1/ai-recommend/metrics — 추천 성능 메트릭."""
    try:
        engine = _get_engine()
        metrics = engine.feedback.get_metrics()
        weights = engine.feedback.get_strategy_weights()
        return jsonify({
            "metrics": metrics,
            "strategy_weights": weights,
        })
    except Exception as exc:
        logger.error("메트릭 조회 오류: %s", exc)
        return jsonify({"error": "Internal server error"}), 500


@ai_recommendation_bp.post("/feedback")
def record_feedback():
    """POST /api/v1/ai-recommend/feedback — 추천 피드백 기록.

    Body:
        rec_id: str
        action: impression | click | purchase
        user_id: str (optional, for impression)
        product_id: str (optional, for impression)
        strategy: str (optional, for impression)
    """
    body = request.get_json(silent=True) or {}
    action = body.get("action", "").strip()
    rec_id = body.get("rec_id", "").strip()
    if not action:
        return jsonify({"error": "action is required"}), 400
    if not rec_id:
        rec_id = str(uuid.uuid4())
    try:
        engine = _get_engine()
        if action == "impression":
            engine.feedback.record_impression(
                rec_id=rec_id,
                user_id=body.get("user_id", ""),
                product_id=body.get("product_id", ""),
                strategy=body.get("strategy", "ensemble"),
            )
        elif action == "click":
            engine.feedback.record_click(rec_id)
        elif action == "purchase":
            engine.feedback.record_purchase(rec_id)
        else:
            return jsonify({"error": f"Invalid action: {action}"}), 400
        return jsonify({"status": "recorded", "rec_id": rec_id, "action": action}), 201
    except Exception as exc:
        logger.error("피드백 기록 오류: %s", exc)
        return jsonify({"error": "Internal server error"}), 500


@ai_recommendation_bp.get("/<user_id>/repurchase")
def repurchase_recommend(user_id: str):
    """GET /api/v1/ai-recommend/<user_id>/repurchase — 재구매 추천.

    Query params:
        top_n: int (default: 5)
    """
    top_n = int(request.args.get("top_n", 5))
    try:
        auto = _get_auto()
        results = auto.get_repurchase_recommendations(user_id, top_n=top_n)
        repurchase_date = auto.estimate_repurchase_date(user_id)
        return jsonify({
            "user_id": user_id,
            "repurchase_date": repurchase_date.isoformat() if repurchase_date else None,
            "recommendations": [r.to_dict() for r in results],
            "count": len(results),
        })
    except Exception as exc:
        logger.error("재구매 추천 오류: %s", exc)
        return jsonify({"error": "Internal server error"}), 500
