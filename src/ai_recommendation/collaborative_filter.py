"""src/ai_recommendation/collaborative_filter.py — Phase 94: 고도화 협업 필터링."""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime

from .recommendation_model import EventType, RecommendationResult, UserEvent

# 이벤트 타입별 가중치
_EVENT_WEIGHT: dict[str, float] = {
    EventType.PURCHASE.value: 5.0,
    EventType.CART.value: 3.0,
    EventType.WISHLIST.value: 2.0,
    EventType.VIEW.value: 1.0,
    EventType.SEARCH.value: 0.5,
}


class AdvancedCollaborativeFilter:
    """고도화 협업 필터링 추천기.

    - 사용자-상품 행렬 (구매/조회/장바구니/위시리스트 이벤트)
    - 코사인 유사도 기반 사용자 유사도 계산
    - 아이템 기반 협업 필터링 (item-item similarity)
    - 신규 사용자 콜드 스타트 처리 (인기 상품 폴백)
    """

    def __init__(self) -> None:
        # user_id -> {product_id: weighted_score}
        self._user_matrix: dict[str, dict[str, float]] = defaultdict(dict)
        # product_id -> interaction_count (인기도 추적)
        self._product_popularity: dict[str, float] = defaultdict(float)
        # 이벤트 로그
        self._events: list[UserEvent] = []

    def add_event(self, event: UserEvent) -> None:
        """사용자 이벤트를 추가한다."""
        self._events.append(event)
        weight = _EVENT_WEIGHT.get(event.event_type.value, 1.0)
        current = self._user_matrix[event.user_id].get(event.product_id, 0.0)
        self._user_matrix[event.user_id][event.product_id] = current + weight
        self._product_popularity[event.product_id] += weight

    def add_interaction(self, user_id: str, product_id: str, score: float) -> None:
        """직접 상호작용 점수를 추가한다."""
        current = self._user_matrix[user_id].get(product_id, 0.0)
        self._user_matrix[user_id][product_id] = current + score
        self._product_popularity[product_id] += score

    def user_similarity(self, user_id1: str, user_id2: str) -> float:
        """두 사용자의 코사인 유사도를 계산한다."""
        v1 = self._user_matrix.get(user_id1, {})
        v2 = self._user_matrix.get(user_id2, {})
        if not v1 or not v2:
            return 0.0
        common = set(v1) & set(v2)
        if not common:
            return 0.0
        dot = sum(v1[p] * v2[p] for p in common)
        norm1 = math.sqrt(sum(s * s for s in v1.values()))
        norm2 = math.sqrt(sum(s * s for s in v2.values()))
        if norm1 == 0.0 or norm2 == 0.0:
            return 0.0
        return dot / (norm1 * norm2)

    def item_similarity(self, product_id1: str, product_id2: str) -> float:
        """두 상품의 코사인 유사도를 계산한다 (아이템 기반)."""
        # 각 상품에 평점을 매긴 사용자 벡터 구성
        v1: dict[str, float] = {}
        v2: dict[str, float] = {}
        for uid, items in self._user_matrix.items():
            if product_id1 in items:
                v1[uid] = items[product_id1]
            if product_id2 in items:
                v2[uid] = items[product_id2]
        if not v1 or not v2:
            return 0.0
        common = set(v1) & set(v2)
        if not common:
            return 0.0
        dot = sum(v1[u] * v2[u] for u in common)
        norm1 = math.sqrt(sum(s * s for s in v1.values()))
        norm2 = math.sqrt(sum(s * s for s in v2.values()))
        if norm1 == 0.0 or norm2 == 0.0:
            return 0.0
        return dot / (norm1 * norm2)

    def recommend(self, user_id: str, top_n: int = 10) -> list[RecommendationResult]:
        """사용자 기반 협업 필터링으로 추천 상품을 반환한다.

        신규 사용자(콜드 스타트)는 인기 상품으로 폴백한다.
        """
        user_items = self._user_matrix.get(user_id, {})
        if not user_items:
            return self._cold_start(top_n)

        seen = set(user_items)
        scores: dict[str, float] = {}

        for other_id, other_items in self._user_matrix.items():
            if other_id == user_id:
                continue
            sim = self.user_similarity(user_id, other_id)
            if sim <= 0:
                continue
            for pid, rating in other_items.items():
                if pid not in seen:
                    scores[pid] = scores.get(pid, 0.0) + sim * rating

        sorted_items = sorted(scores.items(), key=lambda x: -x[1])[:top_n]
        return [
            RecommendationResult(
                product_id=pid,
                score=score,
                strategy="collaborative_user",
                reason="유사 사용자가 관심 가진 상품",
            )
            for pid, score in sorted_items
        ]

    def recommend_item_based(self, product_id: str, top_n: int = 10) -> list[RecommendationResult]:
        """아이템 기반 협업 필터링으로 유사 상품을 반환한다."""
        all_products = set()
        for items in self._user_matrix.values():
            all_products.update(items.keys())
        all_products.discard(product_id)

        scores: dict[str, float] = {}
        for pid in all_products:
            sim = self.item_similarity(product_id, pid)
            if sim > 0:
                scores[pid] = sim

        sorted_items = sorted(scores.items(), key=lambda x: -x[1])[:top_n]
        return [
            RecommendationResult(
                product_id=pid,
                score=score,
                strategy="collaborative_item",
                reason="함께 구매/조회된 유사 상품",
            )
            for pid, score in sorted_items
        ]

    def _cold_start(self, top_n: int) -> list[RecommendationResult]:
        """콜드 스타트: 인기 상품 폴백."""
        sorted_popular = sorted(
            self._product_popularity.items(),
            key=lambda x: -x[1],
        )[:top_n]
        return [
            RecommendationResult(
                product_id=pid,
                score=score,
                strategy="cold_start_popular",
                reason="인기 상품 (신규 사용자)",
            )
            for pid, score in sorted_popular
        ]

    def get_popular_products(self, top_n: int = 10) -> list[RecommendationResult]:
        """인기 상품 목록을 반환한다."""
        return self._cold_start(top_n)
