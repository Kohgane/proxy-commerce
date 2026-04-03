"""tests/test_workflow_engine.py — Phase 75: 워크플로 엔진 고도화 테스트."""
from __future__ import annotations

import pytest

from src.workflow_engine import (
    WorkflowState, WorkflowTransition, WorkflowDefinition,
    WorkflowTrigger, WorkflowHistory, WorkflowInstance, WorkflowEngine
)


class TestWorkflowState:
    def test_to_dict(self):
        state = WorkflowState(name="주문접수", description="신규 주문", is_terminal=False)
        d = state.to_dict()
        assert d["name"] == "주문접수"
        assert d["is_terminal"] is False


class TestWorkflowTransition:
    def test_can_transition_no_condition(self):
        trans = WorkflowTransition("A", "B", name="go")
        assert trans.can_transition({}) is True

    def test_can_transition_with_eq_condition(self):
        trans = WorkflowTransition("A", "B", condition="status=paid")
        assert trans.can_transition({"status": "paid"}) is True
        assert trans.can_transition({"status": "pending"}) is False

    def test_can_transition_with_neq_condition(self):
        trans = WorkflowTransition("A", "B", condition="status!=cancelled")
        assert trans.can_transition({"status": "paid"}) is True
        assert trans.can_transition({"status": "cancelled"}) is False

    def test_to_dict(self):
        trans = WorkflowTransition("A", "B", name="test", condition="x=1")
        d = trans.to_dict()
        assert d["from_state"] == "A"
        assert d["to_state"] == "B"
        assert "transition_id" in d


class TestWorkflowDefinition:
    def setup_method(self):
        self.defn = WorkflowDefinition(
            name="test",
            initial_state="A",
            states=[
                WorkflowState("A"),
                WorkflowState("B"),
                WorkflowState("C", is_terminal=True),
            ],
            transitions=[
                WorkflowTransition("A", "B", name="go_b"),
                WorkflowTransition("B", "C", name="go_c"),
            ],
        )

    def test_get_state(self):
        state = self.defn.get_state("A")
        assert state is not None
        assert state.name == "A"

    def test_get_transitions_from(self):
        transitions = self.defn.get_transitions_from("A")
        assert len(transitions) == 1
        assert transitions[0].to_state == "B"

    def test_to_dict(self):
        d = self.defn.to_dict()
        assert d["name"] == "test"
        assert len(d["states"]) == 3
        assert len(d["transitions"]) == 2


class TestWorkflowHistory:
    def test_record_and_get(self):
        history = WorkflowHistory()
        history.record("A", "B", "go_b")
        entries = history.get_all()
        assert len(entries) == 1
        assert entries[0]["from_state"] == "A"
        assert entries[0]["to_state"] == "B"

    def test_get_last(self):
        history = WorkflowHistory()
        history.record("A", "B")
        history.record("B", "C")
        last = history.get_last()
        assert last["to_state"] == "C"

    def test_count(self):
        history = WorkflowHistory()
        history.record("A", "B")
        history.record("B", "C")
        assert history.count() == 2


class TestWorkflowInstance:
    def test_creation(self):
        instance = WorkflowInstance("test_wf", "A")
        assert instance.current_state == "A"
        assert instance.status == "running"

    def test_transition(self):
        instance = WorkflowInstance("test_wf", "A")
        instance.transition("B", "go_b")
        assert instance.current_state == "B"
        assert instance.history.count() == 1

    def test_complete(self):
        instance = WorkflowInstance("test_wf", "A")
        instance.complete()
        assert instance.status == "completed"

    def test_fail(self):
        instance = WorkflowInstance("test_wf", "A")
        instance.fail("오류 발생")
        assert instance.status == "failed"
        assert instance.context["failure_reason"] == "오류 발생"

    def test_to_dict(self):
        instance = WorkflowInstance("test_wf", "A", context={"key": "val"})
        d = instance.to_dict()
        assert "instance_id" in d
        assert d["current_state"] == "A"
        assert d["context"]["key"] == "val"


class TestWorkflowEngine:
    def setup_method(self):
        self.engine = WorkflowEngine()

    def test_builtin_workflows_initialized(self):
        definitions = self.engine.list_definitions()
        names = [d["name"] for d in definitions]
        assert "주문처리" in names
        assert "반품처리" in names
        assert "CS티켓" in names
        assert "상품등록" in names

    def test_start_order_workflow(self):
        instance = self.engine.start("주문처리")
        assert instance.current_state == "주문접수"
        assert instance.status == "running"

    def test_transition_order_workflow(self):
        instance = self.engine.start("주문처리")
        updated = self.engine.transition(instance.instance_id, "결제완료")
        assert updated.current_state == "결제확인"

    def test_transition_to_terminal_state_completes(self):
        instance = self.engine.start("주문처리")
        self.engine.transition(instance.instance_id, "결제완료")
        self.engine.transition(instance.instance_id, "준비시작")
        self.engine.transition(instance.instance_id, "발송")
        completed = self.engine.transition(instance.instance_id, "도착")
        assert completed.status == "completed"

    def test_invalid_transition_raises(self):
        instance = self.engine.start("주문처리")
        with pytest.raises(ValueError):
            self.engine.transition(instance.instance_id, "invalid_transition")

    def test_get_instance(self):
        instance = self.engine.start("주문처리")
        retrieved = self.engine.get_instance(instance.instance_id)
        assert retrieved is not None
        assert retrieved.instance_id == instance.instance_id

    def test_get_history(self):
        instance = self.engine.start("주문처리")
        self.engine.transition(instance.instance_id, "결제완료")
        history = self.engine.get_history(instance.instance_id)
        assert len(history) == 1

    def test_register_custom_workflow(self):
        defn = WorkflowDefinition(
            name="custom_wf",
            initial_state="start",
            states=[
                WorkflowState("start"),
                WorkflowState("end", is_terminal=True),
            ],
            transitions=[
                WorkflowTransition("start", "end", name="finish"),
            ],
        )
        self.engine.register(defn)
        instance = self.engine.start("custom_wf")
        assert instance.current_state == "start"

    def test_cancel_order_workflow(self):
        instance = self.engine.start("주문처리")
        cancelled = self.engine.transition(instance.instance_id, "취소처리")
        assert cancelled.current_state == "취소"
        assert cancelled.status == "completed"


class TestWorkflowTrigger:
    def test_event_trigger(self):
        trigger = WorkflowTrigger(trigger_type="event", event_name="OrderCreated")
        d = trigger.to_dict()
        assert d["trigger_type"] == "event"
        assert d["event_name"] == "OrderCreated"

    def test_schedule_trigger(self):
        trigger = WorkflowTrigger(trigger_type="schedule", schedule="0 9 * * *")
        d = trigger.to_dict()
        assert d["schedule"] == "0 9 * * *"
