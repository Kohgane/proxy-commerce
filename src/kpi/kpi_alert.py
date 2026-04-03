"""src/kpi/kpi_alert.py — KPI 알림."""
from __future__ import annotations

import datetime


class KPIAlert:
    """KPI 알림 관리자."""

    def __init__(self) -> None:
        self._alerts: list[dict] = []

    def check(self, kpi_name: str, current_value: float, target: float, threshold_pct: float = 10) -> dict:
        """KPI 목표 대비 현재 값을 확인하고 알림을 생성한다."""
        if target == 0:
            alert_type = "normal"
        else:
            diff_pct = abs(current_value - target) / target * 100
            if current_value >= target:
                alert_type = "goal_achieved"
            elif diff_pct <= threshold_pct:
                alert_type = "normal"
            else:
                alert_type = "missed"

        alert = {
            "kpi_name": kpi_name,
            "current_value": current_value,
            "target": target,
            "alert_type": alert_type,
            "checked_at": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
        }
        self._alerts.append(alert)
        return alert

    def get_alerts(self) -> list:
        """알림 목록을 반환한다."""
        return list(self._alerts)

    def clear(self) -> int:
        """알림을 모두 지우고 지운 수를 반환한다."""
        count = len(self._alerts)
        self._alerts.clear()
        return count
