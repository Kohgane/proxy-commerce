"""src/tenancy/usage_tracker.py — 테넌트 사용량 추적."""
import logging
from collections import defaultdict
from typing import Dict

logger = logging.getLogger(__name__)


class UsageTracker:
    """테넌트 사용량 추적."""

    def __init__(self):
        self._usage: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))

    def track(self, tenant_id: str, metric: str, increment: int = 1) -> int:
        self._usage[tenant_id][metric] += increment
        return self._usage[tenant_id][metric]

    def get_usage(self, tenant_id: str) -> dict:
        return dict(self._usage.get(tenant_id, {}))

    def reset_usage(self, tenant_id: str) -> None:
        if tenant_id in self._usage:
            del self._usage[tenant_id]
