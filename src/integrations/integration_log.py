"""src/integrations/integration_log.py — 연동 이벤트 로그."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class IntegrationLog:
    """연동 이벤트 로그 관리."""

    def __init__(self) -> None:
        self._log: List[dict] = []

    def record(self, name: str, success: bool, details: str, error: Optional[str] = None) -> None:
        self._log.append({
            "name": name,
            "success": success,
            "details": details,
            "error": error,
            "recorded_at": _now_iso(),
        })

    def get_log(self, name: Optional[str] = None) -> List[dict]:
        if name:
            return [e for e in self._log if e["name"] == name]
        return list(self._log)

    def get_stats(self, name: str) -> dict:
        entries = [e for e in self._log if e["name"] == name]
        total = len(entries)
        successes = sum(1 for e in entries if e["success"])
        return {
            "name": name,
            "total": total,
            "successes": successes,
            "failures": total - successes,
            "success_rate": round(successes / total * 100, 2) if total else 0,
        }
