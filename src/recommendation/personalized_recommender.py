"""src/recommendation/personalized_recommender.py — 개인화 추천기."""
from __future__ import annotations


class PersonalizedRecommender:
    """개인화 추천기."""

    def recommend(
        self,
        user_id: str,
        purchase_history: list | None = None,
        wishlist: list | None = None,
        search_history: list | None = None,
        top_n: int = 10,
    ) -> list:
        """개인화 추천 상품 목록을 반환한다."""
        seen = set()
        candidates = []
        for source in [purchase_history or [], wishlist or []]:
            for item in source:
                if item not in seen:
                    seen.add(item)
                    candidates.append({'product_id': f'rec-{item}', 'source': 'history'})
        if not candidates:
            candidates = [{'product_id': f'default-{i}', 'source': 'default'} for i in range(5)]
        return candidates[:top_n]
