"""src/workflow/workflows/order_workflow.py — 주문 워크플로."""
from __future__ import annotations

from ..state import State
from ..transition import Transition
from ..workflow_definition import WorkflowDefinition


class OrderWorkflow:
    """주문접수 → 결제 → 배송 → 완료 워크플로."""

    @staticmethod
    def build() -> WorkflowDefinition:
        states = [
            State(name="주문접수"),
            State(name="결제"),
            State(name="배송"),
            State(name="완료", is_terminal=True),
        ]
        transitions = [
            Transition(from_state="주문접수", to_state="결제", condition="결제요청"),
            Transition(from_state="결제", to_state="배송", condition="배송시작"),
            Transition(from_state="배송", to_state="완료", condition="배송완료"),
        ]
        return WorkflowDefinition(
            name="order",
            states=states,
            transitions=transitions,
            initial_state="주문접수",
        )
