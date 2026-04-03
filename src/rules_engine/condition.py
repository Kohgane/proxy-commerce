"""src/rules_engine/condition.py — 조건 클래스."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


class Condition(ABC):
    @abstractmethod
    def evaluate(self, context: dict) -> bool: ...


@dataclass
class ComparisonCondition(Condition):
    field: str
    operator: str  # gt, lt, eq, ne, in, contains
    value: Any

    def evaluate(self, context: dict) -> bool:
        actual = context.get(self.field)
        if self.operator == 'gt':
            return actual > self.value
        elif self.operator == 'lt':
            return actual < self.value
        elif self.operator == 'eq':
            return actual == self.value
        elif self.operator == 'ne':
            return actual != self.value
        elif self.operator == 'in':
            return actual in self.value
        elif self.operator == 'contains':
            return self.value in str(actual)
        return False


@dataclass
class CompositeCondition(Condition):
    operator: str  # AND, OR, NOT
    conditions: list = field(default_factory=list)

    def evaluate(self, context: dict) -> bool:
        if self.operator == 'AND':
            return all(c.evaluate(context) for c in self.conditions)
        elif self.operator == 'OR':
            return any(c.evaluate(context) for c in self.conditions)
        elif self.operator == 'NOT':
            return not self.conditions[0].evaluate(context) if self.conditions else True
        return False


@dataclass
class TimeCondition(Condition):
    condition_type: str  # business_hours, weekends, specific_period
    start_hour: int = 9
    end_hour: int = 18

    def evaluate(self, context: dict) -> bool:
        import datetime
        now = datetime.datetime.now()
        if self.condition_type == 'business_hours':
            return self.start_hour <= now.hour < self.end_hour and now.weekday() < 5
        if self.condition_type == 'weekends':
            return now.weekday() >= 5
        return True
