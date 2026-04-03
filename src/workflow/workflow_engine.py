"""src/workflow/workflow_engine.py — 워크플로 엔진."""
from __future__ import annotations

from typing import Dict, List, Optional

from .workflow_definition import WorkflowDefinition
from .workflow_instance import WorkflowInstance
from .workflow_history import WorkflowHistory


class WorkflowEngine:
    """워크플로 정의 등록 및 인스턴스 실행 관리."""

    def __init__(self) -> None:
        self._definitions: Dict[str, WorkflowDefinition] = {}
        self._instances: Dict[str, WorkflowInstance] = {}
        self._history = WorkflowHistory()

    def register(self, definition: WorkflowDefinition) -> None:
        self._definitions[definition.name] = definition

    def list_definitions(self) -> List[dict]:
        return [d.to_dict() for d in self._definitions.values()]

    def start(self, workflow_name: str) -> WorkflowInstance:
        definition = self._definitions.get(workflow_name)
        if definition is None:
            raise KeyError(f"워크플로 정의 없음: {workflow_name}")
        instance = WorkflowInstance(definition_name=workflow_name,
                                    initial_state=definition.initial_state)
        self._instances[instance.instance_id] = instance
        return instance

    def transition(self, instance_id: str, event: str) -> WorkflowInstance:
        instance = self._instances.get(instance_id)
        if instance is None:
            raise KeyError(f"인스턴스 없음: {instance_id}")
        definition = self._definitions.get(instance.definition_name)
        if definition is None:
            raise KeyError(f"워크플로 정의 없음: {instance.definition_name}")

        transitions = definition.get_transitions_from(instance.current_state)
        target = None
        for t in transitions:
            if t.condition is None or t.condition == event:
                target = t.to_state
                break

        if target is None:
            raise ValueError(
                f"유효한 전환 없음: {instance.current_state} + event={event}"
            )
        from_state = instance.current_state
        instance.transition_to(target)
        self._history.record(instance_id, from_state, target)
        return instance

    def get_status(self, instance_id: str) -> Optional[dict]:
        instance = self._instances.get(instance_id)
        if instance is None:
            return None
        return {
            **instance.to_dict(),
            "transition_history": self._history.get(instance_id),
        }

    def get_all_history(self) -> dict:
        return self._history.get_all()
