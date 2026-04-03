"""src/pipeline/stage_result.py — 파이프라인 스테이지 결과."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class StageResult:
    """스테이지 실행 결과."""

    status: str  # "success" | "failure" | "skipped"
    duration_ms: float = 0.0
    output: Any = None
    error_message: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.status == "success"

    @property
    def failed(self) -> bool:
        return self.status == "failure"

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "duration_ms": self.duration_ms,
            "output": self.output,
            "error_message": self.error_message,
        }
