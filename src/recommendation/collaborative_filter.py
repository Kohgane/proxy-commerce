"""src/recommendation/collaborative_filter.py — 협업 필터링."""
from __future__ import annotations

import math


class CollaborativeFilter:
    """협업 필터링 추천기."""

    def __init__(self) -> None:
        self._interactions: dict[str, dict] = {}

    def add_interaction(self, user_id: str, product_id: str, rating: float) -> None:
        """상호작용을 추가한다."""
        self._interactions.setdefault(user_id, {})[product_id] = rating

    def user_similarity(self, user_id1: str, user_id2: str) -> float:
        """두 사용자 유사도를 계산한다 (코사인 유사도)."""
        ratings1 = self._interactions.get(user_id1, {})
        ratings2 = self._interactions.get(user_id2, {})
        common = set(ratings1) & set(ratings2)
        if not common:
            return 0.0
        dot = sum(ratings1[p] * ratings2[p] for p in common)
        norm1 = math.sqrt(sum(v ** 2 for v in ratings1.values()))
        norm2 = math.sqrt(sum(v ** 2 for v in ratings2.values()))
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return dot / (norm1 * norm2)

    def recommend(self, user_id: str, top_n: int = 10) -> list:
        """사용자에게 상품을 추천한다."""
        user_ratings = self._interactions.get(user_id, {})
        seen = set(user_ratings)
        scores: dict[str, float] = {}
        for other_id, other_ratings in self._interactions.items():
            if other_id == user_id:
                continue
            sim = self.user_similarity(user_id, other_id)
            if sim <= 0:
                continue
            for product_id, rating in other_ratings.items():
                if product_id not in seen:
                    scores[product_id] = scores.get(product_id, 0) + sim * rating
        sorted_items = sorted(scores.items(), key=lambda x: -x[1])[:top_n]
        return [{'product_id': pid, 'score': score} for pid, score in sorted_items]
