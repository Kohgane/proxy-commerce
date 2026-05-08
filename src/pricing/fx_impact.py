"""src/pricing/fx_impact.py — Phase 140 환율 변동 영향 분석."""
from __future__ import annotations

import logging
import os
from decimal import Decimal
from typing import List, Optional

logger = logging.getLogger(__name__)


class FXImpactAnalyzer:
    def __init__(self, alert_threshold_pct: Optional[Decimal] = None):
        self.alert_threshold_pct = Decimal(
            str(alert_threshold_pct if alert_threshold_pct is not None else os.getenv("PRICING_FX_ALERT_THRESHOLD_PCT", "2"))
        )

    def daily_changes(self) -> dict:
        """전일 대비 변동률을 통화별로 반환한다.

        Returns:
            {"USD": Decimal(...), "JPY": Decimal(...), "CNY": Decimal(...)}
        """
        out = {"USD": Decimal("0"), "JPY": Decimal("0"), "CNY": Decimal("0")}
        try:
            from src.fx.history import FXHistory

            hist = FXHistory()
            for c in list(out.keys()):
                out[c] = Decimal(str(hist.get_change_pct(f"{c}KRW", days=1)))
        except Exception as exc:
            logger.debug("FXHistory 변동률 계산 실패: %s", exc)
        return out

    def detect_alerts(self) -> List[dict]:
        changes = self.daily_changes()
        alerts = []
        for currency, change in changes.items():
            if abs(change) >= self.alert_threshold_pct:
                alerts.append({
                    "currency": currency,
                    "change_pct": float(change),
                    "threshold_pct": float(self.alert_threshold_pct),
                })
        return alerts

    def impacted_products(self, catalog_rows: Optional[list] = None) -> list:
        changes = self.daily_changes()
        if catalog_rows is None:
            catalog_rows = self._load_catalog_rows()

        impacted = []
        for row in catalog_rows:
            currency = str(row.get("buy_currency") or row.get("currency") or "KRW").upper()
            if currency not in {"USD", "JPY", "CNY"}:
                continue
            change_pct = changes.get(currency, Decimal("0"))
            if abs(change_pct) < self.alert_threshold_pct:
                continue
            impacted.append({
                "sku": row.get("sku", ""),
                "buy_currency": currency,
                "fx_change_pct": float(change_pct),
                "sell_price_krw": int(float(row.get("sell_price_krw") or 0)),
            })
        return impacted

    def detect_and_notify(self, catalog_rows: Optional[list] = None) -> dict:
        alerts = self.detect_alerts()
        impacted = self.impacted_products(catalog_rows=catalog_rows)
        if alerts:
            self._notify(alerts, len(impacted))
        return {
            "alerts": alerts,
            "impacted": impacted,
            "threshold_pct": float(self.alert_threshold_pct),
        }

    def _load_catalog_rows(self) -> list:
        try:
            from src.utils.sheets import get_worksheet

            ws = get_worksheet("catalog")
            if ws is None:
                return []
            rows = ws.get_all_records()
            return [r for r in rows if str(r.get("status", "active")).strip().lower() in {"", "active"}]
        except Exception:
            return []

    @staticmethod
    def _notify(alerts: list, impacted_count: int) -> None:
        try:
            from src.notifications.telegram import send_telegram

            lines = ["💱 환율 변동 알림 (Phase 140)"]
            for alert in alerts:
                arrow = "↑" if alert["change_pct"] >= 0 else "↓"
                lines.append(
                    f"- {alert['currency']} {abs(alert['change_pct']):.1f}% {arrow} (임계 {alert['threshold_pct']:.1f}%)"
                )
            lines.append(f"- 영향 상품: {impacted_count}개")
            lines.append("- 확인: /seller/pricing/fx-impact")
            send_telegram("\n".join(lines), urgency="warning")
        except Exception as exc:
            logger.debug("FX 알림 실패: %s", exc)
