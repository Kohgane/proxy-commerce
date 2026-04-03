"""src/pipeline/stage.py — 파이프라인 스테이지 ABC."""
from __future__ import annotations

from abc import ABC, abstractmethod

from .stage_result import StageResult


class Stage(ABC):
    """파이프라인 스테이지 추상 기반 클래스."""

    name: str = "base_stage"

    @abstractmethod
    def process(self, context: dict) -> StageResult:
        """스테이지 실행."""

    def validate(self, context: dict) -> bool:
        """실행 전 컨텍스트 유효성 검사. True면 실행 가능."""
        return True

    def rollback(self, context: dict) -> None:
        """실패 시 롤백."""
