"""src/review_analytics/review_summary.py — 리뷰 요약."""
from __future__ import annotations

POSITIVE_KEYWORDS = ['좋아요', '좋음', '최고', '완전', '만족', '훌륭', '추천', '좋다', '빠름', '빠르고', '저렴']
NEGATIVE_KEYWORDS = ['별로', '최악', '실망', '나쁨', '나쁘고', '불만', '불편', '싫어', '포장 나쁨']


class ReviewSummary:
    """리뷰 요약기."""

    def keyword_frequency(self, reviews: list[str]) -> dict:
        """키워드 빈도를 계산한다."""
        freq: dict[str, int] = {}
        for review in reviews:
            for word in review.split():
                freq[word] = freq.get(word, 0) + 1
        return freq

    def extract_pros_cons(self, reviews: list[str]) -> dict:
        """장단점을 추출한다."""
        pros: list[str] = []
        cons: list[str] = []
        for review in reviews:
            if any(kw in review for kw in POSITIVE_KEYWORDS):
                pros.append(review)
            if any(kw in review for kw in NEGATIVE_KEYWORDS):
                cons.append(review)
        return {'pros': pros, 'cons': cons}
