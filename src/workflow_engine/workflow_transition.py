"""src/workflow_engine/workflow_transition.py — 전환 정의."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class WorkflowTransition:
    """워크플로 상태 전환 정의."""
    from_state: str
    to_state: str
    name: str = ""
    condition: Optional[str] = None   # 조건 표현식 (간단한 키=값 형태)
    action: Optional[str] = None      # 전환 시 실행 액션 이름
    transition_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def can_transition(self, context: Dict[str, Any]) -> bool:
        """전환 조건 평가. condition이 None이면 항상 가능."""
        if self.condition is None:
            return True
        # 간단한 key=value 또는 key!=value 조건 파싱
        cond = self.condition.strip()
        if "!=" in cond:
            key, val = cond.split("!=", 1)
            return str(context.get(key.strip())) != val.strip()
        if "=" in cond:
            key, val = cond.split("=", 1)
            return str(context.get(key.strip())) == val.strip()
        # 단순 키 존재 여부
        return bool(context.get(cond))

    def to_dict(self) -> dict:
        return {
            "transition_id": self.transition_id,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "name": self.name,
            "condition": self.condition,
            "action": self.action,
        }
