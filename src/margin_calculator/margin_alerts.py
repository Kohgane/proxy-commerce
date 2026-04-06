"""src/margin_calculator/margin_alerts.py — 마진율 임계값 기반 알림 시스템 (Phase 110).

MarginAlertService: 적자/저마진/목표 미달 알림 + 중복 방지
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from .calculator import MarginResult, RealTimeMarginCalculator
from .margin_config import MarginConfig

logger = logging.getLogger(__name__)

# 중복 방지 간격 (초) — 동일 상품 동일 등급 1시간 내 중복 방지
DEDUP_INTERVAL_SECONDS = 3600


class AlertSeverity(str, Enum):
    CRITICAL = 'CRITICAL'   # 적자 (마진 < 0%)
    WARNING = 'WARNING'     # 저마진 (마진 < 5%)
    INFO = 'INFO'           # 목표 미달
    GOOD = 'GOOD'           # 정상


@dataclass
class MarginAlert:
    """마진 알림."""
    alert_id: str
    product_id: str
    channel: str
    severity: AlertSeverity
    margin_rate: float
    net_profit: float
    selling_price: float
    message: str
    suggestion: str
    acknowledged: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    acknowledged_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            'alert_id': self.alert_id,
            'product_id': self.product_id,
            'channel': self.channel,
            'severity': self.severity.value if isinstance(self.severity, AlertSeverity) else self.severity,
            'margin_rate': self.margin_rate,
            'net_profit': self.net_profit,
            'selling_price': self.selling_price,
            'message': self.message,
            'suggestion': self.suggestion,
            'acknowledged': self.acknowledged,
            'created_at': self.created_at,
            'acknowledged_at': self.acknowledged_at,
        }


class MarginAlertService:
    """마진율 임계값 기반 알림 시스템."""

    def __init__(
        self,
        calculator: Optional[RealTimeMarginCalculator] = None,
        config: Optional[MarginConfig] = None,
    ) -> None:
        self._calc = calculator or RealTimeMarginCalculator()
        self._config = config or MarginConfig()
        self._alerts: Dict[str, MarginAlert] = {}  # alert_id → alert
        # 중복 방지: (product_id, channel, severity) → last_alerted timestamp
        self._last_alerted: Dict[tuple, float] = {}
        # 커스텀 임계값: product_id/category → {critical, warning, target}
        self._custom_thresholds: Dict[str, Dict[str, float]] = {}

    # ── 알림 확인 ─────────────────────────────────────────────────────────────

    def check_margin_alerts(
        self,
        product_id: Optional[str] = None,
        channel: str = 'internal',
    ) -> List[MarginAlert]:
        """알림 대상 상품 확인 및 알림 생성."""
        import time
        results: List[MarginResult]
        if product_id:
            results = [self._calc.calculate_margin(product_id, channel)]
        else:
            results = self._calc.calculate_bulk_margins(channel=channel)

        created: List[MarginAlert] = []
        for r in results:
            severity = self._classify(r)
            if severity == AlertSeverity.GOOD:
                continue

            dedup_key = (r.product_id, r.channel, severity.value)
            last_ts = self._last_alerted.get(dedup_key, 0.0)
            if time.time() - last_ts < DEDUP_INTERVAL_SECONDS:
                continue  # 중복 방지

            alert = self._build_alert(r, severity)
            self._alerts[alert.alert_id] = alert
            self._last_alerted[dedup_key] = time.time()
            created.append(alert)

        return created

    # ── 알림 조회 ─────────────────────────────────────────────────────────────

    def get_alerts(
        self,
        severity: Optional[str] = None,
        channel: Optional[str] = None,
        acknowledged: Optional[bool] = None,
    ) -> List[MarginAlert]:
        """알림 목록 조회."""
        alerts = list(self._alerts.values())
        if severity:
            alerts = [a for a in alerts if a.severity.value == severity.upper()]
        if channel:
            alerts = [a for a in alerts if a.channel == channel]
        if acknowledged is not None:
            alerts = [a for a in alerts if a.acknowledged == acknowledged]
        return alerts

    def acknowledge_alert(self, alert_id: str) -> Optional[MarginAlert]:
        """알림 확인 처리."""
        alert = self._alerts.get(alert_id)
        if not alert:
            return None
        alert.acknowledged = True
        alert.acknowledged_at = datetime.now(timezone.utc).isoformat()
        return alert

    def get_alert_summary(self) -> Dict[str, int]:
        """알림 요약 (등급별 개수)."""
        summary: Dict[str, int] = {s.value: 0 for s in AlertSeverity}
        for alert in self._alerts.values():
            sev = alert.severity.value if isinstance(alert.severity, AlertSeverity) else alert.severity
            summary[sev] = summary.get(sev, 0) + 1
        return summary

    # ── 임계값 커스터마이징 ────────────────────────────────────────────────────

    def set_threshold(self, key: str, critical: float, warning: float, target: float) -> None:
        """상품별/카테고리별 임계값 설정."""
        self._custom_thresholds[key] = {
            'critical': critical,
            'warning': warning,
            'target': target,
        }

    # ── 내부 로직 ─────────────────────────────────────────────────────────────

    def _get_thresholds(self, product_id: str) -> Dict[str, float]:
        """적용될 임계값 반환."""
        if product_id in self._custom_thresholds:
            return self._custom_thresholds[product_id]
        cfg = self._config.get_config(product_id=product_id)
        return {
            'critical': cfg['critical_margin_threshold'],
            'warning': cfg['warning_margin_threshold'],
            'target': cfg['default_target_margin'],
        }

    def _classify(self, result: MarginResult) -> AlertSeverity:
        thresholds = self._get_thresholds(result.product_id)
        m = result.margin_rate
        if m < thresholds['critical']:
            return AlertSeverity.CRITICAL
        if m < thresholds['warning']:
            return AlertSeverity.WARNING
        if m < thresholds['target']:
            return AlertSeverity.INFO
        return AlertSeverity.GOOD

    def _build_alert(self, result: MarginResult, severity: AlertSeverity) -> MarginAlert:
        if severity == AlertSeverity.CRITICAL:
            message = f"[{result.product_id}] 적자 판매 감지! 마진율 {result.margin_rate:.1f}%"
            suggestion = "즉시 판매 중지 또는 판매가 인상이 필요합니다."
        elif severity == AlertSeverity.WARNING:
            message = f"[{result.product_id}] 저마진 경고: 마진율 {result.margin_rate:.1f}%"
            suggestion = "가격 조정 또는 비용 절감을 검토하세요."
        else:
            message = f"[{result.product_id}] 목표 마진 미달: 마진율 {result.margin_rate:.1f}%"
            suggestion = "마진 개선 방안을 검토하세요."

        return MarginAlert(
            alert_id=str(uuid.uuid4()),
            product_id=result.product_id,
            channel=result.channel,
            severity=severity,
            margin_rate=result.margin_rate,
            net_profit=result.net_profit,
            selling_price=result.selling_price,
            message=message,
            suggestion=suggestion,
        )
