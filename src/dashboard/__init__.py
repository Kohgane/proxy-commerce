"""src/dashboard 패키지 — 주문 상태 추적 + 매출/마진 리포트 + 웹 UI."""

from .order_status import OrderStatusTracker
from .revenue_report import RevenueReporter
from .daily_summary import DailySummaryGenerator
from .web_ui import web_ui_bp

__all__ = [
    'OrderStatusTracker',
    'RevenueReporter',
    'DailySummaryGenerator',
    'web_ui_bp',
]
