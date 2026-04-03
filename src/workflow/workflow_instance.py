"""src/workflow/workflow_instance.py — 워크플로 인스턴스."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class WorkflowInstance:
    """실행 중인 워크플로 인스턴스."""

    def __init__(self, definition_name: str, initial_state: str) -> None:
        self.instance_id = str(uuid.uuid4())
        self.definition_name = definition_name
        self.current_state = initial_state
        self.history: List[dict] = [{"state": initial_state, "timestamp": _now_iso()}]

    def transition_to(self, new_state: str) -> None:
        self.current_state = new_state
        self.history.append({"state": new_state, "timestamp": _now_iso()})

    def to_dict(self) -> dict:
        return {
            "instance_id": self.instance_id,
            "definition_name": self.definition_name,
            "current_state": self.current_state,
            "history": self.history,
        }
