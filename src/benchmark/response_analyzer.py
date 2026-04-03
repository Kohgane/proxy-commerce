"""src/benchmark/response_analyzer.py — 응답시간 통계."""
from __future__ import annotations

import math
from typing import List


class ResponseAnalyzer:
    """응답시간 통계 (p50, p95, p99, mean, min, max)."""

    def analyze(self, response_times_ms: List[float]) -> dict:
        """응답시간 목록으로 통계 계산."""
        if not response_times_ms:
            return {
                "count": 0, "mean": 0.0, "min": 0.0, "max": 0.0,
                "p50": 0.0, "p95": 0.0, "p99": 0.0, "stddev": 0.0,
            }

        times = sorted(response_times_ms)
        n = len(times)
        mean = sum(times) / n
        variance = sum((t - mean) ** 2 for t in times) / n
        stddev = math.sqrt(variance)

        return {
            "count": n,
            "mean": round(mean, 2),
            "min": round(times[0], 2),
            "max": round(times[-1], 2),
            "p50": round(self._percentile(times, 50), 2),
            "p95": round(self._percentile(times, 95), 2),
            "p99": round(self._percentile(times, 99), 2),
            "stddev": round(stddev, 2),
        }

    def _percentile(self, sorted_data: List[float], percentile: int) -> float:
        """퍼센타일 계산 (선형 보간)."""
        if len(sorted_data) == 1:
            return sorted_data[0]
        k = (len(sorted_data) - 1) * percentile / 100
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return sorted_data[int(k)]
        return sorted_data[f] * (c - k) + sorted_data[c] * (k - f)

    def success_rate(self, total: int, errors: int) -> float:
        if total == 0:
            return 0.0
        return round((total - errors) / total * 100, 2)

    def throughput(self, total_requests: int, elapsed_seconds: float) -> float:
        """초당 처리량 (RPS)."""
        if elapsed_seconds <= 0:
            return 0.0
        return round(total_requests / elapsed_seconds, 2)
