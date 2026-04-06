"""src/seller_report/goal_manager.py — PerformanceGoalManager (Phase 114)."""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class GoalStatus(str, Enum):
    on_track = 'on_track'
    at_risk = 'at_risk'
    behind = 'behind'
    achieved = 'achieved'
    failed = 'failed'


@dataclass
class PerformanceGoal:
    goal_id: str
    metric_name: str
    target_value: float
    current_value: float
    progress_rate: float
    period: str
    start_date: date
    end_date: date
    status: GoalStatus
    created_at: datetime


class PerformanceGoalManager:
    """목표 설정 + 진행률 추적."""

    def __init__(self) -> None:
        self._goals: Dict[str, PerformanceGoal] = {}

    def set_goal(
        self,
        metric_name: str,
        target_value: float,
        period: str = 'monthly',
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> PerformanceGoal:
        """목표 설정."""
        today = date.today()
        start = start_date or today.replace(day=1)
        if end_date:
            end = end_date
        elif period == 'monthly':
            # 이번달 말일
            import calendar
            last_day = calendar.monthrange(today.year, today.month)[1]
            end = today.replace(day=last_day)
        elif period == 'weekly':
            end = today + __import__('datetime').timedelta(days=6)
        else:
            end = today

        goal_id = str(uuid.uuid4())[:8]
        goal = PerformanceGoal(
            goal_id=goal_id,
            metric_name=metric_name,
            target_value=target_value,
            current_value=0.0,
            progress_rate=0.0,
            period=period,
            start_date=start,
            end_date=end,
            status=GoalStatus.on_track,
            created_at=datetime.now(timezone.utc),
        )
        self._goals[goal_id] = goal
        return goal

    def get_goals(
        self,
        status: Optional[str] = None,
        period: Optional[str] = None,
    ) -> List[PerformanceGoal]:
        """목표 목록."""
        goals = list(self._goals.values())
        if status:
            goals = [g for g in goals if g.status.value == status]
        if period:
            goals = [g for g in goals if g.period == period]
        return goals

    def update_progress(self) -> List[PerformanceGoal]:
        """진행률 업데이트."""
        from .metrics_engine import PerformanceMetricsEngine
        engine = PerformanceMetricsEngine()
        metrics = engine.calculate_metrics('monthly')

        metric_map = {
            'total_revenue': metrics.total_revenue,
            'total_orders': metrics.total_orders,
            'gross_margin_rate': metrics.gross_margin_rate,
            'net_margin_rate': metrics.net_margin_rate,
            'fulfillment_rate': metrics.fulfillment_rate,
            'sla_compliance_rate': metrics.sla_compliance_rate,
            'return_rate': metrics.return_rate,
        }

        updated = []
        for goal in self._goals.values():
            current = metric_map.get(goal.metric_name, 0.0)
            goal.current_value = current
            goal.progress_rate = round(current / goal.target_value * 100, 2) if goal.target_value else 0.0

            today = date.today()
            days_total = max(1, (goal.end_date - goal.start_date).days)
            days_elapsed = (today - goal.start_date).days
            time_progress = days_elapsed / days_total

            if goal.progress_rate >= 100:
                goal.status = GoalStatus.achieved
            elif today > goal.end_date and goal.progress_rate < 100:
                goal.status = GoalStatus.failed
            elif goal.progress_rate >= time_progress * 100 * 0.9:
                goal.status = GoalStatus.on_track
            elif goal.progress_rate >= time_progress * 100 * 0.7:
                goal.status = GoalStatus.at_risk
            else:
                goal.status = GoalStatus.behind

            updated.append(goal)
        return updated

    def get_goal_dashboard(self) -> Dict[str, Any]:
        """목표 대시보드 (진행률 바)."""
        goals = self.get_goals()
        if not goals:
            return {'goals': [], 'summary': {'total': 0}}

        dashboard_items = []
        for g in goals:
            bar_filled = int(g.progress_rate / 5)  # 20칸 기준
            bar_empty = 20 - min(bar_filled, 20)
            progress_bar = '█' * min(bar_filled, 20) + '░' * bar_empty
            dashboard_items.append({
                'goal_id': g.goal_id,
                'metric_name': g.metric_name,
                'target': g.target_value,
                'current': g.current_value,
                'progress_rate': g.progress_rate,
                'status': g.status.value,
                'progress_bar': f"[{progress_bar}] {g.progress_rate:.1f}%",
                'period': g.period,
            })

        status_counts = {}
        for st in GoalStatus:
            status_counts[st.value] = sum(1 for g in goals if g.status == st)

        return {
            'goals': dashboard_items,
            'summary': {
                'total': len(goals),
                **status_counts,
            },
        }

    def check_goal_alerts(self) -> List[Dict[str, Any]]:
        """목표 달성/미달 알림."""
        alerts = []
        for goal in self._goals.values():
            if goal.status == GoalStatus.achieved:
                alerts.append({
                    'goal_id': goal.goal_id,
                    'type': 'achieved',
                    'message': f"🎉 목표 달성! {goal.metric_name} = {goal.current_value:.1f} (목표: {goal.target_value:.1f})",
                })
            elif goal.status == GoalStatus.behind:
                alerts.append({
                    'goal_id': goal.goal_id,
                    'type': 'behind',
                    'message': f"⚠️ 목표 지연: {goal.metric_name} 진행률 {goal.progress_rate:.1f}% (목표 대비 미달)",
                })
            elif goal.status == GoalStatus.failed:
                alerts.append({
                    'goal_id': goal.goal_id,
                    'type': 'failed',
                    'message': f"❌ 목표 미달: {goal.metric_name} = {goal.current_value:.1f} (목표: {goal.target_value:.1f})",
                })
        return alerts
