"""src/review_analytics/review_response.py — 리뷰 응답 관리자."""
from __future__ import annotations


class ReviewResponse:
    """리뷰 응답 관리자."""

    def __init__(self) -> None:
        self._templates: list[dict] = [
            {'id': 1, 'sentiment': 'positive', 'rating_min': 4, 'rating_max': 5,
             'text': '감사합니다! 만족스러우셨다니 정말 기쁩니다. 다음에도 좋은 서비스로 보답하겠습니다.'},
            {'id': 2, 'sentiment': 'negative', 'rating_min': 1, 'rating_max': 2,
             'text': '불편함을 드려 정말 죄송합니다. 더 나은 서비스를 위해 노력하겠습니다.'},
            {'id': 3, 'sentiment': 'neutral', 'rating_min': 3, 'rating_max': 3,
             'text': '소중한 의견 감사합니다. 더 나은 경험을 위해 개선하겠습니다.'},
        ]

    def suggest(self, rating: int, sentiment: str) -> str:
        """응답 템플릿을 제안한다."""
        for tmpl in self._templates:
            if tmpl['sentiment'] == sentiment:
                return tmpl['text']
        for tmpl in self._templates:
            if tmpl['rating_min'] <= rating <= tmpl['rating_max']:
                return tmpl['text']
        return self._templates[0]['text']

    def list_templates(self) -> list:
        """템플릿 목록을 반환한다."""
        return list(self._templates)
