"""src/workflow_engine/workflow_engine.py — 워크플로 실행 엔진 (상태 머신 기반)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .workflow_definition import WorkflowDefinition
from .workflow_instance import WorkflowInstance
from .workflow_state import WorkflowState
from .workflow_transition import WorkflowTransition


def _build_order_workflow() -> WorkflowDefinition:
    """내장: 주문 처리 워크플로."""
    states = [
        WorkflowState("주문접수", "신규 주문 접수"),
        WorkflowState("결제확인", "결제 완료 확인"),
        WorkflowState("배송준비", "상품 포장 및 배송 준비"),
        WorkflowState("배송중", "배송 진행 중"),
        WorkflowState("배송완료", "배송 완료", is_terminal=True),
        WorkflowState("취소", "주문 취소", is_terminal=True),
    ]
    transitions = [
        WorkflowTransition("주문접수", "결제확인", name="결제완료"),
        WorkflowTransition("결제확인", "배송준비", name="준비시작"),
        WorkflowTransition("배송준비", "배송중", name="발송"),
        WorkflowTransition("배송중", "배송완료", name="도착"),
        WorkflowTransition("주문접수", "취소", name="취소처리"),
        WorkflowTransition("결제확인", "취소", name="취소처리"),
    ]
    return WorkflowDefinition(
        name="주문처리",
        initial_state="주문접수",
        states=states,
        transitions=transitions,
        description="주문 처리 워크플로",
    )


def _build_return_workflow() -> WorkflowDefinition:
    """내장: 반품 처리 워크플로."""
    states = [
        WorkflowState("반품접수", "반품 요청 접수"),
        WorkflowState("검수중", "반품 상품 검수"),
        WorkflowState("환불처리", "환불 진행"),
        WorkflowState("완료", "반품/환불 완료", is_terminal=True),
        WorkflowState("반려", "반품 반려", is_terminal=True),
    ]
    transitions = [
        WorkflowTransition("반품접수", "검수중", name="검수시작"),
        WorkflowTransition("검수중", "환불처리", name="검수통과"),
        WorkflowTransition("검수중", "반려", name="검수실패"),
        WorkflowTransition("환불처리", "완료", name="환불완료"),
    ]
    return WorkflowDefinition(
        name="반품처리",
        initial_state="반품접수",
        states=states,
        transitions=transitions,
        description="반품 처리 워크플로",
    )


def _build_cs_ticket_workflow() -> WorkflowDefinition:
    """내장: CS 티켓 워크플로."""
    states = [
        WorkflowState("접수", "CS 티켓 접수"),
        WorkflowState("담당자배정", "담당자 배정 완료"),
        WorkflowState("처리중", "처리 진행 중"),
        WorkflowState("해결", "문제 해결 완료", is_terminal=True),
        WorkflowState("종료", "티켓 종료", is_terminal=True),
    ]
    transitions = [
        WorkflowTransition("접수", "담당자배정", name="배정"),
        WorkflowTransition("담당자배정", "처리중", name="처리시작"),
        WorkflowTransition("처리중", "해결", name="해결완료"),
        WorkflowTransition("해결", "종료", name="종료"),
    ]
    return WorkflowDefinition(
        name="CS티켓",
        initial_state="접수",
        states=states,
        transitions=transitions,
        description="CS 티켓 처리 워크플로",
    )


def _build_product_register_workflow() -> WorkflowDefinition:
    """내장: 상품 등록 워크플로."""
    states = [
        WorkflowState("임시저장", "상품 임시 저장"),
        WorkflowState("검토중", "상품 정보 검토"),
        WorkflowState("승인대기", "최종 승인 대기"),
        WorkflowState("등록완료", "상품 등록 완료", is_terminal=True),
        WorkflowState("반려", "상품 등록 반려", is_terminal=True),
    ]
    transitions = [
        WorkflowTransition("임시저장", "검토중", name="검토요청"),
        WorkflowTransition("검토중", "승인대기", name="검토통과"),
        WorkflowTransition("검토중", "반려", name="검토실패"),
        WorkflowTransition("승인대기", "등록완료", name="승인"),
        WorkflowTransition("승인대기", "반려", name="반려"),
    ]
    return WorkflowDefinition(
        name="상품등록",
        initial_state="임시저장",
        states=states,
        transitions=transitions,
        description="상품 등록 워크플로",
    )


class WorkflowEngine:
    """워크플로 실행 엔진 (상태 머신 기반)."""

    def __init__(self) -> None:
        self._definitions: Dict[str, WorkflowDefinition] = {}
        self._instances: Dict[str, WorkflowInstance] = {}
        self._initialize_builtins()

    def _initialize_builtins(self) -> None:
        for builder in [
            _build_order_workflow,
            _build_return_workflow,
            _build_cs_ticket_workflow,
            _build_product_register_workflow,
        ]:
            defn = builder()
            self._definitions[defn.name] = defn

    def register(self, definition: WorkflowDefinition) -> None:
        self._definitions[definition.name] = definition

    def get_definition(self, name: str) -> Optional[WorkflowDefinition]:
        return self._definitions.get(name)

    def list_definitions(self) -> List[dict]:
        return [d.to_dict() for d in self._definitions.values()]

    def start(self, definition_name: str,
              context: Dict[str, Any] = None) -> WorkflowInstance:
        """새 워크플로 인스턴스 시작."""
        defn = self._definitions.get(definition_name)
        if defn is None:
            raise KeyError(f"워크플로 정의 없음: {definition_name}")
        instance = WorkflowInstance(
            definition_name=definition_name,
            initial_state=defn.initial_state,
            context=context or {},
        )
        self._instances[instance.instance_id] = instance
        return instance

    def transition(self, instance_id: str, transition_name: str,
                   context_updates: Dict[str, Any] = None) -> WorkflowInstance:
        """인스턴스 상태 전환."""
        instance = self._instances.get(instance_id)
        if instance is None:
            raise KeyError(f"인스턴스 없음: {instance_id}")
        defn = self._definitions.get(instance.definition_name)
        if defn is None:
            raise KeyError(f"워크플로 정의 없음: {instance.definition_name}")

        if context_updates:
            instance.context.update(context_updates)

        available = defn.get_transitions_from(instance.current_state)
        matched = [t for t in available
                   if t.name == transition_name
                   and t.can_transition(instance.context)]
        if not matched:
            raise ValueError(
                f"전환 불가: {instance.current_state} → {transition_name}"
            )
        trans = matched[0]
        instance.transition(trans.to_state, transition_name)

        # 종료 상태 확인
        state = defn.get_state(instance.current_state)
        if state and state.is_terminal:
            instance.complete()

        return instance

    def get_instance(self, instance_id: str) -> Optional[WorkflowInstance]:
        return self._instances.get(instance_id)

    def list_instances(self) -> List[dict]:
        return [i.to_dict() for i in self._instances.values()]

    def get_history(self, instance_id: str) -> List[dict]:
        instance = self._instances.get(instance_id)
        if instance is None:
            raise KeyError(f"인스턴스 없음: {instance_id}")
        return instance.history.get_all()
