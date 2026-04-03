"""src/search/ranker.py — TF-IDF 기반 검색 결과 랭커."""
from __future__ import annotations

import math
from typing import Dict, List, Tuple

from .search_index import SearchIndex


class Ranker:
    """TF-IDF 점수 기반 랭킹."""

    def rank(
        self,
        query_tokens: List[str],
        candidates: List[str],
        index: SearchIndex,
    ) -> List[Tuple[str, float]]:
        """(doc_id, score) 리스트를 점수 내림차순으로 반환."""
        total_docs = max(len(index._documents), 1)
        scores: Dict[str, float] = {}
        for token in query_tokens:
            postings = index._index.get(token, {})
            df = len(postings)
            if df == 0:
                continue
            idf = math.log((total_docs + 1) / (df + 1)) + 1.0
            for doc_id in candidates:
                tf = postings.get(doc_id, 0)
                if tf:
                    scores[doc_id] = scores.get(doc_id, 0.0) + tf * idf
        return sorted(scores.items(), key=lambda x: x[1], reverse=True)
