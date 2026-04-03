"""src/logging_tracing/log_aggregator.py — 로그 수집기."""
import logging
from collections import deque
from typing import List, Optional

logger = logging.getLogger(__name__)

MAX_LOGS = 1000


class LogAggregator:
    """로그 레코드 수집/조회."""

    def __init__(self, max_logs: int = MAX_LOGS):
        self._logs: deque = deque(maxlen=max_logs)
        self.max_logs = max_logs

    def add_log(self, log_record: dict) -> None:
        self._logs.append(log_record)

    def get_logs(
        self,
        limit: int = 100,
        level: Optional[str] = None,
        service: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> List[dict]:
        logs = list(self._logs)
        if level:
            logs = [l for l in logs if l.get('level', '').upper() == level.upper()]
        if service:
            logs = [l for l in logs if l.get('service') == service]
        if trace_id:
            logs = [l for l in logs if l.get('trace_id') == trace_id]
        return logs[-limit:]

    def clear(self) -> None:
        self._logs.clear()
