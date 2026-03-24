"""tests/test_forecast_api.py — 수요 예측 API 테스트."""
import os
import sys
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


@pytest.fixture
def api_client(mock_env, monkeypatch):
    """forecast_bp가 등록된 Flask 테스트 클라이언트."""
    monkeypatch.delenv("DASHBOARD_API_KEY", raising=False)
    import src.order_webhook as wh
    wh.app.config['TESTING'] = True
    with wh.app.test_client() as c:
        yield c


SAMPLE_FORECAST = {
    'sku': 'SKU-A',
    'predicted_qty': 30,
    'avg_daily_demand': 1.0,
    'confidence': 'high',
    'trend': 'stable',
    'sma_7d': 1.0,
    'sma_14d': 1.0,
    'sma_30d': 1.0,
    'ema': 1.0,
    'days_ahead': 30,
}

SAMPLE_STOCK_ITEM = {
    'sku': 'SKU-A',
    'title': 'Product A',
    'current_stock': 5,
    'avg_daily_demand': 1.0,
    'safety_stock': 10,
    'eoq': 20,
    'days_of_stock': 5.0,
    'reorder_needed': True,
    'status': 'low_stock',
    'confidence': 'high',
}


class TestGetDemand:
    def test_returns_200(self, api_client):
        """GET /api/forecast/demand/<sku>는 200을 반환해야 한다."""
        with patch('src.forecasting.demand_predictor.DemandPredictor.predict_demand',
                   return_value=SAMPLE_FORECAST):
            with patch('src.forecasting.demand_predictor.DemandPredictor.get_seasonal_pattern',
                       return_value={m: 1.0 for m in range(1, 13)}):
                resp = api_client.get('/api/forecast/demand/SKU-A')
        assert resp.status_code == 200

    def test_returns_required_keys(self, api_client):
        """수요 예측 응답에 필수 키가 있어야 한다."""
        with patch('src.forecasting.demand_predictor.DemandPredictor.predict_demand',
                   return_value=SAMPLE_FORECAST):
            with patch('src.forecasting.demand_predictor.DemandPredictor.get_seasonal_pattern',
                       return_value={}):
                resp = api_client.get('/api/forecast/demand/SKU-A')
        data = resp.get_json()
        assert 'predicted_qty' in data
        assert 'confidence' in data
        assert 'trend' in data

    def test_custom_days_ahead(self, api_client):
        """days_ahead 파라미터가 전달되어야 한다."""
        with patch('src.forecasting.demand_predictor.DemandPredictor.predict_demand',
                   return_value={**SAMPLE_FORECAST, 'days_ahead': 60}) as mock_pred:
            with patch('src.forecasting.demand_predictor.DemandPredictor.get_seasonal_pattern',
                       return_value={}):
                resp = api_client.get('/api/forecast/demand/SKU-A?days_ahead=60')
        assert resp.status_code == 200
        mock_pred.assert_called_once_with('SKU-A', days_ahead=60)


class TestGetStockoutRisk:
    def test_returns_200(self, api_client):
        """GET /api/forecast/stockout-risk는 200을 반환해야 한다."""
        with patch('src.forecasting.stock_optimizer.StockOptimizer.get_stockout_risk',
                   return_value=[SAMPLE_STOCK_ITEM]):
            resp = api_client.get('/api/forecast/stockout-risk')
        assert resp.status_code == 200

    def test_returns_at_risk_key(self, api_client):
        """at_risk 키가 포함되어야 한다."""
        with patch('src.forecasting.stock_optimizer.StockOptimizer.get_stockout_risk',
                   return_value=[]):
            resp = api_client.get('/api/forecast/stockout-risk')
        data = resp.get_json()
        assert 'at_risk' in data
        assert 'count' in data
        assert 'days_horizon' in data


class TestGetTrends:
    def test_returns_200(self, api_client):
        """GET /api/forecast/trends는 200을 반환해야 한다."""
        with patch('src.forecasting.trend_analyzer.TrendAnalyzer.analyze_trends',
                   return_value=[]):
            resp = api_client.get('/api/forecast/trends')
        assert resp.status_code == 200

    def test_returns_trends_key(self, api_client):
        """trends 키가 포함되어야 한다."""
        with patch('src.forecasting.trend_analyzer.TrendAnalyzer.analyze_trends',
                   return_value=[]):
            resp = api_client.get('/api/forecast/trends')
        data = resp.get_json()
        assert 'trends' in data

    def test_grade_filter(self, api_client):
        """grade 파라미터로 필터링되어야 한다."""
        trends = [
            {'sku': 'SKU-A', 'grade': 'Star', 'total_sales': 100,
             'avg_daily_demand': 1.0, 'growth_rate_pct': 20.0, 'trend': 'rising'},
            {'sku': 'SKU-B', 'grade': 'Declining', 'total_sales': 10,
             'avg_daily_demand': 0.1, 'growth_rate_pct': -15.0, 'trend': 'falling'},
        ]
        with patch('src.forecasting.trend_analyzer.TrendAnalyzer.analyze_trends',
                   return_value=trends):
            resp = api_client.get('/api/forecast/trends?grade=Star')
        data = resp.get_json()
        assert data['count'] == 1
        assert data['trends'][0]['grade'] == 'Star'


class TestGetOptimization:
    def test_returns_200(self, api_client):
        """GET /api/forecast/optimization는 200을 반환해야 한다."""
        with patch('src.forecasting.stock_optimizer.StockOptimizer.optimize_stock_levels',
                   return_value=[SAMPLE_STOCK_ITEM]):
            resp = api_client.get('/api/forecast/optimization')
        assert resp.status_code == 200

    def test_returns_recommendations_key(self, api_client):
        """recommendations 키가 포함되어야 한다."""
        with patch('src.forecasting.stock_optimizer.StockOptimizer.optimize_stock_levels',
                   return_value=[]):
            resp = api_client.get('/api/forecast/optimization')
        data = resp.get_json()
        assert 'recommendations' in data

    def test_reorder_only_filter(self, api_client):
        """reorder_only 파라미터로 필터링되어야 한다."""
        items = [
            {**SAMPLE_STOCK_ITEM, 'reorder_needed': True},
            {**SAMPLE_STOCK_ITEM, 'sku': 'SKU-B', 'reorder_needed': False},
        ]
        with patch('src.forecasting.stock_optimizer.StockOptimizer.optimize_stock_levels',
                   return_value=items):
            resp = api_client.get('/api/forecast/optimization?reorder_only=1')
        data = resp.get_json()
        assert data['count'] == 1
