"""src/ai_recommendation/feedback_loop.py — Phase 94: 추천 피드백 루프."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime

# 가중치 혼합 비율: 기존 가중치 유지 비율 (성과 기반 비율 = 1 - _WEIGHT_BLEND_KEEP)
_WEIGHT_BLEND_KEEP = 0.7
_WEIGHT_BLEND_PERF = 1.0 - _WEIGHT_BLEND_KEEP
# 전략 가중치 기본값 (성과 데이터 없을 때 폴백)
_DEFAULT_STRATEGY_WEIGHT = 0.1


class FeedbackLoop:
    """추천 피드백 루프.

    - 추천 결과 추적 (노출 → 클릭 → 구매 전환)
    - 추천 정확도 메트릭 (CTR, CVR, 정밀도, 재현율)
    - 모델 성능 자동 평가 + 가중치 자동 조정
    - A/B 테스트 결과 반영
    """

    def __init__(self) -> None:
        # strategy -> {impressions, clicks, purchases}
        self._stats: dict[str, dict[str, int]] = defaultdict(
            lambda: {"impressions": 0, "clicks": 0, "purchases": 0}
        )
        # 추천 이력: rec_id -> {user_id, product_id, strategy, timestamp, clicked, purchased}
        self._history: dict[str, dict] = {}
        # 전략별 가중치 (동적 조정)
        self._strategy_weights: dict[str, float] = {
            "collaborative_user": 0.3,
            "collaborative_item": 0.2,
            "content_based": 0.2,
            "content_based_user": 0.15,
            "personalized": 0.25,
            "trending": 0.2,
            "cross_sell": 0.15,
            "upsell": 0.1,
        }

    def record_impression(
        self,
        rec_id: str,
        user_id: str,
        product_id: str,
        strategy: str,
    ) -> None:
        """추천 노출을 기록한다."""
        self._stats[strategy]["impressions"] += 1
        self._history[rec_id] = {
            "user_id": user_id,
            "product_id": product_id,
            "strategy": strategy,
            "timestamp": datetime.utcnow().isoformat(),
            "clicked": False,
            "purchased": False,
        }

    def record_click(self, rec_id: str) -> None:
        """추천 클릭을 기록한다."""
        if rec_id in self._history:
            self._history[rec_id]["clicked"] = True
            strategy = self._history[rec_id]["strategy"]
            self._stats[strategy]["clicks"] += 1

    def record_purchase(self, rec_id: str) -> None:
        """추천을 통한 구매를 기록한다."""
        if rec_id in self._history:
            self._history[rec_id]["purchased"] = True
            strategy = self._history[rec_id]["strategy"]
            self._stats[strategy]["purchases"] += 1

    def ctr(self, strategy: str) -> float:
        """클릭률(CTR)을 반환한다."""
        s = self._stats[strategy]
        if s["impressions"] == 0:
            return 0.0
        return s["clicks"] / s["impressions"]

    def cvr(self, strategy: str) -> float:
        """전환율(CVR: 클릭 → 구매)을 반환한다."""
        s = self._stats[strategy]
        if s["clicks"] == 0:
            return 0.0
        return s["purchases"] / s["clicks"]

    def purchase_rate(self, strategy: str) -> float:
        """노출 대비 구매율을 반환한다."""
        s = self._stats[strategy]
        if s["impressions"] == 0:
            return 0.0
        return s["purchases"] / s["impressions"]

    def precision(self, strategy: str) -> float:
        """추천 정밀도 (구매된 추천 / 전체 추천 클릭)."""
        return self.cvr(strategy)

    def get_metrics(self) -> dict:
        """전체 전략별 메트릭을 반환한다."""
        metrics: dict[str, dict] = {}
        for strategy, stats in self._stats.items():
            metrics[strategy] = {
                "impressions": stats["impressions"],
                "clicks": stats["clicks"],
                "purchases": stats["purchases"],
                "ctr": round(self.ctr(strategy), 4),
                "cvr": round(self.cvr(strategy), 4),
                "purchase_rate": round(self.purchase_rate(strategy), 4),
            }
        return metrics

    def auto_adjust_weights(self) -> dict[str, float]:
        """CVR 기반으로 전략 가중치를 자동 조정한다."""
        strategies = list(self._strategy_weights.keys())
        if not strategies:
            return self._strategy_weights

        # CVR 기반 점수 계산
        scores: dict[str, float] = {}
        for s in strategies:
            cvr = self.cvr(s)
            purchase_rate = self.purchase_rate(s)
            # CVR과 구매율을 합산한 성과 점수
            scores[s] = cvr * 0.6 + purchase_rate * 0.4

        total_score = sum(scores.values())
        if total_score == 0:
            return self._strategy_weights

        # 성과 점수 기반으로 가중치 재계산 (이전 가중치와 혼합)
        new_weights: dict[str, float] = {}
        for s in strategies:
            perf_weight = scores[s] / total_score
            # 기존 가중치 70% + 성과 기반 가중치 30%
            blended = self._strategy_weights.get(s, _DEFAULT_STRATEGY_WEIGHT) * _WEIGHT_BLEND_KEEP + perf_weight * _WEIGHT_BLEND_PERF
            new_weights[s] = round(blended, 4)

        self._strategy_weights = new_weights
        return self._strategy_weights

    def get_strategy_weights(self) -> dict[str, float]:
        """현재 전략 가중치를 반환한다."""
        return dict(self._strategy_weights)

    def set_strategy_weight(self, strategy: str, weight: float) -> None:
        """특정 전략의 가중치를 설정한다."""
        self._strategy_weights[strategy] = weight
