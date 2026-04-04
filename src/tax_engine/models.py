"""세금 데이터 모델."""
from __future__ import annotations
from dataclasses import dataclass

@dataclass
class TaxRate:
    country: str
    region: str
    category: str
    rate: float
    name: str
    is_inclusive: bool = False
