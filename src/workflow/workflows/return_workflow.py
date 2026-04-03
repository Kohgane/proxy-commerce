"""src/workflow/workflows/return_workflow.py — 반품 워크플로."""
from __future__ import annotations

from ..state import State
from ..transition import Transition
from ..workflow_definition import WorkflowDefinition


class ReturnWorkflow:
    """반품접수 → 검수 → 환불 워크플로."""

    @staticmethod
    def build() -> WorkflowDefinition:
        states = [
            State(name="반품접수"),
            State(name="검수"),
            State(name="환불", is_terminal=True),
        ]
        transitions = [
            Transition(from_state="반품접수", to_state="검수", condition="검수요청"),
            Transition(from_state="검수", to_state="환불", condition="환불승인"),
        ]
        return WorkflowDefinition(
            name="return",
            states=states,
            transitions=transitions,
            initial_state="반품접수",
        )
