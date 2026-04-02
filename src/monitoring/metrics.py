"""순수 Python 기반 메트릭 수집기."""
from __future__ import annotations

from typing import Dict, List, Optional


class MetricsCollector:
    """카운터·히스토그램·게이지를 관리하는 순수 Python 메트릭 수집기."""

    DEFAULT_METRICS = [
        "orders_total",
        "errors_total",
        "api_latency_seconds",
        "active_products",
    ]

    def __init__(self) -> None:
        self._counters: Dict[str, int] = {}
        self._histograms: Dict[str, List[float]] = {}
        self._gauges: Dict[str, float] = {}
        for m in self.DEFAULT_METRICS:
            self._counters[m] = 0

    # ------------------------------------------------------------------
    # 내부 헬퍼
    # ------------------------------------------------------------------

    @staticmethod
    def _label_key(metric: str, labels: Optional[dict]) -> str:
        if not labels:
            return metric
        label_str = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
        return f"{metric}{{{label_str}}}"

    # ------------------------------------------------------------------
    # 공개 API
    # ------------------------------------------------------------------

    def increment(self, metric: str, value: int = 1, labels: Optional[dict] = None) -> None:
        key = self._label_key(metric, labels)
        self._counters[key] = self._counters.get(key, 0) + value

    def observe(self, metric: str, value: float, labels: Optional[dict] = None) -> None:
        key = self._label_key(metric, labels)
        self._histograms.setdefault(key, []).append(value)

    def set_gauge(self, metric: str, value: float, labels: Optional[dict] = None) -> None:
        key = self._label_key(metric, labels)
        self._gauges[key] = value

    def get_counter(self, metric: str) -> int:
        return self._counters.get(metric, 0)

    def get_gauge(self, metric: str) -> float:
        return self._gauges.get(metric, 0.0)

    def get_histogram_stats(self, metric: str) -> dict:
        values = self._histograms.get(metric, [])
        if not values:
            return {"count": 0, "sum": 0.0, "avg": 0.0, "min": 0.0, "max": 0.0}
        total = sum(values)
        return {
            "count": len(values),
            "sum": total,
            "avg": total / len(values),
            "min": min(values),
            "max": max(values),
        }

    def export_prometheus_text(self) -> str:
        lines: List[str] = []

        for key, value in self._counters.items():
            # 라벨이 포함된 키에서 기본 메트릭 이름 추출
            base = key.split("{")[0]
            lines.append(f"# HELP {base}")
            lines.append(f"# TYPE {base} counter")
            lines.append(f"{key} {value}")

        for key, values in self._histograms.items():
            base = key.split("{")[0]
            total = sum(values) if values else 0.0
            count = len(values)
            lines.append(f"# HELP {base}")
            lines.append(f"# TYPE {base} histogram")
            lines.append(f"{key}_sum {total}")
            lines.append(f"{key}_count {count}")

        for key, value in self._gauges.items():
            base = key.split("{")[0]
            lines.append(f"# HELP {base}")
            lines.append(f"# TYPE {base} gauge")
            lines.append(f"{key} {value}")

        return "\n".join(lines) + ("\n" if lines else "")

    def reset(self) -> None:
        self._counters.clear()
        self._histograms.clear()
        self._gauges.clear()
        for m in self.DEFAULT_METRICS:
            self._counters[m] = 0
