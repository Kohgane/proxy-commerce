"""src/ai_pricing/pricing_analytics.py — 가격 최적화 분석 모듈 (Phase 97)."""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List

from .pricing_models import PricingDecision, PricingMetrics

logger = logging.getLogger(__name__)


class PricingAnalytics:
    """가격 변경 효과, 탄력성, 경쟁력 지수, ROI 분석."""

    def __init__(self) -> None:
        # sku → list[PricingDecision]
        self._decisions: Dict[str, List[PricingDecision]] = defaultdict(list)
        # sku → {before: {revenue, profit}, after: {revenue, profit}}
        self._performance: Dict[str, Dict] = {}

    # ── 데이터 등록 ───────────────────────────────────────────────────────

    def record_decision(self, decision: PricingDecision) -> None:
        """가격 결정을 기록한다."""
        self._decisions[decision.sku].append(decision)

    def record_performance(
        self,
        sku: str,
        before_revenue: float,
        after_revenue: float,
        before_profit: float,
        after_profit: float,
    ) -> None:
        """가격 변경 전후 성과를 기록한다."""
        self._performance[sku] = {
            'before': {'revenue': before_revenue, 'profit': before_profit},
            'after': {'revenue': after_revenue, 'profit': after_profit},
        }

    # ── 효과 분석 ─────────────────────────────────────────────────────────

    def analyze_price_effect(self, sku: str) -> Dict:
        """가격 변경 Before/After 매출/이익 비교 분석."""
        perf = self._performance.get(sku)
        if not perf:
            return {'sku': sku, 'error': '성과 데이터 없음'}

        before = perf['before']
        after = perf['after']

        def pct(a, b):
            return round((b - a) / a * 100, 2) if a != 0 else 0.0

        return {
            'sku': sku,
            'before_revenue': before['revenue'],
            'after_revenue': after['revenue'],
            'revenue_change_pct': pct(before['revenue'], after['revenue']),
            'before_profit': before['profit'],
            'after_profit': after['profit'],
            'profit_change_pct': pct(before['profit'], after['profit']),
        }

    def analyze_all_effects(self) -> List[Dict]:
        """모든 SKU의 가격 효과를 분석한다."""
        return [self.analyze_price_effect(sku) for sku in self._performance]

    # ── 탄력성 리포트 ─────────────────────────────────────────────────────

    def elasticity_report(
        self, sku: str, elasticity: float
    ) -> Dict:
        """SKU별 탄력성 리포트를 생성한다."""
        category = (
            'inelastic' if abs(elasticity) < 1
            else 'unit_elastic' if abs(elasticity) == 1
            else 'elastic'
        )
        return {
            'sku': sku,
            'elasticity': elasticity,
            'category': category,
            'interpretation': {
                'inelastic': '비탄력적 — 가격 인상 여지 있음',
                'unit_elastic': '단위 탄력적',
                'elastic': '탄력적 — 가격 인하가 매출 증대에 유리',
            }.get(category, ''),
        }

    # ── 경쟁력 지수 ───────────────────────────────────────────────────────

    def competitiveness_score(
        self,
        our_price: float,
        competitor_min: float,
        competitor_avg: float,
        competitor_max: float,
    ) -> Dict:
        """경쟁력 지수를 계산한다 (100점 만점).

        점수 계산:
          - 최저가 대비 낮으면 +40
          - 평균 대비 낮으면 +30
          - 최고가 대비 낮으면 +30
        """
        score = 0.0
        details = {}

        if competitor_min > 0:
            ratio_min = our_price / competitor_min
            # 최저가보다 낮으면 40점, 높을수록 감점
            points = max(0, 40 * (2 - ratio_min))
            score += points
            details['vs_min'] = round(ratio_min, 4)

        if competitor_avg > 0:
            ratio_avg = our_price / competitor_avg
            points = max(0, 30 * (2 - ratio_avg))
            score += points
            details['vs_avg'] = round(ratio_avg, 4)

        if competitor_max > 0:
            ratio_max = our_price / competitor_max
            points = max(0, 30 * (2 - ratio_max))
            score += points
            details['vs_max'] = round(ratio_max, 4)

        final_score = min(100, round(score, 1))
        return {
            'our_price': our_price,
            'score': final_score,
            'grade': self._score_grade(final_score),
            'details': details,
        }

    def _score_grade(self, score: float) -> str:
        if score >= 80:
            return 'A'
        if score >= 60:
            return 'B'
        if score >= 40:
            return 'C'
        return 'D'

    # ── 수요 예측 정확도 ──────────────────────────────────────────────────

    def forecast_accuracy_report(
        self,
        sku: str,
        actuals: List[float],
        predictions: List[float],
        mape: float,
        rmse: float,
    ) -> Dict:
        """수요 예측 정확도 리포트를 생성한다."""
        return {
            'sku': sku,
            'periods': len(actuals),
            'mape': mape,
            'rmse': rmse,
            'accuracy_grade': 'A' if mape < 10 else 'B' if mape < 20 else 'C',
            'sample_actuals': actuals[:5],
            'sample_predictions': [round(p, 2) for p in predictions[:5]],
        }

    # ── ROI 분석 ─────────────────────────────────────────────────────────

    def roi_analysis(self) -> Dict:
        """동적 가격 적용 전후 전체 ROI를 분석한다."""
        all_effects = self.analyze_all_effects()
        if not all_effects:
            return {'error': '데이터 없음'}

        total_revenue_before = sum(
            e.get('before_revenue', 0) for e in all_effects
            if 'error' not in e
        )
        total_revenue_after = sum(
            e.get('after_revenue', 0) for e in all_effects
            if 'error' not in e
        )
        total_profit_before = sum(
            e.get('before_profit', 0) for e in all_effects
            if 'error' not in e
        )
        total_profit_after = sum(
            e.get('after_profit', 0) for e in all_effects
            if 'error' not in e
        )

        revenue_roi = (
            (total_revenue_after - total_revenue_before) / total_revenue_before * 100
            if total_revenue_before > 0 else 0.0
        )
        profit_roi = (
            (total_profit_after - total_profit_before) / total_profit_before * 100
            if total_profit_before > 0 else 0.0
        )

        return {
            'total_skus_analyzed': len(all_effects),
            'total_revenue_before': round(total_revenue_before, 2),
            'total_revenue_after': round(total_revenue_after, 2),
            'revenue_roi_pct': round(revenue_roi, 2),
            'total_profit_before': round(total_profit_before, 2),
            'total_profit_after': round(total_profit_after, 2),
            'profit_roi_pct': round(profit_roi, 2),
            'generated_at': datetime.now(timezone.utc).isoformat(),
        }

    # ── 전체 메트릭 ───────────────────────────────────────────────────────

    def get_metrics(self) -> PricingMetrics:
        """전체 가격 결정 메트릭을 반환한다."""
        all_decisions = [
            d for decisions in self._decisions.values() for d in decisions
        ]
        metrics = PricingMetrics()
        metrics.recalculate(all_decisions)
        return metrics

    def get_decision_history(self, sku: str) -> List[PricingDecision]:
        """SKU별 가격 결정 이력을 반환한다."""
        return list(self._decisions.get(sku, []))
