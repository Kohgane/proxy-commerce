"""src/competitor_pricing/competitor_alerts.py — 경쟁사 가격 알림 서비스 (Phase 111)."""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

from .tracker import CompetitorTracker

logger = logging.getLogger(__name__)

_PRICE_CHANGE_THRESHOLD = 0.05  # 5%


class AlertType(str, Enum):
    price_drop = 'price_drop'
    price_increase = 'price_increase'
    new_competitor = 'new_competitor'
    competitor_out_of_stock = 'competitor_out_of_stock'
    competitor_back_in_stock = 'competitor_back_in_stock'
    price_war_detected = 'price_war_detected'
    lost_cheapest = 'lost_cheapest'
    became_cheapest = 'became_cheapest'


class AlertSeverity(str, Enum):
    critical = 'critical'
    warning = 'warning'
    info = 'info'


@dataclass
class CompetitorAlert:
    alert_id: str
    my_product_id: str
    competitor_id: str
    alert_type: AlertType
    message: str
    severity: AlertSeverity
    old_price: float = 0.0
    new_price: float = 0.0
    change_percent: float = 0.0
    created_at: str = field(
        default_factory=lambda: datetime.now(tz=timezone.utc).isoformat()
    )
    acknowledged: bool = False


class CompetitorAlertService:
    """경쟁사 가격 알림 서비스."""

    def __init__(self, tracker: Optional[CompetitorTracker] = None) -> None:
        self._tracker = tracker or CompetitorTracker()
        self._alerts: Dict[str, CompetitorAlert] = {}

    # ── 알림 체크 ─────────────────────────────────────────────────────────────

    def check_alerts(self) -> List[CompetitorAlert]:
        """가격 이력을 분석하여 새 알림을 생성한다."""
        new_alerts: List[CompetitorAlert] = []
        for cp in self._tracker.get_competitors():
            history = self._tracker.get_price_history(cp.competitor_id)
            if len(history) < 2:
                continue

            old_price = history[-2]['price']
            new_price = history[-1]['price']

            if old_price <= 0:
                continue

            change_pct = (new_price - old_price) / old_price

            if change_pct <= -_PRICE_CHANGE_THRESHOLD:
                alert = self._create_alert(
                    my_product_id=cp.product_id,
                    competitor_id=cp.competitor_id,
                    alert_type=AlertType.price_drop,
                    message=(
                        f"{cp.competitor_name}({cp.platform}) 가격 하락: "
                        f"{old_price:,.0f}원 → {new_price:,.0f}원 "
                        f"({change_pct*100:.1f}%)"
                    ),
                    severity=AlertSeverity.warning,
                    old_price=old_price,
                    new_price=new_price,
                    change_percent=round(change_pct * 100, 2),
                )
                new_alerts.append(alert)

            elif change_pct >= _PRICE_CHANGE_THRESHOLD:
                alert = self._create_alert(
                    my_product_id=cp.product_id,
                    competitor_id=cp.competitor_id,
                    alert_type=AlertType.price_increase,
                    message=(
                        f"{cp.competitor_name}({cp.platform}) 가격 상승: "
                        f"{old_price:,.0f}원 → {new_price:,.0f}원 "
                        f"(+{change_pct*100:.1f}%)"
                    ),
                    severity=AlertSeverity.info,
                    old_price=old_price,
                    new_price=new_price,
                    change_percent=round(change_pct * 100, 2),
                )
                new_alerts.append(alert)

        logger.info("알림 체크 완료: %d개 신규 알림", len(new_alerts))
        return new_alerts

    # ── 조회 / 상태 변경 ──────────────────────────────────────────────────────

    def get_alerts(
        self,
        severity: Optional[AlertSeverity] = None,
        alert_type: Optional[AlertType] = None,
        acknowledged: Optional[bool] = None,
    ) -> List[CompetitorAlert]:
        """알림 목록 반환 (필터링 가능)."""
        alerts = list(self._alerts.values())
        if severity:
            alerts = [a for a in alerts if a.severity == severity]
        if alert_type:
            alerts = [a for a in alerts if a.alert_type == alert_type]
        if acknowledged is not None:
            alerts = [a for a in alerts if a.acknowledged == acknowledged]
        return alerts

    def acknowledge_alert(self, alert_id: str) -> bool:
        """알림 확인 처리."""
        alert = self._alerts.get(alert_id)
        if not alert:
            return False
        alert.acknowledged = True
        return True

    def get_alert_summary(self) -> dict:
        """알림 요약 (타입별, 심각도별 카운트)."""
        by_type: Dict[str, int] = {t.value: 0 for t in AlertType}
        by_severity: Dict[str, int] = {s.value: 0 for s in AlertSeverity}
        for alert in self._alerts.values():
            by_type[alert.alert_type.value] += 1
            by_severity[alert.severity.value] += 1
        return {
            'total': len(self._alerts),
            'unacknowledged': sum(1 for a in self._alerts.values() if not a.acknowledged),
            'by_type': by_type,
            'by_severity': by_severity,
        }

    # ── 내부 헬퍼 ────────────────────────────────────────────────────────────

    def _create_alert(
        self,
        my_product_id: str,
        competitor_id: str,
        alert_type: AlertType,
        message: str,
        severity: AlertSeverity,
        old_price: float = 0.0,
        new_price: float = 0.0,
        change_percent: float = 0.0,
    ) -> CompetitorAlert:
        alert = CompetitorAlert(
            alert_id=str(uuid.uuid4()),
            my_product_id=my_product_id,
            competitor_id=competitor_id,
            alert_type=alert_type,
            message=message,
            severity=severity,
            old_price=old_price,
            new_price=new_price,
            change_percent=change_percent,
        )
        self._alerts[alert.alert_id] = alert
        return alert
