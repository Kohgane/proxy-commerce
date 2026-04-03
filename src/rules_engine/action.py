"""src/rules_engine/action.py — 액션 클래스."""
from __future__ import annotations

import datetime
from abc import ABC, abstractmethod
from dataclasses import dataclass


class Action(ABC):
    @abstractmethod
    def execute(self, context: dict) -> dict: ...


@dataclass
class NotifyAction(Action):
    message: str

    def execute(self, context: dict) -> dict:
        return {
            "action": "notify",
            "message": self.message,
            "executed_at": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
        }


@dataclass
class UpdateFieldAction(Action):
    field: str
    value: object

    def execute(self, context: dict) -> dict:
        return {
            "action": "update_field",
            "field": self.field,
            "value": self.value,
            "executed_at": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
        }


@dataclass
class AssignAction(Action):
    assignee: str

    def execute(self, context: dict) -> dict:
        return {
            "action": "assign",
            "assignee": self.assignee,
            "executed_at": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
        }
