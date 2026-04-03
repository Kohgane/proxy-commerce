"""src/api/recommendation_api.py — 상품 추천 API (Phase 83)."""
from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

recommendation_bp = Blueprint("recommendation", __name__, url_prefix="/api/v1/recommendations")


@recommendation_bp.get("/recommend")
def recommend():
    """추천 상품 목록을 반환한다."""
    from ..recommendation import RecommendationEngine
    user_id = request.args.get('user_id', 'anonymous')
    engine = RecommendationEngine()
    return jsonify(engine.recommend(user_id))


@recommendation_bp.get("/similar")
def similar():
    """유사한 상품 목록을 반환한다."""
    from ..recommendation import RecommendationEngine
    product_id = request.args.get('product_id', '')
    engine = RecommendationEngine()
    return jsonify(engine.similar(product_id))


@recommendation_bp.get("/trending")
def trending():
    """인기 상품 목록을 반환한다."""
    from ..recommendation import RecommendationEngine
    engine = RecommendationEngine()
    return jsonify(engine.trending())


@recommendation_bp.get("/personalized")
def personalized():
    """개인화 추천 상품 목록을 반환한다."""
    from ..recommendation import RecommendationEngine
    user_id = request.args.get('user_id', 'anonymous')
    engine = RecommendationEngine()
    return jsonify(engine.personalized(user_id))
