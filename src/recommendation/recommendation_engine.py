"""src/recommendation/recommendation_engine.py — 통합 추천 엔진."""
from __future__ import annotations

from .collaborative_filter import CollaborativeFilter
from .content_based_filter import ContentBasedFilter
from .popularity_ranker import PopularityRanker
from .personalized_recommender import PersonalizedRecommender


class RecommendationEngine:
    """통합 추천 엔진."""

    def __init__(self) -> None:
        self._cf = CollaborativeFilter()
        self._cbf = ContentBasedFilter()
        self._ranker = PopularityRanker()
        self._personalized = PersonalizedRecommender()

    def recommend(self, user_id: str) -> list:
        """사용자에게 추천 상품 목록을 반환한다."""
        return self._cf.recommend(user_id)

    def similar(self, product_id: str) -> list:
        """유사한 상품 목록을 반환한다."""
        return self._cbf.similar(product_id)

    def trending(self) -> list:
        """인기 상품 목록을 반환한다."""
        return self._ranker.get_trending()

    def personalized(self, user_id: str, history: list | None = None) -> list:
        """개인화 추천 상품 목록을 반환한다."""
        return self._personalized.recommend(user_id, purchase_history=history)
