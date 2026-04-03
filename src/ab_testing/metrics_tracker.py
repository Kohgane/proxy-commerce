"""src/ab_testing/metrics_tracker.py — 이벤트 추적."""
import logging
from collections import defaultdict
from typing import Dict

logger = logging.getLogger(__name__)


class MetricsTracker:
    """실험별 변형 이벤트 추적."""

    def __init__(self):
        self._metrics: Dict[str, Dict[str, Dict[str, float]]] = defaultdict(
            lambda: defaultdict(lambda: defaultdict(float))
        )

    def track_event(self, experiment_id: str, variant: str, event_type: str, value: float = 1) -> None:
        self._metrics[experiment_id][variant][event_type] += value

    def get_metrics(self, experiment_id: str) -> dict:
        result = {}
        for variant, events in self._metrics.get(experiment_id, {}).items():
            result[variant] = {
                'conversions': events.get('conversion', 0),
                'clicks': events.get('click', 0),
                'revenue': events.get('revenue', 0),
                'impressions': events.get('impression', 0),
            }
        return result
