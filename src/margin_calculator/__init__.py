"""src/margin_calculator/__init__.py — 마진 계산기 패키지 (Phase 110)."""
from .calculator import RealTimeMarginCalculator, MarginResult
from .cost_breakdown import CostBreakdownService
from .platform_fees import PlatformFeeCalculator
from .margin_alerts import MarginAlertService, AlertSeverity, MarginAlert
from .margin_simulator import MarginSimulator
from .profitability import ProfitabilityAnalyzer
from .margin_trend import MarginTrendAnalyzer
from .margin_config import MarginConfig

__all__ = [
    'RealTimeMarginCalculator',
    'MarginResult',
    'CostBreakdownService',
    'PlatformFeeCalculator',
    'MarginAlertService',
    'AlertSeverity',
    'MarginAlert',
    'MarginSimulator',
    'ProfitabilityAnalyzer',
    'MarginTrendAnalyzer',
    'MarginConfig',
]
