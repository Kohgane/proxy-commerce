"""상품 비교 데이터 모델."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class ComparisonSet:
    comparison_id: str
    product_ids: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    user_id: str = ""
