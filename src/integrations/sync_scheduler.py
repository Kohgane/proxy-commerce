"""src/integrations/sync_scheduler.py — 연동 동기화 스케줄러."""
from __future__ import annotations

import time
from typing import Dict, List

from .integration_registry import IntegrationRegistry


class SyncScheduler:
    """연동 동기화 스케줄 관리."""

    def __init__(self) -> None:
        self._schedule: Dict[str, dict] = {}
        self._last_sync: Dict[str, float] = {}

    def schedule(self, name: str, interval_seconds: int) -> None:
        self._schedule[name] = {"name": name, "interval_seconds": interval_seconds}

    def run_due_syncs(self, registry: IntegrationRegistry) -> List[dict]:
        results = []
        now = time.monotonic()
        for name, config in self._schedule.items():
            last = self._last_sync.get(name, 0)
            if now - last >= config["interval_seconds"]:
                connector = registry.get(name)
                if connector:
                    try:
                        result = connector.sync()
                        self._last_sync[name] = now
                        results.append({"name": name, "status": "ok", "result": result})
                    except Exception as exc:
                        results.append({"name": name, "status": "error", "error": str(exc)})
        return results

    def get_schedule(self) -> List[dict]:
        return list(self._schedule.values())
