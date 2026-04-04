"""src/ai_recommendation/trending_analyzer.py — Phase 94: AI 트렌딩 분석기."""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timedelta

from .recommendation_model import RecommendationResult

# 시즌 감지 (월 → 시즌)
_MONTH_SEASON: dict[int, str] = {
    1: "winter", 2: "winter",
    3: "spring", 4: "spring", 5: "spring",
    6: "summer", 7: "summer", 8: "summer",
    9: "fall", 10: "fall", 11: "fall",
    12: "winter",
}

# 이벤트 타입별 트렌딩 가중치
_TREND_WEIGHT: dict[str, float] = {
    "purchase": 5.0,
    "cart": 3.0,
    "wishlist": 2.0,
    "view": 1.0,
    "search": 0.5,
}


class AITrendingAnalyzer:
    """AI 트렌딩 분석기.

    - 시간 가중 트렌딩 점수 (최근 이벤트에 높은 가중치)
    - 카테고리별 트렌딩 상품
    - 급상승 상품 감지 (이전 기간 대비 성장률)
    - 시즌/이벤트 기반 추천
    """

    def __init__(self, decay_hours: float = 24.0) -> None:
        # product_id -> [(timestamp, event_type, category)]
        self._events: dict[str, list[tuple[datetime, str, str]]] = defaultdict(list)
        self._decay_hours = decay_hours

    def record(
        self,
        product_id: str,
        event_type: str = "view",
        category: str = "",
        timestamp: datetime | None = None,
    ) -> None:
        """이벤트를 기록한다."""
        ts = timestamp or datetime.utcnow()
        self._events[product_id].append((ts, event_type, category))

    def _time_weight(self, ts: datetime, now: datetime) -> float:
        """시간 기반 감쇠 가중치를 계산한다 (지수 감쇠)."""
        age_hours = (now - ts).total_seconds() / 3600.0
        return math.exp(-age_hours / self._decay_hours)

    def trending_score(self, product_id: str, now: datetime | None = None) -> float:
        """상품의 트렌딩 점수를 계산한다."""
        now = now or datetime.utcnow()
        total = 0.0
        for ts, event_type, _ in self._events.get(product_id, []):
            weight = _TREND_WEIGHT.get(event_type, 1.0)
            total += weight * self._time_weight(ts, now)
        return total

    def get_trending(
        self,
        top_n: int = 10,
        category: str | None = None,
        now: datetime | None = None,
    ) -> list[RecommendationResult]:
        """트렌딩 상품 목록을 반환한다."""
        now = now or datetime.utcnow()
        scores: dict[str, float] = {}

        for pid, events in self._events.items():
            if category:
                # 해당 카테고리 이벤트만 필터링
                filtered = [(ts, et, cat) for ts, et, cat in events if cat == category]
            else:
                filtered = events

            if not filtered:
                continue

            total = 0.0
            for ts, event_type, _ in filtered:
                weight = _TREND_WEIGHT.get(event_type, 1.0)
                total += weight * self._time_weight(ts, now)

            if total > 0:
                scores[pid] = total

        sorted_items = sorted(scores.items(), key=lambda x: -x[1])[:top_n]
        return [
            RecommendationResult(
                product_id=pid,
                score=score,
                strategy="trending",
                reason=f"트렌딩 상품({category})" if category else "트렌딩 상품",
            )
            for pid, score in sorted_items
        ]

    def get_surging(
        self,
        top_n: int = 10,
        window_hours: float = 24.0,
        compare_window_hours: float = 48.0,
        now: datetime | None = None,
    ) -> list[RecommendationResult]:
        """급상승 상품을 감지한다 (이전 기간 대비 성장률).

        최근 window_hours 이내의 점수 vs 이전 compare_window_hours의 점수 비교.
        """
        now = now or datetime.utcnow()
        recent_cutoff = now - timedelta(hours=window_hours)
        prev_cutoff = now - timedelta(hours=compare_window_hours)

        growth: dict[str, float] = {}

        for pid, events in self._events.items():
            recent_score = 0.0
            prev_score = 0.0
            for ts, event_type, _ in events:
                w = _TREND_WEIGHT.get(event_type, 1.0)
                if ts >= recent_cutoff:
                    recent_score += w
                elif ts >= prev_cutoff:
                    prev_score += w
            if prev_score > 0:
                growth[pid] = recent_score / prev_score
            elif recent_score > 0:
                growth[pid] = recent_score * 10.0  # 전혀 없다가 급등

        sorted_items = sorted(growth.items(), key=lambda x: -x[1])[:top_n]
        return [
            RecommendationResult(
                product_id=pid,
                score=score,
                strategy="surging",
                reason=f"급상승 상품 (성장률 {score:.1f}x)",
            )
            for pid, score in sorted_items
            if score > 1.0
        ]

    def get_seasonal(
        self,
        top_n: int = 10,
        now: datetime | None = None,
    ) -> list[RecommendationResult]:
        """현재 시즌에 맞는 트렌딩 상품을 반환한다."""
        now = now or datetime.utcnow()
        current_season = _MONTH_SEASON.get(now.month, "general")

        # 시즌 카테고리 매핑 (간단한 규칙 기반)
        _season_categories: dict[str, list[str]] = {
            "winter": ["winter_clothing", "heating", "ski", "holiday"],
            "spring": ["outdoor", "gardening", "spring_clothing", "travel"],
            "summer": ["summer_clothing", "cooling", "beach", "sports"],
            "fall": ["fall_clothing", "outdoor", "back_to_school"],
        }
        season_cats = set(_season_categories.get(current_season, []))

        # 시즌 관련 카테고리가 없으면 일반 트렌딩
        if not season_cats:
            return self.get_trending(top_n=top_n, now=now)

        scores: dict[str, float] = {}
        for pid, events in self._events.items():
            total = 0.0
            matched = False
            for ts, event_type, cat in events:
                w = _TREND_WEIGHT.get(event_type, 1.0)
                total += w * self._time_weight(ts, now)
                if cat in season_cats:
                    matched = True
            if total > 0 and matched:
                scores[pid] = total * 1.5  # 시즌 부스트

        sorted_items = sorted(scores.items(), key=lambda x: -x[1])[:top_n]

        # 시즌 매칭 상품이 부족하면 일반 트렌딩으로 보완
        results = [
            RecommendationResult(
                product_id=pid,
                score=score,
                strategy="seasonal",
                reason=f"시즌 추천 ({current_season})",
            )
            for pid, score in sorted_items
        ]
        if len(results) < top_n:
            fallback = self.get_trending(top_n=top_n - len(results), now=now)
            seen = {r.product_id for r in results}
            results.extend(r for r in fallback if r.product_id not in seen)

        return results[:top_n]

    def get_trending_by_category(self, top_n: int = 5, now: datetime | None = None) -> dict[str, list[RecommendationResult]]:
        """카테고리별 트렌딩 상품을 반환한다."""
        now = now or datetime.utcnow()
        categories: set[str] = set()
        for events in self._events.values():
            for _, _, cat in events:
                if cat:
                    categories.add(cat)

        return {
            cat: self.get_trending(top_n=top_n, category=cat, now=now)
            for cat in categories
        }
