"""tests/test_stock_optimizer.py — 재고 최적화 테스트."""
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestCalcSafetyStock:
    def test_basic_calculation(self):
        """안전 재고 기본 계산이 올바르게 이루어져야 한다."""
        from src.forecasting.stock_optimizer import StockOptimizer
        optimizer = StockOptimizer()
        # avg_daily=2, lead_time=7, safety_factor=1.5 → ceil(2*7*1.5) = ceil(21) = 21
        result = optimizer.calc_safety_stock(2.0, lead_time_days=7, safety_factor=1.5)
        assert result == 21

    def test_zero_demand_returns_zero(self):
        """수요가 0이면 안전 재고도 0이어야 한다."""
        from src.forecasting.stock_optimizer import StockOptimizer
        optimizer = StockOptimizer()
        result = optimizer.calc_safety_stock(0.0, lead_time_days=7, safety_factor=1.5)
        assert result == 0

    def test_uses_defaults(self):
        """기본값 사용 시 환경변수 값을 사용해야 한다."""
        from src.forecasting.stock_optimizer import StockOptimizer
        optimizer = StockOptimizer()
        result = optimizer.calc_safety_stock(1.0)
        assert result > 0


class TestCalcEOQ:
    def test_basic_eoq(self):
        """EOQ 기본 계산이 올바르게 이루어져야 한다."""
        import math
        from src.forecasting.stock_optimizer import StockOptimizer
        optimizer = StockOptimizer()
        # EOQ = sqrt(2 * 100 * 50 / 2) = sqrt(5000) ≈ 70.7 → 71
        result = optimizer.calc_eoq(100, 50, 2)
        expected = math.ceil(math.sqrt(2 * 100 * 50 / 2))
        assert result == expected

    def test_zero_holding_cost_returns_one(self):
        """보관 비용이 0이면 최소 1을 반환해야 한다."""
        from src.forecasting.stock_optimizer import StockOptimizer
        optimizer = StockOptimizer()
        result = optimizer.calc_eoq(100, 50, 0)
        assert result == 1

    def test_zero_demand_returns_one(self):
        """수요가 0이면 최소 1을 반환해야 한다."""
        from src.forecasting.stock_optimizer import StockOptimizer
        optimizer = StockOptimizer()
        result = optimizer.calc_eoq(0, 50, 2)
        assert result == 1


class TestCalcDaysOfStock:
    def test_basic_days(self):
        """재고 소진일 기본 계산이 올바르게 이루어져야 한다."""
        from src.forecasting.stock_optimizer import StockOptimizer
        optimizer = StockOptimizer()
        result = optimizer.calc_days_of_stock(100, 5.0)
        assert result == pytest.approx(20.0)

    def test_zero_demand_returns_inf(self):
        """수요가 0이면 inf를 반환해야 한다."""
        from src.forecasting.stock_optimizer import StockOptimizer
        optimizer = StockOptimizer()
        result = optimizer.calc_days_of_stock(100, 0.0)
        assert result == float('inf')


class TestGetStockoutRisk:
    def test_returns_list(self):
        """get_stockout_risk는 리스트를 반환해야 한다."""
        from src.forecasting.stock_optimizer import StockOptimizer
        optimizer = StockOptimizer()
        mock_levels = [
            {'sku': 'SKU-A', 'days_of_stock': 5.0, 'current_stock': 5,
             'avg_daily_demand': 1.0, 'safety_stock': 7, 'eoq': 10,
             'reorder_needed': True, 'status': 'low_stock', 'confidence': 'high',
             'title': 'Product A'},
            {'sku': 'SKU-B', 'days_of_stock': 30.0, 'current_stock': 30,
             'avg_daily_demand': 1.0, 'safety_stock': 7, 'eoq': 10,
             'reorder_needed': False, 'status': 'ok', 'confidence': 'high',
             'title': 'Product B'},
        ]
        with patch.object(optimizer, 'optimize_stock_levels', return_value=mock_levels):
            result = optimizer.get_stockout_risk(days_horizon=14)
        assert len(result) == 1
        assert result[0]['sku'] == 'SKU-A'

    def test_sorted_by_days(self):
        """결과가 소진 예상일 오름차순으로 정렬되어야 한다."""
        from src.forecasting.stock_optimizer import StockOptimizer
        optimizer = StockOptimizer()
        mock_levels = [
            {'sku': 'SKU-B', 'days_of_stock': 10.0, 'title': 'B',
             'current_stock': 10, 'avg_daily_demand': 1.0, 'safety_stock': 7,
             'eoq': 10, 'reorder_needed': True, 'status': 'low_stock', 'confidence': 'high'},
            {'sku': 'SKU-A', 'days_of_stock': 3.0, 'title': 'A',
             'current_stock': 3, 'avg_daily_demand': 1.0, 'safety_stock': 7,
             'eoq': 10, 'reorder_needed': True, 'status': 'low_stock', 'confidence': 'high'},
        ]
        with patch.object(optimizer, 'optimize_stock_levels', return_value=mock_levels):
            result = optimizer.get_stockout_risk(days_horizon=14)
        assert result[0]['sku'] == 'SKU-A'
        assert result[1]['sku'] == 'SKU-B'
