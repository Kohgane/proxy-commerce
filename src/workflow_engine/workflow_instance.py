"""src/workflow_engine/workflow_instance.py — 워크플로 실행 인스턴스."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .workflow_history import WorkflowHistory


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class WorkflowInstance:
    """워크플로 실행 인스턴스."""

    def __init__(self, definition_name: str, initial_state: str,
                 context: Dict[str, Any] = None) -> None:
        self.instance_id = str(uuid.uuid4())
        self.definition_name = definition_name
        self.current_state = initial_state
        self.context: Dict[str, Any] = context or {}
        self.history = WorkflowHistory()
        self.created_at = _now_iso()
        self.updated_at = _now_iso()
        self.status = "running"  # running, completed, failed

    def transition(self, to_state: str, transition_name: str = "") -> None:
        """상태 전환."""
        prev = self.current_state
        self.history.record(prev, to_state, transition_name, self.context)
        self.current_state = to_state
        self.updated_at = _now_iso()

    def complete(self) -> None:
        self.status = "completed"
        self.updated_at = _now_iso()

    def fail(self, reason: str = "") -> None:
        self.status = "failed"
        self.context["failure_reason"] = reason
        self.updated_at = _now_iso()

    def to_dict(self) -> dict:
        return {
            "instance_id": self.instance_id,
            "definition_name": self.definition_name,
            "current_state": self.current_state,
            "status": self.status,
            "context": self.context,
            "history": self.history.get_all(),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
