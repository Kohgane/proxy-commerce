"""src/ai_recommendation/auto_recommender.py — Phase 94: 자동 추천 실행기."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

from .recommendation_engine import AIRecommendationEngine
from .recommendation_model import EventType, RecommendationResult


class AutoRecommender:
    """자동 추천 실행기.

    - 일일 추천 메일 생성 (사용자별 맞춤 상품 5개)
    - 재구매 시점 예측 (구매 주기 분석)
    - 이탈 방지 추천 (장기 미구매 고객 타겟)
    - 신상품 알림 (관심 카테고리 신상품 자동 추천)
    """

    def __init__(self, engine: AIRecommendationEngine | None = None) -> None:
        self._engine = engine or AIRecommendationEngine()
        # user_id -> [purchase_timestamp]
        self._purchase_history: dict[str, list[datetime]] = defaultdict(list)
        # user_id -> last_activity_timestamp
        self._last_activity: dict[str, datetime] = {}
        # product_id -> registered_at
        self._new_products: dict[str, datetime] = {}

    def record_purchase(self, user_id: str, product_id: str, timestamp: datetime | None = None) -> None:
        """구매를 기록한다."""
        ts = timestamp or datetime.utcnow()
        self._purchase_history[user_id].append(ts)
        self._last_activity[user_id] = ts

    def record_activity(self, user_id: str, timestamp: datetime | None = None) -> None:
        """사용자 활동을 기록한다."""
        self._last_activity[user_id] = timestamp or datetime.utcnow()

    def register_new_product(self, product_id: str, timestamp: datetime | None = None) -> None:
        """신상품을 등록한다."""
        self._new_products[product_id] = timestamp or datetime.utcnow()

    def estimate_repurchase_date(self, user_id: str) -> datetime | None:
        """구매 주기를 분석하여 다음 재구매 예상 날짜를 반환한다."""
        purchases = sorted(self._purchase_history.get(user_id, []))
        if len(purchases) < 2:
            return None

        # 구매 간격 평균 계산
        intervals = [
            (purchases[i + 1] - purchases[i]).total_seconds()
            for i in range(len(purchases) - 1)
        ]
        avg_interval_seconds = sum(intervals) / len(intervals)
        last_purchase = purchases[-1]
        return last_purchase + timedelta(seconds=avg_interval_seconds)

    def get_repurchase_recommendations(
        self,
        user_id: str,
        top_n: int = 5,
        now: datetime | None = None,
    ) -> list[RecommendationResult]:
        """재구매 시점이 된 사용자에게 추천을 반환한다."""
        now = now or datetime.utcnow()
        repurchase_date = self.estimate_repurchase_date(user_id)
        if repurchase_date and repurchase_date > now:
            # 아직 재구매 시점이 아님
            return []
        # 재구매 시점이 됐거나 기록이 없으면 추천 제공
        return self._engine.recommend(user_id, top_n=top_n, strategy="collaborative")

    def get_churn_risk_users(
        self,
        inactivity_days: int = 30,
        now: datetime | None = None,
    ) -> list[str]:
        """장기 미활동(이탈 위험) 사용자 목록을 반환한다."""
        now = now or datetime.utcnow()
        cutoff = now - timedelta(days=inactivity_days)
        return [
            uid
            for uid, last_ts in self._last_activity.items()
            if last_ts < cutoff
        ]

    def get_churn_prevention_recommendations(
        self,
        user_id: str,
        top_n: int = 5,
    ) -> list[RecommendationResult]:
        """이탈 방지를 위한 추천을 반환한다."""
        # 트렌딩 + 크로스셀 조합으로 관심 유도
        trending = self._engine.get_trending(top_n=top_n)
        seen = {r.product_id for r in trending}
        result = list(trending)

        # 부족하면 앙상블로 보완
        if len(result) < top_n:
            ensemble = self._engine.recommend(user_id, top_n=top_n, strategy="ensemble")
            for r in ensemble:
                if r.product_id not in seen:
                    result.append(r)
                    seen.add(r.product_id)
                if len(result) >= top_n:
                    break

        # 이탈 방지 전략으로 마킹
        for r in result:
            r.strategy = "churn_prevention"
            r.reason = "이탈 방지 추천"

        return result[:top_n]

    def generate_daily_recommendations(
        self,
        user_ids: list[str],
        top_n: int = 5,
    ) -> dict[str, list[dict]]:
        """일일 추천 메일용 사용자별 맞춤 상품을 생성한다."""
        result: dict[str, list[dict]] = {}
        for uid in user_ids:
            recs = self._engine.recommend(uid, top_n=top_n, strategy="ensemble")
            result[uid] = [r.to_dict() for r in recs]
        return result

    def get_new_product_alerts(
        self,
        user_id: str,
        top_n: int = 5,
        new_product_days: int = 7,
        now: datetime | None = None,
    ) -> list[RecommendationResult]:
        """관심 카테고리 신상품을 추천한다."""
        now = now or datetime.utcnow()
        cutoff = now - timedelta(days=new_product_days)

        # 최근 등록된 신상품 필터
        new_pids = [
            pid
            for pid, registered_at in self._new_products.items()
            if registered_at >= cutoff
        ]
        if not new_pids:
            return []

        # 개인화 점수로 신상품 중 추천
        results = self._engine.personalization.score_products(user_id, new_pids, top_n=top_n)
        for r in results:
            r.strategy = "new_product_alert"
            r.reason = "관심 카테고리 신상품"

        # 점수가 없으면 단순 신상품 목록
        if not results:
            results = [
                RecommendationResult(
                    product_id=pid,
                    score=1.0,
                    strategy="new_product_alert",
                    reason="신상품",
                )
                for pid in new_pids[:top_n]
            ]

        return results[:top_n]
