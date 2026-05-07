from __future__ import annotations

from .store import CsFaqStore


class CsAutoReplyService:
    """키워드 기반 CS 자동응답 추천 골격."""

    def __init__(self, store: CsFaqStore | None = None) -> None:
        self._store = store or CsFaqStore()

    def suggest(self, text: str) -> list[dict]:
        query = (text or "").strip().lower()
        if not query:
            return []
        suggestions = []
        for item in self._store.list_items():
            keyword = item.keyword.casefold()
            if keyword and keyword in query:
                suggestions.append(
                    {
                        "faq_id": item.faq_id,
                        "keyword": item.keyword,
                        "answer": item.answer,
                        "approval_required": True,
                    }
                )
        return suggestions
