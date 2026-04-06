"""src/autonomous_ops/dashboard.py — 통합 운영 대시보드 (Phase 106)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Dict, List

if TYPE_CHECKING:
    from .engine import AutonomousOperationEngine
    from .revenue_model import RevenueTracker
    from .anomaly_detector import AnomalyDetector
    from .autopilot import AutoPilotController
    from .intervention import InterventionTracker, ManualTaskQueue

logger = logging.getLogger(__name__)


class UnifiedDashboard:
    """매출/주문/자동화율/건강도/비용/트렌드 통합 대시보드."""

    def __init__(
        self,
        engine: 'AutonomousOperationEngine',
        revenue_tracker: 'RevenueTracker',
        anomaly_detector: 'AnomalyDetector',
        autopilot: 'AutoPilotController',
        intervention_tracker: 'InterventionTracker',
        task_queue: 'ManualTaskQueue',
    ) -> None:
        self.engine = engine
        self.revenue_tracker = revenue_tracker
        self.anomaly_detector = anomaly_detector
        self.autopilot = autopilot
        self.intervention_tracker = intervention_tracker
        self.task_queue = task_queue

    def get_realtime_metrics(self) -> Dict:
        daily = self.revenue_tracker.get_daily_revenue()
        revenue_today = sum(daily.values())
        cost_today = revenue_today * 0.7
        profit_today = revenue_today - cost_today
        margin_rate = (profit_today / revenue_today) if revenue_today else 0.0

        status = self.engine.get_status()
        active_alerts = self.anomaly_detector.get_active_alerts()
        automation_rate = self.intervention_tracker.get_automation_coverage()

        return {
            'revenue_today': revenue_today,
            'profit_today': profit_today,
            'margin_rate': round(margin_rate, 4),
            'order_counts': 0,
            'automation_rate': round(automation_rate, 4),
            'active_alerts': len(active_alerts),
            'health_score': status.health_score,
            'operation_mode': status.mode.value,
            'timestamp': datetime.now(timezone.utc).isoformat(),
        }

    def get_revenue_analysis(self) -> Dict:
        records_raw = self.revenue_tracker.list_records(limit=1000)
        by_stream: Dict[str, float] = {}
        for r in records_raw:
            key = r['stream']
            by_stream[key] = by_stream.get(key, 0.0) + r['amount']
        return {
            'by_stream': by_stream,
            'by_channel': {},
        }

    def get_cost_analysis(self) -> Dict:
        records_raw = self.revenue_tracker.list_records(limit=1000)
        total_cost = sum(r['cost'] for r in records_raw)
        return {
            'product_cost': round(total_cost * 0.6, 2),
            'shipping': round(total_cost * 0.15, 2),
            'customs': round(total_cost * 0.1, 2),
            'commission': round(total_cost * 0.08, 2),
            'operation': round(total_cost * 0.05, 2),
            'fx_loss': round(total_cost * 0.02, 2),
            'total': round(total_cost, 2),
        }

    def get_trend_data(self) -> Dict:
        weekly = self.revenue_tracker.get_weekly_summary()
        monthly = self.revenue_tracker.get_monthly_summary()
        return {
            'weekly': weekly,
            'monthly': monthly,
        }

    def get_alert_history(self) -> List[Dict]:
        return self.anomaly_detector.list_alerts()

    def get_full_dashboard(self) -> Dict:
        return {
            'realtime': self.get_realtime_metrics(),
            'revenue': self.get_revenue_analysis(),
            'costs': self.get_cost_analysis(),
            'trends': self.get_trend_data(),
            'alerts': self.get_alert_history(),
            'autopilot_stats': self.autopilot.get_stats(),
            'intervention': self.intervention_tracker.get_stats(),
            'manual_queue': self.task_queue.get_stats(),
        }
