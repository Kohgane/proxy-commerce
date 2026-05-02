"""src/returns_automation/workflow_definition.py — Phase 118: 반품/교환 자동화 상태 머신.

상태 전환:
  requested → classified → approved / rejected / disputed
  approved → pickup_scheduled → in_return_transit → received → inspected
  inspected → refunded / exchanged / partially_refunded
  rejected (terminal)
  disputed (terminal → DisputeManager로 위임)

기존 src/workflow/ 엔진 활용 시도 후 자체 stateful manager fallback.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional, Set

from .models import ReturnStatus

logger = logging.getLogger(__name__)

# 허용된 상태 전환 맵
VALID_TRANSITIONS: Dict[ReturnStatus, List[ReturnStatus]] = {
    ReturnStatus.requested: [
        ReturnStatus.classified,
    ],
    ReturnStatus.classified: [
        ReturnStatus.approved,
        ReturnStatus.rejected,
        ReturnStatus.disputed,
    ],
    ReturnStatus.approved: [
        ReturnStatus.pickup_scheduled,
        ReturnStatus.rejected,  # 취소
    ],
    ReturnStatus.rejected: [],       # 종료 상태
    ReturnStatus.disputed: [],       # 종료 상태 (DisputeManager로 위임)
    ReturnStatus.pickup_scheduled: [
        ReturnStatus.in_return_transit,
    ],
    ReturnStatus.in_return_transit: [
        ReturnStatus.received,
    ],
    ReturnStatus.received: [
        ReturnStatus.inspected,
    ],
    ReturnStatus.inspected: [
        ReturnStatus.refunded,
        ReturnStatus.exchanged,
        ReturnStatus.partially_refunded,
        ReturnStatus.rejected,  # 검수 후 거절
    ],
    ReturnStatus.refunded: [],           # 종료 상태
    ReturnStatus.exchanged: [],          # 종료 상태
    ReturnStatus.partially_refunded: [],  # 종료 상태
}

# 종료 상태 목록
TERMINAL_STATES: Set[ReturnStatus] = {
    ReturnStatus.rejected,
    ReturnStatus.disputed,
    ReturnStatus.refunded,
    ReturnStatus.exchanged,
    ReturnStatus.partially_refunded,
}


class ReturnsAutomationWorkflow:
    """반품/교환 자동화 상태 머신.

    transition()으로 상태 전환을 검증하고 수행한다.
    기존 src/workflow/ 엔진 활용 시도 후 자체 stateful manager fallback.
    """

    def __init__(self) -> None:
        # 기존 workflow 엔진 연동 시도
        self._workflow_engine = self._load_workflow_engine()

    def _load_workflow_engine(self):
        """src/workflow/ 또는 src/workflow_engine/ 활용 시도."""
        try:
            from ..workflow.workflow_definition import WorkflowDefinition
            from ..workflow.state import State
            from ..workflow.transition import Transition
            states = [State(name=s.value, is_terminal=(s in TERMINAL_STATES)) for s in ReturnStatus]
            transitions = []
            for from_state, to_states in VALID_TRANSITIONS.items():
                for to_state in to_states:
                    transitions.append(
                        Transition(
                            from_state=from_state.value,
                            to_state=to_state.value,
                            condition=f'{from_state.value}_to_{to_state.value}',
                        )
                    )
            return WorkflowDefinition(
                name='returns_automation',
                states=states,
                transitions=transitions,
                initial_state=ReturnStatus.requested.value,
            )
        except Exception as exc:
            logger.debug("[워크플로] workflow 엔진 로드 실패 (자체 상태머신 사용): %s", exc)
            return None

    def can_transition(self, from_status: ReturnStatus, to_status: ReturnStatus) -> bool:
        """상태 전환 가능 여부 확인."""
        allowed = VALID_TRANSITIONS.get(from_status, [])
        return to_status in allowed

    def transition(
        self,
        current_status: ReturnStatus,
        new_status: ReturnStatus,
        notes: str = '',
    ) -> ReturnStatus:
        """상태 전환 수행.

        Args:
            current_status: 현재 상태
            new_status: 전환 대상 상태
            notes: 전환 메모

        Returns:
            새로운 상태

        Raises:
            ValueError: 허용되지 않은 상태 전환
        """
        if not self.can_transition(current_status, new_status):
            raise ValueError(
                f"허용되지 않은 상태 전환: {current_status.value} → {new_status.value}"
            )
        logger.info("[워크플로] 상태 전환: %s → %s (%s)", current_status.value, new_status.value, notes)
        return new_status

    def is_terminal(self, status: ReturnStatus) -> bool:
        """종료 상태 여부 확인."""
        return status in TERMINAL_STATES

    def get_allowed_transitions(self, status: ReturnStatus) -> List[ReturnStatus]:
        """허용된 다음 상태 목록 반환."""
        return list(VALID_TRANSITIONS.get(status, []))
