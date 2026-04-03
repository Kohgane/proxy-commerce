"""src/search/search_suggester.py — 검색 자동완성 제안기."""
from __future__ import annotations

from typing import Dict, List


class SearchSuggester:
    """접두사 기반 검색어 제안."""

    def __init__(self) -> None:
        self._terms: Dict[str, float] = {}  # term -> weight

    def add_term(self, term: str, weight: float = 1.0) -> None:
        self._terms[term] = self._terms.get(term, 0.0) + weight

    def suggest(self, prefix: str, limit: int = 5) -> List[str]:
        """prefix로 시작하는 단어를 가중치 내림차순으로 반환."""
        prefix_lower = prefix.lower()
        matches = [
            (term, w)
            for term, w in self._terms.items()
            if term.lower().startswith(prefix_lower)
        ]
        matches.sort(key=lambda x: x[1], reverse=True)
        return [term for term, _ in matches[:limit]]
