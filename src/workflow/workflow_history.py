"""src/workflow/workflow_history.py — 워크플로 히스토리 저장소."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class WorkflowHistory:
    """인스턴스별 전환 이력 저장."""

    def __init__(self) -> None:
        self._history: Dict[str, List[dict]] = {}

    def record(self, instance_id: str, from_state: str, to_state: str) -> dict:
        entry = {
            "instance_id": instance_id,
            "from_state": from_state,
            "to_state": to_state,
            "timestamp": _now_iso(),
        }
        self._history.setdefault(instance_id, []).append(entry)
        return entry

    def get(self, instance_id: str) -> List[dict]:
        return list(self._history.get(instance_id, []))

    def get_all(self) -> Dict[str, List[dict]]:
        return dict(self._history)
