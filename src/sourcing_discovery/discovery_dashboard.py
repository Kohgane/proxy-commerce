"""src/sourcing_discovery/discovery_dashboard.py — 발굴 대시보드 (Phase 115)."""
from __future__ import annotations

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class DiscoveryDashboard:
    """소싱 발굴 대시보드."""

    def get_dashboard_data(self) -> Dict[str, Any]:
        """대시보드 데이터 조회."""
        from src.sourcing_discovery.trend_analyzer import TrendAnalyzer
        from src.sourcing_discovery.opportunity_finder import SourcingOpportunityFinder
        from src.sourcing_discovery.market_gap_analyzer import MarketGapAnalyzer
        from src.sourcing_discovery.supplier_scout import SupplierScout
        from src.sourcing_discovery.discovery_alerts import DiscoveryAlertService
        from src.sourcing_discovery.profitability_predictor import ProfitabilityPredictor

        trend_analyzer = TrendAnalyzer()
        opportunity_finder = SourcingOpportunityFinder()
        gap_analyzer = MarketGapAnalyzer()
        scout = SupplierScout()
        alert_service = DiscoveryAlertService()
        predictor = ProfitabilityPredictor()

        # 기회 발굴
        opps = opportunity_finder.discover_opportunities(limit=20)
        approved = [o for o in opps if o.opportunity_score >= 85.0]

        # 트렌드 키워드
        rising = trend_analyzer.get_rising_trends(limit=10)
        trend_keywords = [
            {'keyword': t.keyword, 'growth_rate': t.growth_rate, 'direction': t.trend_direction.value}
            for t in rising
        ]

        # 카테고리 분포
        category_dist: Dict[str, int] = {}
        for opp in opps:
            category_dist[opp.category] = category_dist.get(opp.category, 0) + 1

        # 상위 수익성 상품
        top_profitable = []
        for opp in sorted(opps, key=lambda x: x.estimated_margin_rate, reverse=True)[:5]:
            pred = predictor.predict_profitability({
                'product_name': opp.product_name,
                'source_price': opp.source_price,
                'source_currency': opp.source_currency,
            })
            top_profitable.append({
                'product_name': opp.product_name,
                'margin_rate': pred.estimated_margin_rate,
                'monthly_profit': pred.estimated_monthly_profit,
                'recommended_model': pred.recommended_model,
            })

        # 마켓 갭
        top_gaps = gap_analyzer.get_top_gaps(limit=5)

        # 공급사 탐색
        candidates = scout.scout_suppliers()

        # 알림
        alerts = alert_service.get_alert_summary()

        return {
            'weekly_opportunities_found': len(opps),
            'weekly_approved': len(approved),
            'trend_keywords': trend_keywords,
            'category_distribution': category_dist,
            'top_profitable_products': top_profitable,
            'top_market_gaps': [
                {'category': g.category, 'description': g.description, 'gap_score': g.gap_score}
                for g in top_gaps
            ],
            'new_supplier_candidates': len(candidates),
            'pipeline_status': 'active',
            'alert_summary': alerts,
        }

    def get_weekly_discovery_report(self) -> Dict[str, Any]:
        """주간 발굴 리포트."""
        from src.sourcing_discovery.trend_analyzer import TrendAnalyzer
        from src.sourcing_discovery.opportunity_finder import SourcingOpportunityFinder
        from src.sourcing_discovery.market_gap_analyzer import MarketGapAnalyzer
        from datetime import datetime

        trend_analyzer = TrendAnalyzer()
        opportunity_finder = SourcingOpportunityFinder()
        gap_analyzer = MarketGapAnalyzer()

        summary = trend_analyzer.get_trend_summary()
        opps = opportunity_finder.discover_opportunities(limit=15)
        top_gaps = gap_analyzer.get_top_gaps(limit=3)

        return {
            'report_period': 'weekly',
            'generated_at': datetime.now().isoformat(),
            'trend_summary': summary,
            'opportunities_discovered': len(opps),
            'top_opportunities': [
                {
                    'product_name': o.product_name,
                    'score': o.opportunity_score,
                    'margin_rate': o.estimated_margin_rate,
                    'platform': o.source_platform,
                }
                for o in sorted(opps, key=lambda x: x.opportunity_score, reverse=True)[:5]
            ],
            'key_market_gaps': [
                {'category': g.category, 'gap_score': g.gap_score, 'action': g.recommended_action}
                for g in top_gaps
            ],
            'recommendation': '트렌드 기반 건강식품/뷰티 카테고리 집중 소싱 권장',
        }
