"""src/workflow_engine/workflow_state.py — 워크플로 상태 정의."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class WorkflowState:
    """워크플로 상태."""
    name: str
    description: str = ""
    is_terminal: bool = False  # 종료 상태 여부
    timeout_seconds: Optional[int] = None
    entry_actions: List[str] = field(default_factory=list)   # 진입 시 실행 액션 이름
    exit_actions: List[str] = field(default_factory=list)    # 이탈 시 실행 액션 이름

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "is_terminal": self.is_terminal,
            "timeout_seconds": self.timeout_seconds,
            "entry_actions": self.entry_actions,
            "exit_actions": self.exit_actions,
        }
