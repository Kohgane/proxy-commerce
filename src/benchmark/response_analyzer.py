"""src/benchmark/response_analyzer.py — 응답 시간 분석."""
import logging
from typing import List

logger = logging.getLogger(__name__)


class ResponseAnalyzer:
    """응답 시간 통계 계산."""

    def analyze(self, response_times: List[float]) -> dict:
        if not response_times:
            return {'p50': 0, 'p95': 0, 'p99': 0, 'mean': 0, 'min': 0, 'max': 0, 'count': 0}
        sorted_times = sorted(response_times)
        count = len(sorted_times)

        def percentile(p: float) -> float:
            idx = int(count * p / 100)
            idx = min(idx, count - 1)
            return round(sorted_times[idx], 2)

        return {
            'p50': percentile(50),
            'p95': percentile(95),
            'p99': percentile(99),
            'mean': round(sum(sorted_times) / count, 2),
            'min': round(sorted_times[0], 2),
            'max': round(sorted_times[-1], 2),
            'count': count,
        }
