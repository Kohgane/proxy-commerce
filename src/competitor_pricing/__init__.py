"""src/competitor_pricing 패키지 — 경쟁사 가격 모니터링 + 자동 가격 조정 제안 (Phase 111)."""
from .tracker import CompetitorTracker, CompetitorProduct
from .matcher import CompetitorMatcher, CompetitorMatch, MatchType
from .position_analyzer import PricePositionAnalyzer, PricePosition, PositionLabel
from .adjuster import PriceAdjustmentSuggester, AdjustmentSuggestion, AdjustmentStrategy
from .price_rules import CompetitorPriceRules, PriceRule
from .competitor_alerts import CompetitorAlertService, CompetitorAlert, AlertType
from .competitor_dashboard import CompetitorDashboard
from .competitor_scheduler import CompetitorCheckScheduler

__all__ = [
    'CompetitorTracker', 'CompetitorProduct',
    'CompetitorMatcher', 'CompetitorMatch', 'MatchType',
    'PricePositionAnalyzer', 'PricePosition', 'PositionLabel',
    'PriceAdjustmentSuggester', 'AdjustmentSuggestion', 'AdjustmentStrategy',
    'CompetitorPriceRules', 'PriceRule',
    'CompetitorAlertService', 'CompetitorAlert', 'AlertType',
    'CompetitorDashboard',
    'CompetitorCheckScheduler',
]
