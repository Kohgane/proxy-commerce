"""src/search/autocomplete.py — Phase 48: 자동완성."""
import logging
from collections import Counter
from typing import List

logger = logging.getLogger(__name__)

MAX_POPULAR = 10


class Autocomplete:
    """접두사 매칭 자동완성, 인기 검색어 상위 10개, 최근 검색어."""

    def __init__(self):
        self._query_counts: Counter = Counter()
        self._recent: List[str] = []
        self._keywords: List[str] = []   # 인덱싱된 키워드 목록

    def index_keyword(self, keyword: str):
        """키워드 인덱스에 추가."""
        if keyword and keyword not in self._keywords:
            self._keywords.append(keyword)

    def index_keywords(self, keywords: List[str]):
        for kw in keywords:
            self.index_keyword(kw)

    def complete(self, prefix: str, limit: int = 10) -> List[str]:
        """접두사 매칭 자동완성."""
        prefix_lower = prefix.lower()
        matches = [kw for kw in self._keywords if kw.lower().startswith(prefix_lower)]
        # 인기 순으로 정렬
        matches.sort(key=lambda kw: self._query_counts.get(kw, 0), reverse=True)
        return matches[:limit]

    def record_query(self, query: str):
        """검색어 기록 (인기/최근 추적)."""
        if not query:
            return
        self._query_counts[query] += 1
        if query in self._recent:
            self._recent.remove(query)
        self._recent.insert(0, query)
        if len(self._recent) > 50:
            self._recent = self._recent[:50]
        # 자동으로 키워드 인덱싱
        self.index_keyword(query)

    def get_popular(self, top_n: int = MAX_POPULAR) -> List[str]:
        """인기 검색어 상위 N개."""
        return [kw for kw, _ in self._query_counts.most_common(top_n)]

    def get_recent(self, n: int = 10) -> List[str]:
        """최근 검색어 N개."""
        return self._recent[:n]
