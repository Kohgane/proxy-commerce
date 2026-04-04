"""src/ai_recommendation/personalization.py — Phase 94: 개인화 엔진."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

from .recommendation_model import EventType, RecommendationResult, UserEvent, UserProfile

# 이벤트별 선호도 가중치
_PREF_WEIGHT: dict[str, float] = {
    EventType.PURCHASE.value: 5.0,
    EventType.CART.value: 3.0,
    EventType.WISHLIST.value: 2.5,
    EventType.VIEW.value: 1.0,
    EventType.SEARCH.value: 0.5,
}

# 세그먼트별 전략 가중치 {collaborative, content, trending, cross_sell}
_SEGMENT_STRATEGY: dict[str, dict[str, float]] = {
    "vip": {"collaborative": 0.4, "content": 0.3, "trending": 0.1, "cross_sell": 0.2},
    "new": {"collaborative": 0.1, "content": 0.3, "trending": 0.5, "cross_sell": 0.1},
    "churn_risk": {"collaborative": 0.2, "content": 0.2, "trending": 0.3, "cross_sell": 0.3},
    "general": {"collaborative": 0.3, "content": 0.3, "trending": 0.2, "cross_sell": 0.2},
}


class PersonalizationEngine:
    """개인화 추천 엔진.

    - 사용자 프로필 분석 (구매/검색/조회/위시리스트 이력)
    - 취향 벡터 생성 (카테고리/브랜드/가격대 선호도)
    - 실시간 세션 기반 추천
    - 사용자 세그먼트별 추천 전략
    """

    def __init__(self) -> None:
        # user_id -> UserProfile
        self._profiles: dict[str, UserProfile] = {}
        # user_id -> [UserEvent] (현재 세션 이벤트)
        self._sessions: dict[str, list[UserEvent]] = defaultdict(list)
        # product_id -> {category, brand, price_tier}
        self._product_meta: dict[str, dict] = {}

    def register_product(self, product_id: str, category: str, brand: str = "", price_tier: str = "mid") -> None:
        """상품 메타데이터를 등록한다."""
        self._product_meta[product_id] = {
            "category": category,
            "brand": brand,
            "price_tier": price_tier,
        }

    def record_event(self, event: UserEvent) -> None:
        """사용자 이벤트를 기록하고 프로필을 갱신한다."""
        self._sessions[event.user_id].append(event)
        self._update_profile(event)

    def _update_profile(self, event: UserEvent) -> None:
        """이벤트를 기반으로 사용자 프로필을 업데이트한다."""
        uid = event.user_id
        profile = self._profiles.setdefault(uid, UserProfile(user_id=uid))
        weight = _PREF_WEIGHT.get(event.event_type.value, 1.0)
        pid = event.product_id
        meta = self._product_meta.get(pid, {})

        # 카테고리 선호도 업데이트
        cat = meta.get("category")
        if cat:
            profile.category_preferences[cat] = (
                profile.category_preferences.get(cat, 0.0) + weight
            )

        # 브랜드 선호도 업데이트
        brand = meta.get("brand")
        if brand:
            profile.brand_preferences[brand] = (
                profile.brand_preferences.get(brand, 0.0) + weight
            )

        # 가격대 선호도 업데이트
        pt = meta.get("price_tier")
        if pt:
            profile.price_range[pt] = profile.price_range.get(pt, 0.0) + weight

        # 이력 업데이트
        if event.event_type == EventType.PURCHASE:
            if pid not in profile.purchase_history:
                profile.purchase_history.append(pid)
        elif event.event_type == EventType.WISHLIST:
            if pid not in profile.wishlist:
                profile.wishlist.append(pid)
        elif event.event_type == EventType.SEARCH:
            if pid not in profile.search_history:
                profile.search_history.append(pid)
            if len(profile.search_history) > 100:
                profile.search_history = profile.search_history[-100:]
        elif event.event_type == EventType.VIEW:
            if pid not in profile.view_history:
                profile.view_history.append(pid)
            if len(profile.view_history) > 200:
                profile.view_history = profile.view_history[-200:]

    def get_profile(self, user_id: str) -> UserProfile:
        """사용자 프로필을 반환한다."""
        return self._profiles.get(user_id, UserProfile(user_id=user_id))

    def set_segment(self, user_id: str, segment: str) -> None:
        """사용자 세그먼트를 설정한다."""
        profile = self._profiles.setdefault(user_id, UserProfile(user_id=user_id))
        profile.segment = segment

    def get_taste_vector(self, user_id: str) -> dict[str, dict[str, float]]:
        """사용자 취향 벡터를 반환한다."""
        profile = self.get_profile(user_id)

        def _normalize(d: dict[str, float]) -> dict[str, float]:
            total = sum(d.values()) or 1.0
            return {k: v / total for k, v in sorted(d.items(), key=lambda x: -x[1])}

        return {
            "categories": _normalize(profile.category_preferences),
            "brands": _normalize(profile.brand_preferences),
            "price_ranges": _normalize(profile.price_range),
        }

    def get_session_context(self, user_id: str, window_minutes: int = 30) -> list[str]:
        """현재 세션의 최근 상품 ID를 반환한다."""
        cutoff = datetime.utcnow() - timedelta(minutes=window_minutes)
        return [
            e.product_id
            for e in self._sessions.get(user_id, [])
            if e.timestamp >= cutoff
        ]

    def get_strategy_weights(self, user_id: str) -> dict[str, float]:
        """사용자 세그먼트별 추천 전략 가중치를 반환한다."""
        profile = self.get_profile(user_id)
        seg = profile.segment if profile.segment in _SEGMENT_STRATEGY else "general"
        return _SEGMENT_STRATEGY[seg]

    def score_products(
        self,
        user_id: str,
        product_ids: list[str],
        top_n: int = 10,
    ) -> list[RecommendationResult]:
        """사용자 취향 벡터 기반으로 상품 점수를 계산한다."""
        profile = self.get_profile(user_id)
        seen = set(profile.purchase_history) | set(profile.view_history)
        results: list[RecommendationResult] = []

        for pid in product_ids:
            if pid in seen:
                continue
            meta = self._product_meta.get(pid, {})
            score = 0.0

            cat = meta.get("category")
            if cat:
                score += profile.category_preferences.get(cat, 0.0) * 3.0

            brand = meta.get("brand")
            if brand:
                score += profile.brand_preferences.get(brand, 0.0) * 2.0

            pt = meta.get("price_tier")
            if pt:
                score += profile.price_range.get(pt, 0.0) * 1.5

            if score > 0:
                results.append(
                    RecommendationResult(
                        product_id=pid,
                        score=score,
                        strategy="personalized",
                        reason="취향 벡터 기반 개인화 추천",
                    )
                )

        results.sort(key=lambda r: -r.score)
        return results[:top_n]
