"""src/workflow_engine/workflow_history.py — 워크플로 실행 이력."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import List


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


@dataclass
class HistoryEntry:
    """이력 항목."""
    from_state: str
    to_state: str
    transition_name: str = ""
    timestamp: str = field(default_factory=_now_iso)
    entry_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    context_snapshot: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "entry_id": self.entry_id,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "transition_name": self.transition_name,
            "timestamp": self.timestamp,
            "context_snapshot": self.context_snapshot,
        }


class WorkflowHistory:
    """워크플로 실행 이력 관리."""

    def __init__(self) -> None:
        self._entries: List[HistoryEntry] = []

    def record(self, from_state: str, to_state: str,
               transition_name: str = "", context: dict = None) -> HistoryEntry:
        entry = HistoryEntry(
            from_state=from_state,
            to_state=to_state,
            transition_name=transition_name,
            context_snapshot=dict(context) if context else {},
        )
        self._entries.append(entry)
        return entry

    def get_all(self) -> List[dict]:
        return [e.to_dict() for e in self._entries]

    def get_last(self) -> dict:
        if not self._entries:
            return {}
        return self._entries[-1].to_dict()

    def count(self) -> int:
        return len(self._entries)
