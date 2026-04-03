"""src/workflow_engine/workflow_definition.py — 워크플로 정의."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .workflow_state import WorkflowState
from .workflow_transition import WorkflowTransition


@dataclass
class WorkflowDefinition:
    """워크플로 정의 (상태 머신)."""
    name: str
    initial_state: str
    states: List[WorkflowState] = field(default_factory=list)
    transitions: List[WorkflowTransition] = field(default_factory=list)
    triggers: List[dict] = field(default_factory=list)
    description: str = ""
    definition_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def get_state(self, name: str) -> Optional[WorkflowState]:
        for s in self.states:
            if s.name == name:
                return s
        return None

    def get_transitions_from(self, state_name: str) -> List[WorkflowTransition]:
        return [t for t in self.transitions if t.from_state == state_name]

    def to_dict(self) -> dict:
        return {
            "definition_id": self.definition_id,
            "name": self.name,
            "description": self.description,
            "initial_state": self.initial_state,
            "states": [s.to_dict() for s in self.states],
            "transitions": [t.to_dict() for t in self.transitions],
            "triggers": self.triggers,
        }
