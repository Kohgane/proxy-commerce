"""알림 규칙 및 알림 매니저."""
from __future__ import annotations

import logging
import operator as op
from dataclasses import dataclass
from typing import List

from .metrics import MetricsCollector

logger = logging.getLogger(__name__)

_OPERATORS = {
    ">": op.gt,
    ">=": op.ge,
    "<": op.lt,
    "<=": op.le,
    "==": op.eq,
    "!=": op.ne,
}


@dataclass
class AlertRule:
    name: str
    metric: str
    threshold: float
    operator: str = ">"
    message_template: str = ""


class AlertManager:
    """알림 규칙을 평가하고 Telegram 등으로 통보하는 매니저."""

    def __init__(self, notifier=None) -> None:
        self._notifier = notifier
        self._rules: List[AlertRule] = [
            AlertRule(name="error_rate_high", metric="errors_total", threshold=100.0, operator=">"),
            AlertRule(name="api_slow", metric="api_latency_seconds", threshold=2.0, operator=">"),
        ]

    def add_rule(self, rule: AlertRule) -> None:
        self._rules.append(rule)

    def evaluate(self, metrics: MetricsCollector) -> List[dict]:
        triggered = []
        for rule in self._rules:
            # 카운터·게이지 모두 조회 (카운터 우선)
            counter_val = metrics.get_counter(rule.metric)
            gauge_val = metrics.get_gauge(rule.metric)
            # 히스토그램이면 avg 사용
            hist_stats = metrics.get_histogram_stats(rule.metric)
            if hist_stats["count"] > 0:
                value = hist_stats["avg"]
            elif counter_val != 0:
                value = float(counter_val)
            else:
                value = gauge_val

            cmp_fn = _OPERATORS.get(rule.operator, op.gt)
            if cmp_fn(value, rule.threshold):
                triggered.append({
                    "rule": rule.name,
                    "metric": rule.metric,
                    "value": value,
                    "threshold": rule.threshold,
                    "triggered": True,
                })
        return triggered

    def evaluate_and_notify(self, metrics: MetricsCollector) -> List[dict]:
        triggered = self.evaluate(metrics)
        if triggered and self._notifier is not None:
            for alert in triggered:
                try:
                    msg = (
                        f"🚨 Alert [{alert['rule']}]: {alert['metric']} = {alert['value']}"
                        f" (threshold {alert['threshold']})"
                    )
                    self._notifier.send_message(msg)
                except Exception as exc:
                    logger.warning("알림 전송 실패: %s", exc)
        return triggered
