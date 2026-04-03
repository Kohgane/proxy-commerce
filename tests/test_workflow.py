"""tests/test_workflow.py — Phase 66: 워크플로 엔진 테스트."""
from __future__ import annotations

import pytest

from src.workflow import (
    State, Transition, WorkflowAction, WorkflowDefinition,
    WorkflowInstance, WorkflowEngine, WorkflowHistory,
)
from src.workflow.workflows.order_workflow import OrderWorkflow
from src.workflow.workflows.return_workflow import ReturnWorkflow


class TestState:
    def test_state_creation(self):
        s = State(name="초기", is_terminal=False)
        assert s.name == "초기"
        assert not s.is_terminal

    def test_terminal_state(self):
        s = State(name="완료", is_terminal=True)
        assert s.is_terminal

    def test_to_dict(self):
        s = State(name="test", on_enter="enter_action")
        d = s.to_dict()
        assert d["name"] == "test"
        assert d["on_enter"] == "enter_action"


class TestTransition:
    def test_transition_creation(self):
        t = Transition(from_state="A", to_state="B", condition="event1")
        assert t.from_state == "A"
        assert t.to_state == "B"
        assert t.condition == "event1"

    def test_to_dict(self):
        t = Transition(from_state="A", to_state="B")
        d = t.to_dict()
        assert d["from_state"] == "A"


class TestWorkflowDefinition:
    def test_create_definition(self):
        states = [State("A"), State("B", is_terminal=True)]
        transitions = [Transition("A", "B", condition="go")]
        defn = WorkflowDefinition("test_wf", states, transitions, "A")
        assert defn.name == "test_wf"
        assert defn.initial_state == "A"

    def test_get_state(self):
        states = [State("X")]
        defn = WorkflowDefinition("wf", states, [], "X")
        assert defn.get_state("X").name == "X"
        assert defn.get_state("missing") is None

    def test_get_transitions_from(self):
        states = [State("A"), State("B")]
        transitions = [Transition("A", "B", "go"), Transition("A", "B", "also")]
        defn = WorkflowDefinition("wf", states, transitions, "A")
        ts = defn.get_transitions_from("A")
        assert len(ts) == 2

    def test_from_dict(self):
        data = {
            "name": "my_wf",
            "initial_state": "start",
            "states": [{"name": "start"}, {"name": "end", "is_terminal": True}],
            "transitions": [{"from_state": "start", "to_state": "end", "condition": "finish"}],
        }
        defn = WorkflowDefinition.from_dict(data)
        assert defn.name == "my_wf"
        assert defn.initial_state == "start"


class TestWorkflowInstance:
    def test_creation(self):
        inst = WorkflowInstance("order", "주문접수")
        assert inst.current_state == "주문접수"
        assert len(inst.history) == 1

    def test_transition_to(self):
        inst = WorkflowInstance("order", "주문접수")
        inst.transition_to("결제")
        assert inst.current_state == "결제"
        assert len(inst.history) == 2

    def test_to_dict(self):
        inst = WorkflowInstance("order", "시작")
        d = inst.to_dict()
        assert "instance_id" in d
        assert "history" in d


class TestWorkflowEngine:
    def _make_engine(self):
        engine = WorkflowEngine()
        engine.register(OrderWorkflow.build())
        engine.register(ReturnWorkflow.build())
        return engine

    def test_list_definitions(self):
        engine = self._make_engine()
        defs = engine.list_definitions()
        names = [d["name"] for d in defs]
        assert "order" in names
        assert "return" in names

    def test_start_instance(self):
        engine = self._make_engine()
        inst = engine.start("order")
        assert inst.current_state == "주문접수"

    def test_transition(self):
        engine = self._make_engine()
        inst = engine.start("order")
        inst2 = engine.transition(inst.instance_id, "결제요청")
        assert inst2.current_state == "결제"

    def test_full_order_flow(self):
        engine = self._make_engine()
        inst = engine.start("order")
        engine.transition(inst.instance_id, "결제요청")
        engine.transition(inst.instance_id, "배송시작")
        engine.transition(inst.instance_id, "배송완료")
        status = engine.get_status(inst.instance_id)
        assert status["current_state"] == "완료"

    def test_missing_instance_raises(self):
        engine = self._make_engine()
        with pytest.raises(KeyError):
            engine.transition("no-such-id", "event")

    def test_invalid_event_raises(self):
        engine = self._make_engine()
        inst = engine.start("order")
        with pytest.raises(ValueError):
            engine.transition(inst.instance_id, "invalid_event")

    def test_get_status_missing(self):
        engine = self._make_engine()
        assert engine.get_status("missing") is None


class TestWorkflowHistory:
    def test_record_and_get(self):
        history = WorkflowHistory()
        entry = history.record("inst-1", "A", "B")
        assert entry["from_state"] == "A"
        assert entry["to_state"] == "B"
        records = history.get("inst-1")
        assert len(records) == 1

    def test_get_all(self):
        history = WorkflowHistory()
        history.record("i1", "A", "B")
        history.record("i2", "X", "Y")
        all_history = history.get_all()
        assert "i1" in all_history
        assert "i2" in all_history


class TestOrderWorkflow:
    def test_build(self):
        defn = OrderWorkflow.build()
        assert defn.name == "order"
        assert defn.initial_state == "주문접수"
        state_names = [s.name for s in defn.states]
        assert "완료" in state_names

    def test_terminal_state(self):
        defn = OrderWorkflow.build()
        terminal = [s for s in defn.states if s.is_terminal]
        assert len(terminal) == 1
        assert terminal[0].name == "완료"


class TestReturnWorkflow:
    def test_build(self):
        defn = ReturnWorkflow.build()
        assert defn.name == "return"
        assert defn.initial_state == "반품접수"

    def test_full_return_flow(self):
        engine = WorkflowEngine()
        engine.register(ReturnWorkflow.build())
        inst = engine.start("return")
        engine.transition(inst.instance_id, "검수요청")
        engine.transition(inst.instance_id, "환불승인")
        status = engine.get_status(inst.instance_id)
        assert status["current_state"] == "환불"
