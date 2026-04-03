"""src/workflow_engine/workflow_trigger.py — 워크플로 트리거."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class WorkflowTrigger:
    """워크플로 트리거 정의."""
    trigger_type: str    # 'event', 'schedule', 'manual'
    event_name: Optional[str] = None
    schedule: Optional[str] = None  # cron 표현식
    parameters: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "trigger_type": self.trigger_type,
            "event_name": self.event_name,
            "schedule": self.schedule,
            "parameters": self.parameters,
        }
