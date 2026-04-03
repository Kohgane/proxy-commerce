"""src/workflow/transition.py — 워크플로 전환 데이터클래스."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Transition:
    from_state: str
    to_state: str
    condition: Optional[str] = None
    action: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "from_state": self.from_state,
            "to_state": self.to_state,
            "condition": self.condition,
            "action": self.action,
        }
