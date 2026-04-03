"""면세 조건 관리."""
from __future__ import annotations

class TaxExemption:
    def __init__(self) -> None:
        self._exempt_categories: set[str] = set()
        self._de_minimis_limit: float = 150000  # 소액 면세 한도 (원)

    def add_exempt_category(self, category: str) -> None:
        self._exempt_categories.add(category)

    def is_exempt(self, amount: float, category: str = "") -> bool:
        if category in self._exempt_categories:
            return True
        return amount <= self._de_minimis_limit

    def set_de_minimis(self, limit: float) -> None:
        self._de_minimis_limit = limit
