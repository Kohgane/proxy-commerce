"""src/virtual_inventory/stock_alerts.py — 가상 재고 알림 서비스 (Phase 113)."""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class AlertType(str, Enum):
    low_stock = 'low_stock'
    out_of_stock = 'out_of_stock'
    overstock = 'overstock'
    single_source_risk = 'single_source_risk'
    source_depleted = 'source_depleted'
    reservation_expiring = 'reservation_expiring'
    sync_discrepancy = 'sync_discrepancy'


class AlertSeverity(str, Enum):
    critical = 'critical'
    warning = 'warning'
    info = 'info'


@dataclass
class StockAlert:
    alert_id: str
    product_id: str
    alert_type: AlertType
    severity: AlertSeverity
    message: str
    current_stock: int
    threshold: int
    source_details: Dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    acknowledged: bool = False


class VirtualStockAlertService:
    """가상 재고 알림 서비스."""

    def __init__(self) -> None:
        self._alerts: Dict[str, StockAlert] = {}
        self._stock_pool = None
        self._daily_sales_rate: int = 1

    def set_stock_pool(self, pool) -> None:
        self._stock_pool = pool

    # ── 알림 체크 ─────────────────────────────────────────────────────────────

    def check_alerts(self, product_id: Optional[str] = None) -> List[StockAlert]:
        """알림 검사 후 새 알림 목록 반환."""
        if self._stock_pool is None:
            return []

        if product_id is not None:
            products = [self._stock_pool.get_virtual_stock(product_id)]
            products = [p for p in products if p is not None]
        else:
            products = self._stock_pool.get_all_virtual_stocks()

        new_alerts: List[StockAlert] = []
        rate = self._daily_sales_rate

        for vs in products:
            sources = vs.sources
            active_sources = [s for s in sources if s.is_active]

            # out_of_stock
            if vs.sellable == 0:
                alert = self._make_alert(
                    vs.product_id, AlertType.out_of_stock, AlertSeverity.critical,
                    f'재고 소진: {vs.product_id}', vs.sellable, 0,
                )
                new_alerts.append(alert)

            # low_stock
            elif vs.sellable <= rate * 3:
                alert = self._make_alert(
                    vs.product_id, AlertType.low_stock, AlertSeverity.warning,
                    f'재고 부족: {vs.product_id} ({vs.sellable}개)', vs.sellable, rate * 3,
                )
                new_alerts.append(alert)

            # overstock
            if vs.sellable > rate * 30:
                alert = self._make_alert(
                    vs.product_id, AlertType.overstock, AlertSeverity.info,
                    f'과잉 재고: {vs.product_id} ({vs.sellable}개)', vs.sellable, rate * 30,
                )
                new_alerts.append(alert)

            # single_source_risk
            if len(active_sources) == 1:
                alert = self._make_alert(
                    vs.product_id, AlertType.single_source_risk, AlertSeverity.warning,
                    f'단일 소싱처 위험: {vs.product_id}', vs.sellable, 0,
                    source_details={'active_sources': len(active_sources)},
                )
                new_alerts.append(alert)

            # source_depleted
            for src in sources:
                if src.available_qty == 0:
                    alert = self._make_alert(
                        vs.product_id, AlertType.source_depleted, AlertSeverity.info,
                        f'소싱처 재고 소진: {src.source_id}', 0, 0,
                        source_details={'source_id': src.source_id},
                    )
                    new_alerts.append(alert)

        return new_alerts

    def _make_alert(
        self,
        product_id: str,
        alert_type: AlertType,
        severity: AlertSeverity,
        message: str,
        current_stock: int,
        threshold: int,
        source_details: Optional[dict] = None,
    ) -> StockAlert:
        alert = StockAlert(
            alert_id=str(uuid.uuid4()),
            product_id=product_id,
            alert_type=alert_type,
            severity=severity,
            message=message,
            current_stock=current_stock,
            threshold=threshold,
            source_details=source_details or {},
            created_at=datetime.now(timezone.utc),
            acknowledged=False,
        )
        self._alerts[alert.alert_id] = alert
        return alert

    # ── 알림 조회 ─────────────────────────────────────────────────────────────

    def get_alerts(
        self,
        severity: Optional[str] = None,
        alert_type: Optional[str] = None,
        acknowledged: Optional[bool] = None,
    ) -> List[StockAlert]:
        alerts = list(self._alerts.values())
        if severity is not None:
            alerts = [a for a in alerts if a.severity.value == severity]
        if alert_type is not None:
            alerts = [a for a in alerts if a.alert_type.value == alert_type]
        if acknowledged is not None:
            alerts = [a for a in alerts if a.acknowledged == acknowledged]
        return alerts

    def acknowledge_alert(self, alert_id: str) -> bool:
        alert = self._alerts.get(alert_id)
        if alert is None:
            return False
        alert.acknowledged = True
        return True

    def get_alert_summary(self) -> dict:
        alerts = list(self._alerts.values())
        by_severity: Dict[str, int] = {}
        by_type: Dict[str, int] = {}
        for a in alerts:
            by_severity[a.severity.value] = by_severity.get(a.severity.value, 0) + 1
            by_type[a.alert_type.value] = by_type.get(a.alert_type.value, 0) + 1
        return {
            'total': len(alerts),
            'by_severity': by_severity,
            'by_type': by_type,
            'unacknowledged': sum(1 for a in alerts if not a.acknowledged),
        }
