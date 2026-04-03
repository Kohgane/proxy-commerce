"""src/logging_tracing/log_aggregator.py — 로그 수집 및 검색."""
from __future__ import annotations

from collections import deque
from typing import Deque, List, Optional


class LogAggregator:
    """로그 수집 및 검색 (인메모리, 최근 N개 보관)."""

    def __init__(self, max_size: int = 10_000) -> None:
        self._logs: Deque[dict] = deque(maxlen=max_size)
        self.max_size = max_size

    def add(self, entry: dict) -> None:
        """로그 항목 추가."""
        if entry:
            self._logs.append(entry)

    def search(self, trace_id: str = None, level: str = None,
               service: str = None, keyword: str = None,
               limit: int = 100) -> List[dict]:
        """로그 검색."""
        results = list(self._logs)

        if trace_id:
            results = [r for r in results if r.get("trace_id") == trace_id]
        if level:
            results = [r for r in results if r.get("level") == level.upper()]
        if service:
            results = [r for r in results if r.get("service") == service]
        if keyword:
            kw = keyword.lower()
            results = [r for r in results if kw in str(r.get("message", "")).lower()]

        return results[-limit:]

    def get_by_trace(self, trace_id: str) -> List[dict]:
        """특정 trace_id의 모든 로그."""
        return [r for r in self._logs if r.get("trace_id") == trace_id]

    def clear(self) -> None:
        self._logs.clear()

    def count(self) -> int:
        return len(self._logs)

    def recent(self, n: int = 50) -> List[dict]:
        """최근 N개 로그."""
        logs = list(self._logs)
        return logs[-n:]
