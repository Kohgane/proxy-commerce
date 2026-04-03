"""src/workflow/state.py — 워크플로 상태 데이터클래스."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class State:
    name: str
    on_enter: Optional[str] = None
    on_exit: Optional[str] = None
    is_terminal: bool = False

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "on_enter": self.on_enter,
            "on_exit": self.on_exit,
            "is_terminal": self.is_terminal,
        }
