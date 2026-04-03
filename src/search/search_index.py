"""src/search/search_index.py — 역색인 기반 검색 인덱스."""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple


def _tokenize(text: str) -> List[str]:
    """기본 토크나이즈 (공백/구두점 분리, 소문자)."""
    return [t.lower() for t in re.split(r"[\s\W]+", text) if t]


class SearchIndex:
    """역색인(inverted index) 기반 문서 검색."""

    def __init__(self) -> None:
        self._documents: Dict[str, dict] = {}
        self._index: Dict[str, Dict[str, int]] = {}  # token -> {doc_id: freq}

    def add_document(self, doc_id: str, fields: dict) -> None:
        self._documents[doc_id] = fields
        # Remove old entries if document exists
        self._remove_from_index(doc_id)
        full_text = " ".join(str(v) for v in fields.values())
        tokens = _tokenize(full_text)
        for token in tokens:
            if token not in self._index:
                self._index[token] = {}
            self._index[token][doc_id] = self._index[token].get(doc_id, 0) + 1

    def remove_document(self, doc_id: str) -> None:
        self._documents.pop(doc_id, None)
        self._remove_from_index(doc_id)

    def _remove_from_index(self, doc_id: str) -> None:
        for token in list(self._index.keys()):
            self._index[token].pop(doc_id, None)
            if not self._index[token]:
                del self._index[token]

    def search(self, query: str, top_k: int = 10) -> List[Tuple[str, float]]:
        """(doc_id, score) 리스트를 점수 내림차순으로 반환."""
        tokens = _tokenize(query)
        scores: Dict[str, float] = {}
        for token in tokens:
            if token in self._index:
                for doc_id, freq in self._index[token].items():
                    scores[doc_id] = scores.get(doc_id, 0.0) + freq
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return ranked[:top_k]

    def get_document(self, doc_id: str) -> Optional[dict]:
        return self._documents.get(doc_id)
