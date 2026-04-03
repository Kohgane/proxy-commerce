"""src/benchmark/regression_detector.py — 성능 회귀 감지."""
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

REGRESSION_THRESHOLD = 0.20  # 20%


class RegressionDetector:
    """이전 벤치마크 결과와 비교해 회귀 감지."""

    def __init__(self, threshold: float = REGRESSION_THRESHOLD):
        self._results: Dict[str, dict] = {}
        self.threshold = threshold

    def store_result(self, name: str, result: dict) -> None:
        self._results[name] = result

    def compare(self, name: str, new_result: dict) -> dict:
        old = self._results.get(name)
        if old is None:
            return {'degraded': False, 'metrics': {}, 'reason': 'no baseline'}
        old_stats = old.get('stats', {})
        new_stats = new_result.get('stats', {})
        metrics = {}
        degraded = False
        for metric in ('p50', 'p95', 'p99', 'mean'):
            old_val = old_stats.get(metric, 0)
            new_val = new_stats.get(metric, 0)
            if old_val > 0:
                change = (new_val - old_val) / old_val
                is_worse = change > self.threshold
                metrics[metric] = {
                    'old': old_val,
                    'new': new_val,
                    'change_rate': round(change, 4),
                    'degraded': is_worse,
                }
                if is_worse:
                    degraded = True
        return {'degraded': degraded, 'metrics': metrics}

    def list_results(self) -> Dict[str, dict]:
        return dict(self._results)
