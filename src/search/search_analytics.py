"""src/search/search_analytics.py — Phase 48: 검색 분석."""
import logging
from collections import Counter
from typing import List

logger = logging.getLogger(__name__)


class SearchAnalytics:
    """검색 분석 (인기 검색어, 검색 결과 없는 키워드, 클릭률 추적)."""

    def __init__(self):
        self._query_counts: Counter = Counter()
        self._no_results: Counter = Counter()
        self._clicks: Counter = Counter()       # query → click count
        self._impressions: Counter = Counter()  # query → impression count

    def record_search(self, query: str, result_count: int = 0):
        """검색 기록."""
        if not query:
            return
        self._query_counts[query] += 1
        self._impressions[query] += result_count
        if result_count == 0:
            self._no_results[query] += 1

    def record_click(self, query: str, product_id: str):
        """검색 결과 클릭 기록."""
        if query:
            self._clicks[query] += 1

    def get_popular_queries(self, top_n: int = 10) -> List[dict]:
        """인기 검색어 목록."""
        return [
            {'query': q, 'count': c}
            for q, c in self._query_counts.most_common(top_n)
        ]

    def get_no_result_queries(self, top_n: int = 10) -> List[dict]:
        """결과 없는 검색어 목록."""
        return [
            {'query': q, 'count': c}
            for q, c in self._no_results.most_common(top_n)
        ]

    def get_click_rate(self, query: str) -> float:
        """특정 검색어 클릭률 (clicks / searches)."""
        searches = self._query_counts.get(query, 0)
        if searches == 0:
            return 0.0
        clicks = self._clicks.get(query, 0)
        return clicks / searches

    def get_summary(self) -> dict:
        """전체 분석 요약."""
        total_searches = sum(self._query_counts.values())
        total_no_results = sum(self._no_results.values())
        return {
            'total_searches': total_searches,
            'unique_queries': len(self._query_counts),
            'no_result_queries': len(self._no_results),
            'no_result_rate': total_no_results / total_searches if total_searches else 0.0,
        }
