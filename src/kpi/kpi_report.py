"""src/kpi/kpi_report.py — KPI 리포트."""
from __future__ import annotations

import datetime


class KPIReport:
    """KPI 리포트 생성기."""

    def generate_summary(self, kpis: list) -> dict:
        """KPI 요약 리포트를 생성한다."""
        return {
            "total_kpis": len(kpis),
            "kpis": kpis,
            "generated_at": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
        }

    def generate_trends(self, kpi_name: str, history: list) -> dict:
        """KPI 트렌드를 생성한다."""
        values = [h.get("value", 0) for h in history if "value" in h]
        trend = "stable"
        if len(values) >= 2:
            if values[-1] > values[-2]:
                trend = "up"
            elif values[-1] < values[-2]:
                trend = "down"
        return {
            "kpi_name": kpi_name,
            "trend": trend,
            "data_points": len(values),
            "latest_value": values[-1] if values else None,
        }

    def generate_comparison(self, current: dict, previous: dict) -> dict:
        """현재와 이전 KPI를 비교한다."""
        comparison = {}
        for key in current:
            curr_val = current.get(key, 0)
            prev_val = previous.get(key, 0)
            if prev_val and prev_val != 0:
                change_pct = (curr_val - prev_val) / prev_val * 100
            else:
                change_pct = 0.0
            comparison[key] = {
                "current": curr_val,
                "previous": prev_val,
                "change_pct": round(change_pct, 2),
            }
        return comparison
