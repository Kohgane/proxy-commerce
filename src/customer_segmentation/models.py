"""고객 세그먼트 데이터 모델."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class Segment:
    segment_id: str
    name: str
    description: str = ""
    rules: list[dict] = field(default_factory=list)
    customer_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
