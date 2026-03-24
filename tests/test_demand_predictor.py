"""tests/test_demand_predictor.py — 수요 예측 엔진 테스트."""
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestSMA:
    def test_sma_basic(self):
        """기본 SMA 계산이 올바르게 이루어져야 한다."""
        from src.forecasting.demand_predictor import _sma
        result = _sma([1, 2, 3, 4, 5], 3)
        assert result == pytest.approx([2.0, 3.0, 4.0])

    def test_sma_window_larger_than_data(self):
        """윈도우가 데이터 크기보다 크면 빈 리스트를 반환해야 한다."""
        from src.forecasting.demand_predictor import _sma
        result = _sma([1, 2], 5)
        assert result == []

    def test_sma_window_equals_data(self):
        """윈도우가 데이터 크기와 같으면 단일 평균이어야 한다."""
        from src.forecasting.demand_predictor import _sma
        result = _sma([2, 4, 6], 3)
        assert result == pytest.approx([4.0])


class TestEMA:
    def test_ema_basic(self):
        """EMA 계산이 리스트를 반환해야 한다."""
        from src.forecasting.demand_predictor import _ema
        result = _ema([1, 2, 3, 4, 5])
        assert len(result) == 5

    def test_ema_first_value(self):
        """EMA 첫 값은 원래 데이터의 첫 값과 같아야 한다."""
        from src.forecasting.demand_predictor import _ema
        values = [10, 20, 30]
        result = _ema(values)
        assert result[0] == 10

    def test_ema_empty(self):
        """빈 리스트에 대해 빈 리스트를 반환해야 한다."""
        from src.forecasting.demand_predictor import _ema
        result = _ema([])
        assert result == []

    def test_ema_recent_weighted(self):
        """EMA는 최근 값에 더 많은 가중치를 부여해야 한다."""
        from src.forecasting.demand_predictor import _ema
        # 급증 후 EMA는 단순 평균보다 높아야 함
        values = [1, 1, 1, 1, 100]
        ema = _ema(values, alpha=0.5)
        simple_avg = sum(values) / len(values)
        assert ema[-1] > simple_avg


class TestPredictDemand:
    def test_returns_dict_with_required_keys(self):
        """predict_demand는 필수 키를 포함해야 한다."""
        from src.forecasting.demand_predictor import DemandPredictor
        predictor = DemandPredictor()
        series = [2, 3, 1, 4, 2, 3, 2, 1, 3, 2] * 9  # 90일
        with patch.object(predictor, '_build_daily_series', return_value=series):
            result = predictor.predict_demand('SKU-A', days_ahead=30)
        assert 'predicted_qty' in result
        assert 'confidence' in result
        assert 'trend' in result
        assert 'avg_daily_demand' in result

    def test_insufficient_data_returns_low_confidence(self):
        """데이터 부족 시 confidence=low를 반환해야 한다."""
        from src.forecasting.demand_predictor import DemandPredictor
        predictor = DemandPredictor()
        with patch.object(predictor, '_build_daily_series', return_value=[0] * 5):
            result = predictor.predict_demand('SKU-X', days_ahead=30)
        assert result['confidence'] == 'low'

    def test_rising_trend_detected(self):
        """증가 추세 데이터에서 rising 트렌드가 감지되어야 한다."""
        from src.forecasting.demand_predictor import DemandPredictor
        predictor = DemandPredictor()
        # SMA-7 >> SMA-30: 마지막 7일이 나머지보다 훨씬 높음
        # SMA-7 last = avg of last 7 = 50, SMA-30 last = avg([1]*23 + [50]*7) ≈ 12.6
        # 50 > 12.6 * 1.1 → rising
        series = [1] * 83 + [50] * 7
        with patch.object(predictor, '_build_daily_series', return_value=series):
            result = predictor.predict_demand('SKU-A', days_ahead=30)
        assert result['trend'] == 'rising'


class TestGetSeasonalPattern:
    def test_returns_12_months(self):
        """계절성 패턴은 12개월 데이터를 반환해야 한다."""
        from src.forecasting.demand_predictor import DemandPredictor
        predictor = DemandPredictor()
        history = {'2026-01-01': 5, '2026-06-01': 10}
        with patch.object(predictor, '_get_sales_history', return_value=history):
            pattern = predictor.get_seasonal_pattern('SKU-A')
        assert len(pattern) == 12

    def test_no_history_returns_ones(self):
        """이력 없으면 모두 1.0이어야 한다."""
        from src.forecasting.demand_predictor import DemandPredictor
        predictor = DemandPredictor()
        with patch.object(predictor, '_get_sales_history', return_value={}):
            pattern = predictor.get_seasonal_pattern('SKU-X')
        assert all(v == 1.0 for v in pattern.values())
