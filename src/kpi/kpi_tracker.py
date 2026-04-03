"""src/kpi/kpi_tracker.py — KPI 추적기."""
from __future__ import annotations

import datetime


class KPITracker:
    """KPI 값 추적기."""

    def __init__(self) -> None:
        self._history: dict[str, list] = {}

    def record(self, kpi_name: str, value: float, period: str = "daily") -> dict:
        """KPI 값을 기록한다."""
        entry = {
            "kpi_name": kpi_name,
            "value": value,
            "period": period,
            "recorded_at": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
        }
        self._history.setdefault(kpi_name, []).append(entry)
        return entry

    def get_history(self, kpi_name: str, limit: int = 30) -> list:
        """KPI 기록 이력을 반환한다."""
        records = self._history.get(kpi_name, [])
        return records[-limit:]

    def get_latest(self, kpi_name: str) -> dict:
        """최신 KPI 값을 반환한다."""
        records = self._history.get(kpi_name, [])
        if not records:
            return {}
        return records[-1]
