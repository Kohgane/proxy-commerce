"""src/autonomous_ops/anomaly_detector.py — 이상 감지 시스템 (Phase 106)."""
from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional


class AnomalyType(str, Enum):
    revenue_drop = 'revenue_drop'
    cost_spike = 'cost_spike'
    order_surge = 'order_surge'
    order_drought = 'order_drought'
    conversion_drop = 'conversion_drop'
    refund_spike = 'refund_spike'
    delivery_delay_spike = 'delivery_delay_spike'
    seller_issue = 'seller_issue'
    system_error = 'system_error'


class AnomalySeverity(str, Enum):
    low = 'low'
    medium = 'medium'
    high = 'high'
    critical = 'critical'


@dataclass
class AnomalyAlert:
    alert_id: str
    type: AnomalyType
    severity: AnomalySeverity
    metric_name: str
    expected_value: float
    actual_value: float
    deviation_percent: float
    detected_at: str
    acknowledged: bool = False
    consecutive_count: int = 1
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            'alert_id': self.alert_id,
            'type': self.type.value,
            'severity': self.severity.value,
            'metric_name': self.metric_name,
            'expected_value': self.expected_value,
            'actual_value': self.actual_value,
            'deviation_percent': self.deviation_percent,
            'detected_at': self.detected_at,
            'acknowledged': self.acknowledged,
            'consecutive_count': self.consecutive_count,
            'metadata': self.metadata,
        }


class AnomalyDetector:
    """이동평균 ± 표준편차, 변동률, 임계값 기반 이상 감지."""

    def __init__(
        self,
        std_dev_threshold: float = 2.0,
        change_threshold_pct: float = 30.0,
        min_consecutive: int = 1,
    ) -> None:
        self.std_dev_threshold = std_dev_threshold
        self.change_threshold_pct = change_threshold_pct
        self.min_consecutive = min_consecutive
        self._alerts: Dict[str, AnomalyAlert] = {}
        self._metric_history: Dict[str, List[float]] = {}

    def add_metric_value(self, metric_name: str, value: float) -> None:
        self._metric_history.setdefault(metric_name, []).append(value)

    def check_metric(
        self,
        metric_name: str,
        current_value: float,
        anomaly_type: AnomalyType,
    ) -> Optional[AnomalyAlert]:
        history = self._metric_history.get(metric_name, [])
        if len(history) < 2:
            return None
        avg, std = self._calculate_moving_avg_std(history)
        if std == 0:
            return None
        deviation = abs(current_value - avg)
        if deviation < self.std_dev_threshold * std:
            return None
        deviation_pct = (deviation / avg * 100) if avg else 0.0
        severity = self._determine_severity(deviation_pct)
        alert = AnomalyAlert(
            alert_id=f'ano_{uuid.uuid4().hex[:10]}',
            type=anomaly_type,
            severity=severity,
            metric_name=metric_name,
            expected_value=round(avg, 4),
            actual_value=current_value,
            deviation_percent=round(deviation_pct, 2),
            detected_at=datetime.now(timezone.utc).isoformat(),
        )
        self._alerts[alert.alert_id] = alert
        return alert

    def check_change_rate(
        self,
        metric_name: str,
        current_value: float,
        previous_value: float,
        anomaly_type: AnomalyType,
    ) -> Optional[AnomalyAlert]:
        if previous_value == 0:
            return None
        change_pct = abs((current_value - previous_value) / previous_value * 100)
        if change_pct < self.change_threshold_pct:
            return None
        severity = self._determine_severity(change_pct)
        alert = AnomalyAlert(
            alert_id=f'ano_{uuid.uuid4().hex[:10]}',
            type=anomaly_type,
            severity=severity,
            metric_name=metric_name,
            expected_value=previous_value,
            actual_value=current_value,
            deviation_percent=round(change_pct, 2),
            detected_at=datetime.now(timezone.utc).isoformat(),
        )
        self._alerts[alert.alert_id] = alert
        return alert

    def check_threshold(
        self,
        metric_name: str,
        value: float,
        threshold: float,
        anomaly_type: AnomalyType,
        above: bool = True,
    ) -> Optional[AnomalyAlert]:
        triggered = (value > threshold) if above else (value < threshold)
        if not triggered:
            return None
        deviation_pct = abs((value - threshold) / threshold * 100) if threshold else 0.0
        severity = self._determine_severity(deviation_pct)
        alert = AnomalyAlert(
            alert_id=f'ano_{uuid.uuid4().hex[:10]}',
            type=anomaly_type,
            severity=severity,
            metric_name=metric_name,
            expected_value=threshold,
            actual_value=value,
            deviation_percent=round(deviation_pct, 2),
            detected_at=datetime.now(timezone.utc).isoformat(),
        )
        self._alerts[alert.alert_id] = alert
        return alert

    def acknowledge(self, alert_id: str) -> bool:
        alert = self._alerts.get(alert_id)
        if alert:
            alert.acknowledged = True
            return True
        return False

    def get_active_alerts(self) -> List[Dict]:
        return [a.to_dict() for a in self._alerts.values() if not a.acknowledged]

    def list_alerts(self, acknowledged: Optional[bool] = None) -> List[Dict]:
        alerts = list(self._alerts.values())
        if acknowledged is not None:
            alerts = [a for a in alerts if a.acknowledged == acknowledged]
        return [a.to_dict() for a in alerts]

    def _determine_severity(self, deviation_pct: float) -> AnomalySeverity:
        if deviation_pct < 50:
            return AnomalySeverity.low
        elif deviation_pct < 100:
            return AnomalySeverity.medium
        elif deviation_pct < 200:
            return AnomalySeverity.high
        return AnomalySeverity.critical

    def _calculate_moving_avg_std(self, values: List[float]) -> tuple:
        n = len(values)
        if n == 0:
            return 0.0, 0.0
        avg = sum(values) / n
        variance = sum((v - avg) ** 2 for v in values) / n
        std = math.sqrt(variance)
        return avg, std
