"""src/email_service/email_tracker.py — 이메일 추적."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class EmailTracker:
    """이메일 발송/열람/클릭 추적."""

    def __init__(self) -> None:
        self._history: Dict[str, dict] = {}

    def record_sent(self, email_id: str, to: str, subject: str) -> None:
        self._history[email_id] = {
            "email_id": email_id,
            "to": to,
            "subject": subject,
            "sent_at": _now_iso(),
            "opened": False,
            "open_count": 0,
            "clicks": [],
        }

    def record_open(self, email_id: str) -> None:
        if email_id in self._history:
            self._history[email_id]["opened"] = True
            self._history[email_id]["open_count"] += 1
            self._history[email_id]["last_opened_at"] = _now_iso()

    def record_click(self, email_id: str, url: str) -> None:
        if email_id in self._history:
            self._history[email_id]["clicks"].append({"url": url, "clicked_at": _now_iso()})

    def get_history(self, limit: Optional[int] = None) -> List[dict]:
        items = list(self._history.values())
        if limit:
            items = items[-limit:]
        return items

    def get_stats(self) -> dict:
        total = len(self._history)
        opened = sum(1 for e in self._history.values() if e.get("opened"))
        total_clicks = sum(len(e.get("clicks", [])) for e in self._history.values())
        return {
            "total_sent": total,
            "total_opened": opened,
            "open_rate": round(opened / total * 100, 2) if total else 0,
            "total_clicks": total_clicks,
        }
