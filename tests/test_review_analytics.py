"""tests/test_review_analytics.py — Phase 79: 리뷰 분석 & 감성 분석 테스트."""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.review_analytics import (
    ReviewAnalyzer,
    SentimentAnalyzer,
    ReviewSummary,
    ReviewFlagManager,
    ReviewResponse,
)


class TestReviewAnalyzer:
    def test_analyze_empty(self):
        analyzer = ReviewAnalyzer()
        result = analyzer.analyze('p001')
        assert result['review_count'] == 0
        assert result['avg_rating'] == 0.0
        assert result['positive_ratio'] == 0.0

    def test_analyze_with_reviews(self):
        analyzer = ReviewAnalyzer()
        analyzer.add_review('p001', {'rating': 5, 'date': '2024-01-01'})
        analyzer.add_review('p001', {'rating': 4, 'date': '2024-01-01'})
        analyzer.add_review('p001', {'rating': 2, 'date': '2024-01-02'})
        result = analyzer.analyze('p001')
        assert result['review_count'] == 3
        assert abs(result['avg_rating'] - 11/3) < 0.01
        assert abs(result['positive_ratio'] - 2/3) < 0.01

    def test_period_trends(self):
        analyzer = ReviewAnalyzer()
        analyzer.add_review('p001', {'rating': 5, 'date': '2024-01-01'})
        analyzer.add_review('p001', {'rating': 3, 'date': '2024-01-02'})
        trends = analyzer.period_trends('p001')
        assert len(trends) == 2
        assert trends[0]['date'] == '2024-01-01'
        assert trends[0]['count'] == 1


class TestSentimentAnalyzer:
    def test_analyze_positive(self):
        sa = SentimentAnalyzer()
        result = sa.analyze_text('정말 좋아요 최고 만족')
        assert result['sentiment'] == 'positive'
        assert result['score'] > 0

    def test_analyze_negative(self):
        sa = SentimentAnalyzer()
        result = sa.analyze_text('별로 최악 실망')
        assert result['sentiment'] == 'negative'
        assert result['score'] < 0

    def test_analyze_empty(self):
        sa = SentimentAnalyzer()
        result = sa.analyze_text('')
        assert result['sentiment'] == 'neutral'

    def test_analyze_product(self):
        sa = SentimentAnalyzer()
        sa.add_review('p001', '좋아요 최고')
        sa.add_review('p001', '별로 최악')
        result = sa.analyze_product('p001')
        assert result['product_id'] == 'p001'
        assert result['positive'] >= 1
        assert result['negative'] >= 1


class TestReviewSummary:
    def test_keyword_frequency(self):
        sm = ReviewSummary()
        reviews = ['좋아요 상품', '좋아요 배송']
        freq = sm.keyword_frequency(reviews)
        assert freq.get('좋아요') == 2

    def test_extract_pros_cons(self):
        sm = ReviewSummary()
        reviews = ['좋아요 정말 만족', '별로 실망']
        result = sm.extract_pros_cons(reviews)
        assert len(result['pros']) >= 1
        assert len(result['cons']) >= 1


class TestReviewFlagManager:
    def test_flag_and_list(self):
        mgr = ReviewFlagManager()
        mgr.flag('r001', 'spam', 'user1')
        flagged = mgr.list_flagged()
        assert len(flagged) == 1
        assert flagged[0]['review_id'] == 'r001'
        assert flagged[0]['status'] == 'pending'

    def test_resolve(self):
        mgr = ReviewFlagManager()
        mgr.flag('r001', 'spam', 'user1')
        result = mgr.resolve('r001', 'dismissed')
        assert result['status'] == 'dismissed'


class TestReviewResponse:
    def test_suggest_positive(self):
        resp = ReviewResponse()
        text = resp.suggest(rating=5, sentiment='positive')
        assert len(text) > 0

    def test_suggest_negative(self):
        resp = ReviewResponse()
        text = resp.suggest(rating=1, sentiment='negative')
        assert len(text) > 0

    def test_list_templates(self):
        resp = ReviewResponse()
        templates = resp.list_templates()
        assert len(templates) >= 3
