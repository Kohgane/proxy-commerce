"""src/ai_recommendation/recommendation_engine.py — Phase 94: AI 추천 엔진 오케스트레이터."""
from __future__ import annotations

import hashlib
import time
from datetime import datetime

from .collaborative_filter import AdvancedCollaborativeFilter
from .content_based_filter import AdvancedContentBasedFilter
from .cross_sell import CrossSellEngine
from .feedback_loop import FeedbackLoop
from .personalization import PersonalizationEngine
from .recommendation_model import RecommendationResult, UserEvent
from .trending_analyzer import AITrendingAnalyzer

# 기본 캐시 TTL (초)
_DEFAULT_TTL = 300


class _CacheEntry:
    __slots__ = ("data", "expires_at")

    def __init__(self, data: list, ttl: float) -> None:
        self.data = data
        self.expires_at = time.monotonic() + ttl


class AIRecommendationEngine:
    """AI 추천 엔진 — 전략 통합 오케스트레이터.

    - 가중치 기반 앙상블 (협업 필터링 + 콘텐츠 기반 + 개인화 + 트렌딩 + 크로스셀)
    - 추천 결과 TTL 캐싱
    - A/B 테스트 연동
    - FeedbackLoop 기반 자동 가중치 조정
    """

    def __init__(self, cache_ttl: float = _DEFAULT_TTL) -> None:
        self.collaborative = AdvancedCollaborativeFilter()
        self.content_based = AdvancedContentBasedFilter()
        self.personalization = PersonalizationEngine()
        self.trending = AITrendingAnalyzer()
        self.cross_sell = CrossSellEngine()
        self.feedback = FeedbackLoop()
        self._cache: dict[str, _CacheEntry] = {}
        # user_id -> set of cache keys (for targeted invalidation)
        self._user_cache_keys: dict[str, set[str]] = {}
        self._cache_ttl = cache_ttl
        # A/B 테스트 실험 등록 (실험 ID -> 활성 여부)
        self._ab_experiments: dict[str, bool] = {}

    def record_event(self, event: UserEvent) -> None:
        """사용자 이벤트를 모든 하위 엔진에 전파한다."""
        self.collaborative.add_event(event)
        self.personalization.record_event(event)
        self.trending.record(
            product_id=event.product_id,
            event_type=event.event_type.value,
            category=event.metadata.get("category", ""),
            timestamp=event.timestamp,
        )

    def _cache_key(self, user_id: str, strategy: str, **kwargs) -> str:
        raw = f"{user_id}:{strategy}:{sorted(kwargs.items())}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def _get_cache(self, key: str) -> list | None:
        entry = self._cache.get(key)
        if entry and time.monotonic() < entry.expires_at:
            return entry.data
        if entry:
            del self._cache[key]
        return None

    def _set_cache(self, key: str, data: list, user_id: str = "") -> None:
        self._cache[key] = _CacheEntry(data, self._cache_ttl)
        if user_id:
            self._user_cache_keys.setdefault(user_id, set()).add(key)

    def recommend(
        self,
        user_id: str,
        top_n: int = 10,
        strategy: str = "ensemble",
        use_cache: bool = True,
    ) -> list[RecommendationResult]:
        """사용자에게 추천 상품을 반환한다."""
        cache_key = self._cache_key(user_id, strategy, top_n=top_n)
        if use_cache:
            cached = self._get_cache(cache_key)
            if cached is not None:
                return cached

        if strategy == "collaborative":
            results = self.collaborative.recommend(user_id, top_n=top_n)
        elif strategy == "content":
            profile = self.personalization.get_profile(user_id)
            liked = profile.purchase_history or profile.view_history
            results = self.content_based.recommend_for_user(liked, top_n=top_n)
        elif strategy == "trending":
            results = self.trending.get_trending(top_n=top_n)
        elif strategy == "personalized":
            all_products = list(self.content_based._products.keys())
            results = self.personalization.score_products(user_id, all_products, top_n=top_n)
        else:
            results = self._ensemble(user_id, top_n=top_n)

        if use_cache:
            self._set_cache(cache_key, results, user_id=user_id)
        return results

    def _ensemble(self, user_id: str, top_n: int = 10) -> list[RecommendationResult]:
        """가중치 기반 앙상블 추천을 실행한다."""
        weights = self.feedback.get_strategy_weights()
        all_products = list(self.content_based._products.keys())

        # 각 전략의 추천 결과 수집
        cf_results = self.collaborative.recommend(user_id, top_n=top_n * 2)
        cb_results = self.content_based.recommend_for_user(
            self.personalization.get_profile(user_id).purchase_history
            or self.personalization.get_profile(user_id).view_history,
            top_n=top_n * 2,
        )
        trend_results = self.trending.get_trending(top_n=top_n * 2)
        pers_results = self.personalization.score_products(user_id, all_products, top_n=top_n * 2)

        # 앙상블 점수 계산
        scores: dict[str, float] = {}
        _seen = set(self.personalization.get_profile(user_id).purchase_history)

        def _add(recs: list[RecommendationResult], weight_key: str) -> None:
            w = weights.get(weight_key, 0.2)
            if not recs:
                return
            max_score = max(r.score for r in recs) or 1.0
            for r in recs:
                if r.product_id not in _seen:
                    normalized = r.score / max_score
                    scores[r.product_id] = scores.get(r.product_id, 0.0) + normalized * w

        _add(cf_results, "collaborative_user")
        _add(cb_results, "content_based_user")
        _add(trend_results, "trending")
        _add(pers_results, "personalized")

        sorted_items = sorted(scores.items(), key=lambda x: -x[1])[:top_n]
        return [
            RecommendationResult(
                product_id=pid,
                score=score,
                strategy="ensemble",
                reason="앙상블 추천",
            )
            for pid, score in sorted_items
        ]

    def get_cross_sell(
        self,
        product_ids: list[str],
        top_n: int = 5,
    ) -> list[RecommendationResult]:
        """크로스셀 추천을 반환한다."""
        return self.cross_sell.cross_sell(product_ids, top_n=top_n)

    def get_trending(
        self,
        top_n: int = 10,
        category: str | None = None,
    ) -> list[RecommendationResult]:
        """트렌딩 상품을 반환한다."""
        return self.trending.get_trending(top_n=top_n, category=category)

    def register_ab_experiment(self, experiment_id: str, active: bool = True) -> None:
        """A/B 테스트 실험을 등록한다."""
        self._ab_experiments[experiment_id] = active

    def get_ab_strategy(self, user_id: str, experiment_id: str) -> str:
        """A/B 테스트 기반으로 추천 전략을 반환한다."""
        if not self._ab_experiments.get(experiment_id):
            return "ensemble"
        # 사용자 ID 해시로 variant 결정
        h = int(hashlib.sha256(f"{user_id}:{experiment_id}".encode()).hexdigest(), 16)
        strategies = ["ensemble", "collaborative", "content", "trending"]
        return strategies[h % len(strategies)]

    def invalidate_cache(self, user_id: str | None = None) -> None:
        """캐시를 무효화한다."""
        if user_id is None:
            self._cache.clear()
            self._user_cache_keys.clear()
        else:
            keys_to_delete = self._user_cache_keys.pop(user_id, set())
            for k in keys_to_delete:
                self._cache.pop(k, None)
