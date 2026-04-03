"""src/recommendation/popularity_ranker.py — 인기도 랭커."""
from __future__ import annotations


class PopularityRanker:
    """인기도 랭커."""

    def __init__(self) -> None:
        self._stats: dict[str, dict] = {}

    def add_stats(self, product_id: str, views: int = 0, sales: int = 0, reviews: int = 0) -> None:
        """상품 통계를 추가한다."""
        self._stats[product_id] = {'views': views, 'sales': sales, 'reviews': reviews}

    def score(self, product_id: str) -> float:
        """상품 인기도 점수를 계산한다."""
        s = self._stats.get(product_id, {})
        return s.get('views', 0) * 0.1 + s.get('sales', 0) * 1.0 + s.get('reviews', 0) * 0.5

    def get_trending(self, top_n: int = 10) -> list:
        """인기 상품 목록을 반환한다."""
        scored = [
            {'product_id': pid, 'score': self.score(pid), 'name': ''}
            for pid in self._stats
        ]
        return sorted(scored, key=lambda x: -x['score'])[:top_n]
