"""src/workflow/workflow_definition.py — 워크플로 정의."""
from __future__ import annotations

from typing import List, Optional

from .state import State
from .transition import Transition


class WorkflowDefinition:
    """워크플로 정의 (상태 + 전환 + 초기상태)."""

    def __init__(self, name: str, states: List[State], transitions: List[Transition],
                 initial_state: str) -> None:
        self.name = name
        self.states = states
        self.transitions = transitions
        self.initial_state = initial_state
        self._state_map = {s.name: s for s in states}

    def get_state(self, name: str) -> Optional[State]:
        return self._state_map.get(name)

    def get_transitions_from(self, state_name: str) -> List[Transition]:
        return [t for t in self.transitions if t.from_state == state_name]

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "initial_state": self.initial_state,
            "states": [s.to_dict() for s in self.states],
            "transitions": [t.to_dict() for t in self.transitions],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "WorkflowDefinition":
        states = [State(**s) for s in data.get("states", [])]
        transitions = [Transition(**t) for t in data.get("transitions", [])]
        return cls(
            name=data["name"],
            states=states,
            transitions=transitions,
            initial_state=data["initial_state"],
        )
