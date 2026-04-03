"""src/kpi/kpi_definition.py — KPI 정의 데이터클래스."""
from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass, field


@dataclass
class KPIDefinition:
    name: str
    formula: str
    target: float
    unit: str
    period: str  # daily, weekly, monthly
    kpi_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    description: str = ''
    created_at: datetime.datetime = field(
        default_factory=lambda: datetime.datetime.now(tz=datetime.timezone.utc)
    )

    def to_dict(self) -> dict:
        return {
            'kpi_id': self.kpi_id,
            'name': self.name,
            'formula': self.formula,
            'target': self.target,
            'unit': self.unit,
            'period': self.period,
            'description': self.description,
        }
