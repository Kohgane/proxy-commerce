"""src/ab_testing/metrics_tracker.py — 실험별 메트릭 수집."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class MetricsTracker:
    """실험별 전환율/클릭율/매출 메트릭 수집."""

    def __init__(self) -> None:
        # {experiment_id: {variant: {impressions, conversions, clicks, revenue}}}
        self._data: Dict[str, Dict[str, dict]] = defaultdict(
            lambda: defaultdict(lambda: {
                "impressions": 0,
                "conversions": 0,
                "clicks": 0,
                "revenue": 0.0,
                "events": [],
            })
        )

    def record_impression(self, experiment_id: str, variant: str, user_id: str = "") -> None:
        self._data[experiment_id][variant]["impressions"] += 1
        self._data[experiment_id][variant]["events"].append({
            "type": "impression", "user_id": user_id, "ts": _now_iso()
        })

    def record_click(self, experiment_id: str, variant: str, user_id: str = "") -> None:
        self._data[experiment_id][variant]["clicks"] += 1
        self._data[experiment_id][variant]["events"].append({
            "type": "click", "user_id": user_id, "ts": _now_iso()
        })

    def record_conversion(self, experiment_id: str, variant: str,
                          user_id: str = "", revenue: float = 0.0) -> None:
        self._data[experiment_id][variant]["conversions"] += 1
        self._data[experiment_id][variant]["revenue"] += revenue
        self._data[experiment_id][variant]["events"].append({
            "type": "conversion", "user_id": user_id, "revenue": revenue, "ts": _now_iso()
        })

    def get_metrics(self, experiment_id: str, variant: str = None) -> dict:
        """실험 메트릭 조회."""
        exp_data = self._data.get(experiment_id, {})
        if variant:
            raw = exp_data.get(variant, {"impressions": 0, "conversions": 0,
                                         "clicks": 0, "revenue": 0.0})
            return self._compute_rates(dict(raw))
        result = {}
        for v, raw in exp_data.items():
            result[v] = self._compute_rates(dict(raw))
        return result

    def _compute_rates(self, data: dict) -> dict:
        imp = data.get("impressions", 0)
        clicks = data.get("clicks", 0)
        conversions = data.get("conversions", 0)
        data["ctr"] = round(clicks / imp, 4) if imp > 0 else 0.0
        data["cvr"] = round(conversions / imp, 4) if imp > 0 else 0.0
        return data
