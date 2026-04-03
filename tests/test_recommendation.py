"""tests/test_recommendation.py — Phase 83: 상품 추천 테스트."""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.recommendation import (
    RecommendationEngine,
    CollaborativeFilter,
    ContentBasedFilter,
    PopularityRanker,
    PersonalizedRecommender,
    RecommendationCache,
    ABTestRecommender,
)


class TestCollaborativeFilter:
    def test_recommend_empty(self):
        cf = CollaborativeFilter()
        result = cf.recommend('user1')
        assert result == []

    def test_user_similarity_no_common(self):
        cf = CollaborativeFilter()
        cf.add_interaction('u1', 'p1', 5.0)
        cf.add_interaction('u2', 'p2', 4.0)
        sim = cf.user_similarity('u1', 'u2')
        assert sim == 0.0

    def test_user_similarity_identical(self):
        cf = CollaborativeFilter()
        cf.add_interaction('u1', 'p1', 5.0)
        cf.add_interaction('u2', 'p1', 5.0)
        sim = cf.user_similarity('u1', 'u2')
        assert abs(sim - 1.0) < 0.01

    def test_recommend_with_data(self):
        cf = CollaborativeFilter()
        cf.add_interaction('u1', 'p1', 5.0)
        cf.add_interaction('u2', 'p1', 5.0)
        cf.add_interaction('u2', 'p2', 4.0)
        result = cf.recommend('u1')
        product_ids = [r['product_id'] for r in result]
        assert 'p2' in product_ids


class TestContentBasedFilter:
    def test_similar_empty(self):
        cbf = ContentBasedFilter()
        assert cbf.similar('p1') == []

    def test_similar_same_category(self):
        cbf = ContentBasedFilter()
        cbf.add_product('p1', category='electronics', tags=['phone'], price=500)
        cbf.add_product('p2', category='electronics', tags=['tablet'], price=300)
        cbf.add_product('p3', category='clothing', tags=['shirt'], price=50)
        results = cbf.similar('p1')
        product_ids = [r['product_id'] for r in results]
        assert 'p2' in product_ids
        # p2 should score higher than p3
        p2_score = next(r['score'] for r in results if r['product_id'] == 'p2')
        p3_score = next(r['score'] for r in results if r['product_id'] == 'p3')
        assert p2_score > p3_score

    def test_similar_common_tags(self):
        cbf = ContentBasedFilter()
        cbf.add_product('p1', category='electronics', tags=['phone', 'android'], price=500)
        cbf.add_product('p2', category='electronics', tags=['phone', 'android'], price=400)
        results = cbf.similar('p1')
        assert len(results) == 1
        assert results[0]['score'] > 1.0


class TestPopularityRanker:
    def test_empty(self):
        ranker = PopularityRanker()
        result = ranker.get_trending()
        assert result == []

    def test_score(self):
        ranker = PopularityRanker()
        ranker.add_stats('p1', views=100, sales=10, reviews=5)
        score = ranker.score('p1')
        assert score == 100 * 0.1 + 10 * 1.0 + 5 * 0.5

    def test_trending_sorted(self):
        ranker = PopularityRanker()
        ranker.add_stats('p1', views=10, sales=1, reviews=0)
        ranker.add_stats('p2', views=100, sales=10, reviews=5)
        result = ranker.get_trending()
        assert result[0]['product_id'] == 'p2'


class TestPersonalizedRecommender:
    def test_with_history(self):
        rec = PersonalizedRecommender()
        result = rec.recommend('u1', purchase_history=['p1', 'p2'])
        assert len(result) >= 2
        product_ids = [r['product_id'] for r in result]
        assert 'rec-p1' in product_ids

    def test_default_recommendations(self):
        rec = PersonalizedRecommender()
        result = rec.recommend('u1')
        assert len(result) > 0
        assert result[0]['source'] == 'default'

    def test_top_n_limit(self):
        rec = PersonalizedRecommender()
        result = rec.recommend('u1', purchase_history=[f'p{i}' for i in range(20)], top_n=5)
        assert len(result) <= 5


class TestRecommendationCache:
    def test_set_and_get(self):
        cache = RecommendationCache(ttl=300)
        cache.set('key1', [{'product_id': 'p1'}])
        result = cache.get('key1')
        assert result is not None
        assert result[0]['product_id'] == 'p1'

    def test_get_missing(self):
        cache = RecommendationCache()
        assert cache.get('nonexistent') is None

    def test_invalidate(self):
        cache = RecommendationCache()
        cache.set('key1', [{'product_id': 'p1'}])
        cache.invalidate('key1')
        assert cache.get('key1') is None

    def test_expired(self):
        cache = RecommendationCache(ttl=-1)
        cache.set('key1', [{'product_id': 'p1'}])
        assert cache.get('key1') is None


class TestABTestRecommender:
    def test_assign_variant(self):
        ab = ABTestRecommender()
        variant = ab.assign_variant('u1', 'test1')
        assert variant in ('A', 'B')

    def test_consistent_assignment(self):
        ab = ABTestRecommender()
        v1 = ab.assign_variant('u1', 'test1')
        v2 = ab.assign_variant('u1', 'test1')
        assert v1 == v2

    def test_record_result(self):
        ab = ABTestRecommender()
        ab.record_result('u1', 'test1', clicked=True)
        stats = ab.get_stats('test1')
        assert len(stats) > 0


class TestRecommendationEngine:
    def test_recommend(self):
        engine = RecommendationEngine()
        result = engine.recommend('u1')
        assert isinstance(result, list)

    def test_similar(self):
        engine = RecommendationEngine()
        result = engine.similar('p1')
        assert isinstance(result, list)

    def test_trending(self):
        engine = RecommendationEngine()
        result = engine.trending()
        assert isinstance(result, list)

    def test_personalized(self):
        engine = RecommendationEngine()
        result = engine.personalized('u1')
        assert isinstance(result, list)
