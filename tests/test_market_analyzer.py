"""tests/test_market_analyzer.py — 시장 분석 테스트."""
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


SAMPLE_CATALOG = [
    {'sku': 'SKU-A', 'category': 'bags', 'price_krw': 100000, 'title': 'Bag A'},
    {'sku': 'SKU-B', 'category': 'bags', 'price_krw': 80000, 'title': 'Bag B'},
    {'sku': 'SKU-C', 'category': 'shoes', 'price_krw': 200000, 'title': 'Shoe C'},
]

SAMPLE_COMP_ROWS = [
    {
        'our_sku': 'SKU-A', 'competitor_name': 'CompA',
        'competitor_price': 90000, 'competitor_currency': 'KRW',
        'price_diff_pct': 11.0,
    },
    {
        'our_sku': 'SKU-C', 'competitor_name': 'CompC',
        'competitor_price': 180000, 'competitor_currency': 'KRW',
        'price_diff_pct': 11.1,
    },
]


class TestAnalyzeCategory:
    def test_returns_dict_with_required_keys(self):
        """analyze_category는 필수 키를 포함해야 한다."""
        from src.competitor.market_analyzer import MarketAnalyzer
        analyzer = MarketAnalyzer()
        with patch.object(analyzer, '_get_catalog_rows', return_value=SAMPLE_CATALOG):
            with patch.object(analyzer, '_get_competitor_rows', return_value=SAMPLE_COMP_ROWS):
                result = analyzer.analyze_category('bags')
        assert 'avg_price' in result
        assert 'our_position' in result
        assert 'trend' in result
        assert 'sku_count' in result

    def test_unknown_category_returns_zero(self):
        """없는 카테고리는 avg_price=0을 반환해야 한다."""
        from src.competitor.market_analyzer import MarketAnalyzer
        analyzer = MarketAnalyzer()
        with patch.object(analyzer, '_get_catalog_rows', return_value=SAMPLE_CATALOG):
            with patch.object(analyzer, '_get_competitor_rows', return_value=[]):
                result = analyzer.analyze_category('nonexistent')
        assert result['avg_price'] == 0
        assert result['our_position'] == 'unknown'

    def test_position_premium(self):
        """우리 가격이 평균보다 20% 이상 높으면 premium이어야 한다."""
        from src.competitor.market_analyzer import MarketAnalyzer
        analyzer = MarketAnalyzer()
        catalog = [
            {'sku': 'SKU-X', 'category': 'luxury', 'price_krw': 500000, 'title': 'X'},
        ]
        comp_rows = [
            {'our_sku': 'SKU-X', 'competitor_price': 300000,
             'competitor_currency': 'KRW', 'price_diff_pct': 0},
        ]
        with patch.object(analyzer, '_get_catalog_rows', return_value=catalog):
            with patch.object(analyzer, '_get_competitor_rows', return_value=comp_rows):
                with patch.object(analyzer, '_convert_to_krw', side_effect=lambda p, c: float(p)):
                    result = analyzer.analyze_category('luxury')
        assert result['our_position'] == 'premium'


class TestGetPricingOpportunities:
    def test_returns_list(self):
        """get_pricing_opportunities는 리스트를 반환해야 한다."""
        from src.competitor.market_analyzer import MarketAnalyzer
        analyzer = MarketAnalyzer()
        with patch.object(analyzer, '_get_competitor_rows', return_value=SAMPLE_COMP_ROWS):
            with patch.object(analyzer, '_get_catalog_rows', return_value=SAMPLE_CATALOG):
                result = analyzer.get_pricing_opportunities()
        assert isinstance(result, list)

    def test_overpriced_has_price_decrease_type(self):
        """경쟁사보다 비싼 상품은 price_decrease 타입이어야 한다."""
        from src.competitor.market_analyzer import MarketAnalyzer
        analyzer = MarketAnalyzer()
        catalog_map = {'SKU-A': 100000}
        rows = [{'our_sku': 'SKU-A', 'competitor_name': 'CompA',
                 'price_diff_pct': 15.0, 'competitor_price': 0,
                 'competitor_currency': 'KRW'}]
        with patch.object(analyzer, '_get_competitor_rows', return_value=rows):
            with patch.object(analyzer, '_get_catalog_rows', return_value=SAMPLE_CATALOG):
                result = analyzer.get_pricing_opportunities()
        types = [r['type'] for r in result]
        assert 'price_decrease' in types


class TestDetectTrend:
    def test_stable_trend(self):
        """안정적인 가격 데이터는 stable을 반환해야 한다."""
        from src.competitor.market_analyzer import MarketAnalyzer
        analyzer = MarketAnalyzer()
        prices = [100000, 101000, 99000, 100000, 100500]
        trend = analyzer._detect_trend(prices)
        assert trend == 'stable'

    def test_rising_trend(self):
        """가격이 오르면 rising이어야 한다."""
        from src.competitor.market_analyzer import MarketAnalyzer
        analyzer = MarketAnalyzer()
        prices = [90000, 95000, 100000, 110000, 120000, 130000]
        trend = analyzer._detect_trend(prices)
        assert trend == 'rising'

    def test_falling_trend(self):
        """가격이 떨어지면 falling이어야 한다."""
        from src.competitor.market_analyzer import MarketAnalyzer
        analyzer = MarketAnalyzer()
        prices = [130000, 120000, 110000, 100000, 90000, 80000]
        trend = analyzer._detect_trend(prices)
        assert trend == 'falling'
