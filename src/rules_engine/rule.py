"""src/rules_engine/rule.py — Rule 데이터클래스."""
from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass, field

from .condition import Condition
from .action import Action


@dataclass
class Rule:
    name: str
    conditions: list  # list of Condition
    actions: list     # list of Action
    priority: int = 0
    enabled: bool = True
    rule_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime.datetime = field(
        default_factory=lambda: datetime.datetime.now(tz=datetime.timezone.utc)
    )

    def evaluate(self, context: dict) -> bool:
        if not self.enabled:
            return False
        return all(c.evaluate(context) for c in self.conditions)

    def execute(self, context: dict) -> list:
        return [a.execute(context) for a in self.actions]

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "name": self.name,
            "priority": self.priority,
            "enabled": self.enabled,
            "conditions_count": len(self.conditions),
            "actions_count": len(self.actions),
        }
