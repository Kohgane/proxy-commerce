"""비교 이력 저장/조회."""
from __future__ import annotations
import uuid
from datetime import datetime
from .models import ComparisonSet

class ComparisonHistory:
    def __init__(self) -> None:
        self._history: list[ComparisonSet] = []

    def save(self, product_ids: list[str], user_id: str = "") -> ComparisonSet:
        cs = ComparisonSet(
            comparison_id=str(uuid.uuid4()),
            product_ids=product_ids,
            created_at=datetime.now().isoformat(),
            user_id=user_id,
        )
        self._history.append(cs)
        return cs

    def list(self, user_id: str | None = None) -> list[ComparisonSet]:
        if user_id is None:
            return list(self._history)
        return [h for h in self._history if h.user_id == user_id]
