"""src/marketplace_sync/sync_log.py — 동기화 로그."""
from __future__ import annotations

import datetime

from .sync_job import SyncJob


class SyncLog:
    """동기화 로그 관리자."""

    def __init__(self) -> None:
        self._logs: list[dict] = []

    def record(self, job: SyncJob) -> None:
        """동기화 작업 결과를 기록한다."""
        self._logs.append({
            **job.to_dict(),
            "recorded_at": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
        })

    def get_logs(self, marketplace: str | None = None, limit: int = 50) -> list:
        """로그 목록을 반환한다."""
        logs = self._logs
        if marketplace:
            logs = [l for l in logs if l.get("marketplace") == marketplace]
        return logs[-limit:]

    def get_summary(self) -> dict:
        """로그 요약을 반환한다."""
        total = len(self._logs)
        success = sum(1 for l in self._logs if l.get("status") == "completed")
        failed = sum(1 for l in self._logs if l.get("status") == "failed")
        skip = total - success - failed
        return {
            "total_jobs": total,
            "success_count": success,
            "failure_count": failed,
            "skip_count": max(skip, 0),
        }
