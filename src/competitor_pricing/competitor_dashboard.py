"""src/competitor_pricing/competitor_dashboard.py — 경쟁사 가격 대시보드 (Phase 111)."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .tracker import CompetitorTracker
from .position_analyzer import PricePositionAnalyzer, PositionLabel
from .adjuster import PriceAdjustmentSuggester, SuggestionStatus

logger = logging.getLogger(__name__)


class CompetitorDashboard:
    """경쟁사 가격 모니터링 대시보드."""

    def __init__(
        self,
        tracker: Optional[CompetitorTracker] = None,
        analyzer: Optional[PricePositionAnalyzer] = None,
        adjuster: Optional[PriceAdjustmentSuggester] = None,
    ) -> None:
        self._tracker = tracker or CompetitorTracker()
        self._analyzer = analyzer or PricePositionAnalyzer(self._tracker)
        self._adjuster = adjuster or PriceAdjustmentSuggester(self._tracker, self._analyzer)

    # ── 대시보드 데이터 ───────────────────────────────────────────────────────

    def get_dashboard_data(self) -> Dict[str, Any]:
        """전체 대시보드 데이터 반환."""
        competitors = self._tracker.get_competitors()
        product_ids = list({cp.product_id for cp in competitors if cp.product_id})

        # 포지션 분포
        position_distribution = {label.value: 0 for label in PositionLabel}
        for pid in product_ids:
            try:
                pos = self._analyzer.analyze_position(pid)
                position_distribution[pos.position_label.value] += 1
            except Exception:
                pass

        # 경쟁사 통계
        total_competitors = len(competitors)
        avg_competitors_per_product = (
            total_competitors / len(product_ids) if product_ids else 0.0
        )

        # 독점 상품 (경쟁사 0개)
        monopoly_products = sum(
            1
            for pid in product_ids
            if not self._tracker.get_competitors(my_product_id=pid)
        )

        # 최근 가격 변경 이벤트 (최대 10개)
        recent_price_changes = self._get_recent_price_changes(limit=10)

        # 제안 통계
        suggestions = self._adjuster.get_suggestions()
        suggestion_stats = {
            SuggestionStatus.pending.value: sum(
                1 for s in suggestions if s.status == SuggestionStatus.pending
            ),
            SuggestionStatus.applied.value: sum(
                1 for s in suggestions if s.status == SuggestionStatus.applied
            ),
            SuggestionStatus.rejected.value: sum(
                1 for s in suggestions if s.status == SuggestionStatus.rejected
            ),
        }

        # 가격 전쟁 상품
        price_war_products = self._analyzer.detect_price_war()

        # 경쟁 강도 점수 (0-100)
        competition_score = self._calc_competition_score(
            total_competitors, len(product_ids), len(price_war_products)
        )

        return {
            'position_distribution': position_distribution,
            'total_competitors': total_competitors,
            'avg_competitors_per_product': round(avg_competitors_per_product, 2),
            'monopoly_products': monopoly_products,
            'recent_price_changes': recent_price_changes,
            'suggestion_stats': suggestion_stats,
            'price_war_products': price_war_products,
            'competition_score': competition_score,
        }

    def get_competition_intensity(self, my_product_id: Optional[str] = None) -> float:
        """경쟁 강도 반환 (경쟁사 수 × 가격 변동 빈도).

        반환값: 0 이상의 float (높을수록 경쟁 심화)
        """
        if my_product_id:
            competitors = self._tracker.get_competitors(my_product_id=my_product_id)
        else:
            competitors = self._tracker.get_competitors()

        total_changes = 0
        for cp in competitors:
            history = self._tracker.get_price_history(cp.competitor_id)
            changes = sum(
                1
                for i in range(1, len(history))
                if history[i]['price'] != history[i - 1]['price']
            )
            total_changes += changes

        return round(len(competitors) * (1 + total_changes / max(1, len(competitors))), 2)

    # ── 내부 헬퍼 ────────────────────────────────────────────────────────────

    def _get_recent_price_changes(self, limit: int = 10) -> List[dict]:
        """최근 가격 변동 이벤트 목록."""
        events: List[dict] = []
        for cp in self._tracker.get_competitors():
            history = self._tracker.get_price_history(cp.competitor_id)
            if len(history) < 2:
                continue
            old = history[-2]['price']
            new = history[-1]['price']
            if old != new:
                change_pct = ((new - old) / old * 100) if old > 0 else 0.0
                events.append(
                    {
                        'competitor_id': cp.competitor_id,
                        'competitor_name': cp.competitor_name,
                        'product_id': cp.product_id,
                        'old_price': old,
                        'new_price': new,
                        'change_percent': round(change_pct, 2),
                        'checked_at': history[-1].get('checked_at', ''),
                    }
                )
        events.sort(key=lambda e: e.get('checked_at', ''), reverse=True)
        return events[:limit]

    @staticmethod
    def _calc_competition_score(
        total_competitors: int, total_products: int, price_war_count: int
    ) -> float:
        """경쟁 점수 (0–100)."""
        if total_products == 0:
            return 0.0
        avg = total_competitors / total_products
        base = min(100.0, avg * 20)
        war_bonus = min(30.0, price_war_count * 10)
        return round(min(100.0, base + war_bonus), 2)
