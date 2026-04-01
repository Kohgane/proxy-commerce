"""tests/test_competitor_api.py — 경쟁사 분석 API 테스트."""
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


@pytest.fixture
def api_client(mock_env, monkeypatch):
    """competitor_bp가 등록된 Flask 테스트 클라이언트."""
    monkeypatch.delenv("DASHBOARD_API_KEY", raising=False)
    import src.order_webhook as wh
    wh.app.config['TESTING'] = True
    with wh.app.test_client() as c:
        yield c


SAMPLE_ROWS = [
    {
        'our_sku': 'SKU-A',
        'competitor_name': 'CompA',
        'competitor_url': '',
        'competitor_price': 90000,
        'competitor_currency': 'KRW',
        'last_checked': '2026-03-01T00:00:00',
        'price_diff_pct': 11.0,
    },
]


class TestListPrices:
    def test_returns_200(self, api_client):
        """GET /api/competitor/prices는 200을 반환해야 한다."""
        with patch('src.competitor.price_tracker.CompetitorPriceTracker._get_all_rows',
                   return_value=SAMPLE_ROWS):
            with patch('src.competitor.price_tracker.CompetitorPriceTracker.get_price_comparison',
                       return_value={'our_sku': 'SKU-A', 'our_price_krw': 100000,
                                     'competitors': [], 'best_competitor_price_krw': 90000}):
                resp = api_client.get('/api/competitor/prices')
        assert resp.status_code == 200

    def test_returns_comparisons_key(self, api_client):
        """comparisons 키가 포함되어야 한다."""
        with patch('src.competitor.price_tracker.CompetitorPriceTracker._get_all_rows',
                   return_value=[]):
            resp = api_client.get('/api/competitor/prices')
        data = resp.get_json()
        assert 'comparisons' in data
        assert 'count' in data


class TestGetPrice:
    def test_returns_200_for_sku(self, api_client):
        """GET /api/competitor/prices/<sku>는 200을 반환해야 한다."""
        mock_comparison = {
            'our_sku': 'SKU-A',
            'our_price_krw': 100000,
            'competitors': [],
            'best_competitor_price_krw': 0,
        }
        with patch('src.competitor.price_tracker.CompetitorPriceTracker.get_price_comparison',
                   return_value=mock_comparison):
            resp = api_client.get('/api/competitor/prices/SKU-A')
        assert resp.status_code == 200

    def test_returns_our_sku(self, api_client):
        """our_sku 필드가 반환되어야 한다."""
        mock_comparison = {
            'our_sku': 'SKU-A',
            'our_price_krw': 100000,
            'competitors': [],
            'best_competitor_price_krw': 0,
        }
        with patch('src.competitor.price_tracker.CompetitorPriceTracker.get_price_comparison',
                   return_value=mock_comparison):
            resp = api_client.get('/api/competitor/prices/SKU-A')
        data = resp.get_json()
        assert data['our_sku'] == 'SKU-A'


class TestGetOpportunities:
    def test_returns_200(self, api_client):
        """GET /api/competitor/opportunities는 200을 반환해야 한다."""
        with patch('src.competitor.market_analyzer.MarketAnalyzer.get_pricing_opportunities',
                   return_value=[]):
            resp = api_client.get('/api/competitor/opportunities')
        assert resp.status_code == 200

    def test_returns_opportunities_key(self, api_client):
        """opportunities 키가 포함되어야 한다."""
        with patch('src.competitor.market_analyzer.MarketAnalyzer.get_pricing_opportunities',
                   return_value=[]):
            resp = api_client.get('/api/competitor/opportunities')
        data = resp.get_json()
        assert 'opportunities' in data

    def test_threshold_filter_applied(self, api_client):
        """임계값 필터가 적용되어야 한다."""
        opportunities = [
            {'our_sku': 'SKU-A', 'price_diff_pct': 15.0, 'type': 'price_decrease',
             'our_price_krw': 100000, 'competitor_name': 'C', 'recommendation': ''},
            {'our_sku': 'SKU-B', 'price_diff_pct': 5.0, 'type': 'price_decrease',
             'our_price_krw': 100000, 'competitor_name': 'C', 'recommendation': ''},
        ]
        with patch('src.competitor.market_analyzer.MarketAnalyzer.get_pricing_opportunities',
                   return_value=opportunities):
            resp = api_client.get('/api/competitor/opportunities?threshold_pct=10')
        data = resp.get_json()
        assert data['count'] == 1


class TestGetAlerts:
    def test_returns_200(self, api_client):
        """GET /api/competitor/alerts는 200을 반환해야 한다."""
        with patch('src.competitor.price_alert.PriceAlert.check_price_changes',
                   return_value=[]):
            resp = api_client.get('/api/competitor/alerts')
        assert resp.status_code == 200

    def test_returns_alerts_key(self, api_client):
        """alerts 키가 포함되어야 한다."""
        with patch('src.competitor.price_alert.PriceAlert.check_price_changes',
                   return_value=[]):
            resp = api_client.get('/api/competitor/alerts')
        data = resp.get_json()
        assert 'alerts' in data
