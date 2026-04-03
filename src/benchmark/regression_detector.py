"""src/benchmark/regression_detector.py — 성능 회귀 감지."""
from __future__ import annotations

from typing import List, Optional


class RegressionDetector:
    """이전 결과와 비교하여 성능 저하 감지."""

    def __init__(self, threshold_pct: float = 20.0) -> None:
        """threshold_pct: 성능 저하 감지 기준 (예: 20 = 20% 이상 증가 시 회귀)."""
        self.threshold_pct = threshold_pct
        self._history: List[dict] = []

    def add_result(self, report: dict) -> None:
        """결과 이력 추가."""
        self._history.append(report)

    def compare(self, current: dict, baseline: dict = None) -> dict:
        """현재 결과와 기준 결과 비교."""
        if baseline is None:
            if len(self._history) < 2:
                return {"regression": False, "message": "기준 데이터 없음"}
            baseline = self._history[-2]

        current_stats = current.get("stats", {})
        baseline_stats = baseline.get("stats", {})

        metrics = ["mean", "p95", "p99"]
        regressions = []
        improvements = []

        for m in metrics:
            cur_val = current_stats.get(m, 0)
            base_val = baseline_stats.get(m, 0)
            if base_val == 0:
                continue
            change_pct = (cur_val - base_val) / base_val * 100
            entry = {"metric": m, "baseline": base_val, "current": cur_val,
                     "change_pct": round(change_pct, 2)}
            if change_pct > self.threshold_pct:
                regressions.append(entry)
            elif change_pct < -self.threshold_pct:
                improvements.append(entry)

        return {
            "regression": len(regressions) > 0,
            "regressions": regressions,
            "improvements": improvements,
            "threshold_pct": self.threshold_pct,
        }

    def get_history(self) -> List[dict]:
        return list(self._history)
