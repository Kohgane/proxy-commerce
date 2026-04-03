"""src/review_analytics/sentiment_analyzer.py — 감성 분석기."""
from __future__ import annotations


class SentimentAnalyzer:
    """감성 분석기."""

    POSITIVE_KEYWORDS = ['좋아요', '좋음', '최고', '완전', '만족', '훌륭', '추천', '좋다', '빠름', '빠르고', '저렴']
    NEGATIVE_KEYWORDS = ['별로', '최악', '실망', '나쁨', '나쁘고', '불만', '불편', '싫어', '포장 나쁨']

    def __init__(self) -> None:
        self._reviews: dict[str, list] = {}

    def analyze_text(self, text: str) -> dict:
        """텍스트 감성을 분석한다."""
        pos_count = sum(1 for kw in self.POSITIVE_KEYWORDS if kw in text)
        neg_count = sum(1 for kw in self.NEGATIVE_KEYWORDS if kw in text)
        total = pos_count + neg_count
        score = (pos_count - neg_count) / max(total, 1)
        if score > 0:
            sentiment = 'positive'
        elif score < 0:
            sentiment = 'negative'
        else:
            sentiment = 'neutral'
        return {'sentiment': sentiment, 'score': score}

    def add_review(self, product_id: str, text: str) -> None:
        """리뷰 텍스트를 추가한다."""
        self._reviews.setdefault(product_id, []).append(text)

    def analyze_product(self, product_id: str) -> dict:
        """상품 전체 감성을 분석한다."""
        reviews = self._reviews.get(product_id, [])
        counts = {'positive': 0, 'negative': 0, 'neutral': 0}
        scores = []
        for text in reviews:
            result = self.analyze_text(text)
            counts[result['sentiment']] += 1
            scores.append(result['score'])
        avg_score = sum(scores) / len(scores) if scores else 0.0
        return {
            'product_id': product_id,
            'positive': counts['positive'],
            'negative': counts['negative'],
            'neutral': counts['neutral'],
            'sentiment_score': avg_score,
        }
