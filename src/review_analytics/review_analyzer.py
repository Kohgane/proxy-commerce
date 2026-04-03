"""src/review_analytics/review_analyzer.py — 리뷰 분석기."""
from __future__ import annotations


class ReviewAnalyzer:
    """리뷰 분석기."""

    def __init__(self) -> None:
        self._reviews: dict[str, list] = {}

    def add_review(self, product_id: str, review_dict: dict) -> None:
        """리뷰를 추가한다."""
        self._reviews.setdefault(product_id, []).append(review_dict)

    def analyze(self, product_id: str) -> dict:
        """상품 리뷰를 분석한다."""
        reviews = self._reviews.get(product_id, [])
        count = len(reviews)
        if count == 0:
            return {
                'product_id': product_id,
                'review_count': 0,
                'avg_rating': 0.0,
                'positive_ratio': 0.0,
                'period_trends': [],
            }
        ratings = [r.get('rating', 0) for r in reviews]
        avg = sum(ratings) / count
        positive = sum(1 for r in ratings if r >= 4)
        return {
            'product_id': product_id,
            'review_count': count,
            'avg_rating': avg,
            'positive_ratio': positive / count,
            'period_trends': self.period_trends(product_id),
        }

    def period_trends(self, product_id: str) -> list:
        """기간별 트렌드를 반환한다."""
        reviews = self._reviews.get(product_id, [])
        trend_map: dict[str, list] = {}
        for r in reviews:
            date = r.get('date', 'unknown')
            trend_map.setdefault(date, []).append(r.get('rating', 0))
        return [
            {'date': d, 'avg_rating': sum(rs) / len(rs), 'count': len(rs)}
            for d, rs in sorted(trend_map.items())
        ]
