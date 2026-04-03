"""tests/test_product_comparison.py — Phase 87: 상품 비교 도구 테스트."""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.product_comparison import (
    ComparisonSet,
    ComparisonEngine,
    AttributeComparer,
    PriceComparer,
    FeatureMatrix,
    ComparisonScore,
    ComparisonHistory,
)


SAMPLE_PRODUCTS = [
    {'product_id': 'P001', 'price': 10000, 'weight': 500, 'rating': 4.5, 'category': '전자기기',
     'cost_price': 6000, 'sell_price': 10000},
    {'product_id': 'P002', 'price': 15000, 'weight': 300, 'rating': 4.2, 'category': '전자기기',
     'cost_price': 9000, 'sell_price': 15000},
    {'product_id': 'P003', 'price': 8000, 'weight': 800, 'rating': 3.8, 'category': '의류',
     'cost_price': 4000, 'sell_price': 8000},
]


class TestComparisonSet:
    def test_dataclass_fields(self):
        cs = ComparisonSet(
            comparison_id='c1',
            product_ids=['P001', 'P002'],
            user_id='user1',
        )
        assert cs.comparison_id == 'c1'
        assert len(cs.product_ids) == 2
        assert cs.created_at


class TestAttributeComparer:
    def test_compare(self):
        comparer = AttributeComparer()
        result = comparer.compare(SAMPLE_PRODUCTS[:2])
        assert 'price' in result
        assert 'P001' in result['price']
        assert result['price']['P001'] == 10000

    def test_compare_specific_attributes(self):
        comparer = AttributeComparer()
        result = comparer.compare(SAMPLE_PRODUCTS[:2], attributes=['price', 'weight'])
        assert 'price' in result
        assert 'weight' in result
        assert 'rating' not in result

    def test_compare_empty(self):
        comparer = AttributeComparer()
        result = comparer.compare([])
        assert result == {}


class TestPriceComparer:
    def test_compare(self):
        comparer = PriceComparer()
        result = comparer.compare(SAMPLE_PRODUCTS[:2])
        assert 'products' in result
        assert 'min_price' in result
        assert 'max_price' in result
        assert result['min_price'] == 10000
        assert result['max_price'] == 15000

    def test_margin_calculation(self):
        comparer = PriceComparer()
        result = comparer.compare([SAMPLE_PRODUCTS[0]])
        product = result['products'][0]
        assert product['margin_pct'] == 40.0  # (10000-6000)/10000 * 100

    def test_compare_empty(self):
        comparer = PriceComparer()
        result = comparer.compare([])
        assert result == {}


class TestFeatureMatrix:
    def test_build(self):
        matrix = FeatureMatrix()
        result = matrix.build(SAMPLE_PRODUCTS[:2])
        assert 'features' in result
        assert 'matrix' in result
        assert len(result['matrix']) == 2

    def test_build_specific_features(self):
        matrix = FeatureMatrix()
        result = matrix.build(SAMPLE_PRODUCTS[:2], features=['price', 'weight'])
        for row in result['matrix']:
            assert 'price' in row['features']
            assert 'weight' in row['features']

    def test_build_empty(self):
        matrix = FeatureMatrix()
        result = matrix.build([])
        assert result['matrix'] == []


class TestComparisonScore:
    def test_calculate(self):
        score = ComparisonScore()
        products = [
            {'product_id': 'P001', 'price': 100, 'rating': 4.5, 'stock': 50},
            {'product_id': 'P002', 'price': 200, 'rating': 4.0, 'stock': 30},
        ]
        result = score.calculate(products)
        assert len(result) == 2
        assert 'product_id' in result[0]
        assert 'score' in result[0]
        # Results should be sorted by score descending
        assert result[0]['score'] >= result[1]['score']

    def test_calculate_empty(self):
        score = ComparisonScore()
        result = score.calculate([])
        assert result == []

    def test_custom_weights(self):
        score = ComparisonScore()
        products = [{'product_id': 'P001', 'price': 100, 'rating': 5}]
        result = score.calculate(products, weights={'price': 1.0, 'rating': 0.5})
        assert result[0]['product_id'] == 'P001'


class TestComparisonHistory:
    def test_save(self):
        history = ComparisonHistory()
        cs = history.save(['P001', 'P002'], user_id='user1')
        assert cs.comparison_id
        assert cs.product_ids == ['P001', 'P002']
        assert cs.user_id == 'user1'

    def test_list_all(self):
        history = ComparisonHistory()
        history.save(['P001', 'P002'], user_id='user1')
        history.save(['P002', 'P003'], user_id='user2')
        result = history.list()
        assert len(result) == 2

    def test_list_by_user(self):
        history = ComparisonHistory()
        history.save(['P001', 'P002'], user_id='user1')
        history.save(['P002', 'P003'], user_id='user2')
        result = history.list(user_id='user1')
        assert len(result) == 1
        assert result[0].user_id == 'user1'

    def test_list_empty(self):
        history = ComparisonHistory()
        assert history.list() == []


class TestComparisonEngine:
    def test_compare(self):
        engine = ComparisonEngine()
        result = engine.compare(SAMPLE_PRODUCTS[:2], user_id='user1')
        assert 'comparison_id' in result
        assert 'attributes' in result
        assert 'prices' in result
        assert 'scores' in result

    def test_history(self):
        engine = ComparisonEngine()
        engine.compare(SAMPLE_PRODUCTS[:2], user_id='user1')
        history = engine.history('user1')
        assert len(history) == 1
        assert 'comparison_id' in history[0]

    def test_history_empty_user(self):
        engine = ComparisonEngine()
        engine.compare(SAMPLE_PRODUCTS[:2], user_id='user1')
        history = engine.history('user2')
        assert len(history) == 0
