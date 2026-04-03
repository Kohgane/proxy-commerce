"""src/workflow/workflow_action.py — 워크플로 액션 ABC."""
from __future__ import annotations

from abc import ABC, abstractmethod


class WorkflowAction(ABC):
    """워크플로 액션 기본 클래스."""

    @abstractmethod
    def execute(self, context: dict) -> dict:
        """액션 실행."""

    @abstractmethod
    def rollback(self, context: dict) -> None:
        """액션 롤백."""
