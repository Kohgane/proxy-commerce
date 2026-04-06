"""src/seller_report/performance_alerts.py — PerformanceAlertService (Phase 114)."""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class AlertType(str, Enum):
    revenue_drop = 'revenue_drop'
    margin_decline = 'margin_decline'
    return_spike = 'return_spike'
    sla_breach = 'sla_breach'
    stock_risk = 'stock_risk'
    channel_underperform = 'channel_underperform'
    product_grade_change = 'product_grade_change'


class AlertSeverity(str, Enum):
    critical = 'critical'
    warning = 'warning'
    info = 'info'


@dataclass
class PerformanceAlert:
    alert_id: str
    alert_type: str
    severity: str
    message: str
    metric_name: str
    current_value: float
    threshold_value: float
    change_rate: float
    affected_items: List[str]
    recommendation: str
    created_at: datetime
    acknowledged: bool = False


class PerformanceAlertService:
    """성과 이상 감지 알림."""

    # 알림 기준값
    REVENUE_DROP_THRESHOLD = -30.0     # 매출 30%+ 하락
    MARGIN_DECLINE_THRESHOLD = -5.0    # 마진율 5%p+ 하락
    RETURN_SPIKE_MULTIPLIER = 2.0      # 반품률 2배+ 상승
    SLA_BREACH_THRESHOLD = 80.0        # SLA 달성률 80% 미만

    def __init__(self) -> None:
        self._alerts: Dict[str, PerformanceAlert] = {}
        self._check_and_generate_sample_alerts()

    def _make_alert(
        self,
        alert_type: AlertType,
        severity: AlertSeverity,
        message: str,
        metric_name: str,
        current_value: float,
        threshold_value: float,
        change_rate: float = 0.0,
        affected_items: Optional[List[str]] = None,
        recommendation: str = '',
    ) -> PerformanceAlert:
        alert_id = str(uuid.uuid4())[:8]
        alert = PerformanceAlert(
            alert_id=alert_id,
            alert_type=alert_type.value,
            severity=severity.value,
            message=message,
            metric_name=metric_name,
            current_value=current_value,
            threshold_value=threshold_value,
            change_rate=change_rate,
            affected_items=affected_items or [],
            recommendation=recommendation,
            created_at=datetime.now(timezone.utc),
        )
        self._alerts[alert_id] = alert
        return alert

    def _check_and_generate_sample_alerts(self) -> None:
        """샘플 알림 생성 (데모용)."""
        import random

        # 매출 하락 (랜덤하게 발생)
        revenue_change = random.uniform(-40, 20)
        if revenue_change <= self.REVENUE_DROP_THRESHOLD:
            self._make_alert(
                AlertType.revenue_drop,
                AlertSeverity.critical,
                f"매출 전일 대비 {abs(revenue_change):.1f}% 하락",
                'total_revenue',
                current_value=800_000,
                threshold_value=1_200_000,
                change_rate=revenue_change,
                recommendation="프로모션 실행 또는 재고 보충 검토",
            )

        # 마진 하락
        margin_change = random.uniform(-8, 3)
        if margin_change <= self.MARGIN_DECLINE_THRESHOLD:
            self._make_alert(
                AlertType.margin_decline,
                AlertSeverity.warning,
                f"평균 마진율 {abs(margin_change):.1f}%p 하락",
                'gross_margin_rate',
                current_value=12.5,
                threshold_value=18.0,
                change_rate=margin_change,
                recommendation="소싱 비용 점검 및 가격 재조정 검토",
            )

        # SLA 위반 (랜덤하게 발생)
        sla_rate = random.uniform(70, 98)
        if sla_rate < self.SLA_BREACH_THRESHOLD:
            self._make_alert(
                AlertType.sla_breach,
                AlertSeverity.critical,
                f"SLA 달성률 {sla_rate:.1f}% (기준: {self.SLA_BREACH_THRESHOLD}%)",
                'sla_compliance_rate',
                current_value=sla_rate,
                threshold_value=self.SLA_BREACH_THRESHOLD,
                change_rate=0.0,
                recommendation="이행 프로세스 점검 및 소싱처 긴급 연락",
            )

        # 반품 급증
        return_rate = random.uniform(2, 18)
        prev_return_rate = return_rate / random.uniform(1.5, 3.5)
        if return_rate >= prev_return_rate * self.RETURN_SPIKE_MULTIPLIER:
            self._make_alert(
                AlertType.return_spike,
                AlertSeverity.warning,
                f"반품률 급증: {prev_return_rate:.1f}% → {return_rate:.1f}%",
                'return_rate',
                current_value=return_rate,
                threshold_value=prev_return_rate * self.RETURN_SPIKE_MULTIPLIER,
                change_rate=round((return_rate - prev_return_rate) / prev_return_rate * 100, 1),
                recommendation="반품 상품 QC 강화 및 상품 설명 개선",
            )

        # 채널 저성과
        self._make_alert(
            AlertType.channel_underperform,
            AlertSeverity.info,
            "네이버 스토어 성장률 전주 대비 -5.2%",
            'channel_growth_rate',
            current_value=-5.2,
            threshold_value=0.0,
            change_rate=-5.2,
            affected_items=['naver'],
            recommendation="네이버 광고 예산 재검토 및 상품 SEO 개선",
        )

    def check_alerts(self) -> List[PerformanceAlert]:
        """알림 대상 확인 + 생성."""
        from .metrics_engine import PerformanceMetricsEngine
        engine = PerformanceMetricsEngine()
        kpi = engine.get_kpi_summary()

        new_alerts = []

        # 매출 하락 체크
        revenue_change = kpi['revenue']['change_rate']
        if revenue_change <= self.REVENUE_DROP_THRESHOLD:
            alert = self._make_alert(
                AlertType.revenue_drop,
                AlertSeverity.critical,
                f"매출 전일 대비 {abs(revenue_change):.1f}% 하락",
                'total_revenue',
                current_value=kpi['revenue']['value'],
                threshold_value=0,
                change_rate=revenue_change,
                recommendation="긴급 프로모션 또는 재고 점검 필요",
            )
            new_alerts.append(alert)

        # SLA 달성률 체크
        sla_value = kpi['sla_compliance_rate']['value']
        if sla_value < self.SLA_BREACH_THRESHOLD:
            alert = self._make_alert(
                AlertType.sla_breach,
                AlertSeverity.critical,
                f"SLA 달성률 {sla_value:.1f}% — 기준치({self.SLA_BREACH_THRESHOLD}%) 미달",
                'sla_compliance_rate',
                current_value=sla_value,
                threshold_value=self.SLA_BREACH_THRESHOLD,
                recommendation="이행 프로세스 즉시 점검",
            )
            new_alerts.append(alert)

        return new_alerts

    def get_alerts(
        self,
        severity: Optional[str] = None,
        acknowledged: Optional[bool] = None,
    ) -> List[PerformanceAlert]:
        """알림 목록."""
        alerts = list(self._alerts.values())
        if severity:
            alerts = [a for a in alerts if a.severity == severity]
        if acknowledged is not None:
            alerts = [a for a in alerts if a.acknowledged == acknowledged]
        return sorted(alerts, key=lambda a: a.created_at, reverse=True)

    def acknowledge_alert(self, alert_id: str) -> bool:
        """알림 확인."""
        if alert_id in self._alerts:
            self._alerts[alert_id].acknowledged = True
            return True
        return False

    def get_alert_summary(self) -> Dict[str, Any]:
        """알림 요약."""
        alerts = list(self._alerts.values())
        critical = [a for a in alerts if a.severity == 'critical']
        warnings = [a for a in alerts if a.severity == 'warning']
        info_alerts = [a for a in alerts if a.severity == 'info']
        unacknowledged = [a for a in alerts if not a.acknowledged]

        return {
            'total': len(alerts),
            'critical': len(critical),
            'warning': len(warnings),
            'info': len(info_alerts),
            'unacknowledged': len(unacknowledged),
            'types': {
                alert_type.value: len([a for a in alerts if a.alert_type == alert_type.value])
                for alert_type in AlertType
            },
        }
