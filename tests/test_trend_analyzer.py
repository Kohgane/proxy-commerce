"""tests/test_trend_analyzer.py — 트렌드 분석 테스트."""
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestAnalyzeTrends:
    def test_returns_list(self):
        """analyze_trends는 리스트를 반환해야 한다."""
        from src.forecasting.trend_analyzer import TrendAnalyzer
        analyzer = TrendAnalyzer()
        series = [2, 3, 1, 4, 2, 3, 2, 1, 3, 2] * 6
        with patch.object(analyzer, '_get_active_skus', return_value=['SKU-A']):
            with patch.object(analyzer, '_get_daily_series', return_value=series):
                result = analyzer.analyze_trends(period_days=30)
        assert isinstance(result, list)

    def test_result_has_required_keys(self):
        """각 항목에 필수 키가 포함되어야 한다."""
        from src.forecasting.trend_analyzer import TrendAnalyzer
        analyzer = TrendAnalyzer()
        series = [2] * 60
        with patch.object(analyzer, '_get_active_skus', return_value=['SKU-A']):
            with patch.object(analyzer, '_get_daily_series', return_value=series):
                result = analyzer.analyze_trends(period_days=30)
        assert len(result) > 0
        item = result[0]
        assert 'sku' in item
        assert 'grade' in item
        assert 'trend' in item
        assert 'growth_rate_pct' in item

    def test_empty_skus_returns_empty(self):
        """SKU 없으면 빈 리스트를 반환해야 한다."""
        from src.forecasting.trend_analyzer import TrendAnalyzer
        analyzer = TrendAnalyzer()
        with patch.object(analyzer, '_get_active_skus', return_value=[]):
            result = analyzer.analyze_trends()
        assert result == []


class TestClassifyGrade:
    def test_star_grade(self):
        """성장률 높고 판매량 높으면 Star."""
        from src.forecasting.trend_analyzer import TrendAnalyzer
        analyzer = TrendAnalyzer()
        grade = analyzer._classify_grade(5.0, 20.0, [])
        assert grade == 'Star'

    def test_cash_cow_grade(self):
        """성장률 낮고 판매량 높으면 Cash Cow."""
        from src.forecasting.trend_analyzer import TrendAnalyzer
        analyzer = TrendAnalyzer()
        grade = analyzer._classify_grade(5.0, -5.0, [])
        assert grade == 'Cash Cow'

    def test_rising_grade(self):
        """성장률 높고 판매량 낮으면 Rising."""
        from src.forecasting.trend_analyzer import TrendAnalyzer
        analyzer = TrendAnalyzer()
        grade = analyzer._classify_grade(0.1, 30.0, [])
        assert grade == 'Rising'

    def test_declining_grade(self):
        """성장률 낮고 판매량 낮으면 Declining."""
        from src.forecasting.trend_analyzer import TrendAnalyzer
        analyzer = TrendAnalyzer()
        grade = analyzer._classify_grade(0.1, -15.0, [])
        assert grade == 'Declining'


class TestDetectAnomalies:
    def test_spike_detected(self):
        """이상치 급증 감지 테스트."""
        from src.forecasting.trend_analyzer import TrendAnalyzer
        analyzer = TrendAnalyzer()
        # 평균=1, std=0.5, 이상치=10 → z > 2
        series = [1] * 29 + [100]
        with patch.object(analyzer, '_get_daily_series', return_value=series):
            result = analyzer.detect_anomalies('SKU-A', period_days=30)
        assert len(result) > 0
        assert result[-1]['type'] == 'spike'

    def test_drop_detected(self):
        """이상치 급감 감지 테스트."""
        from src.forecasting.trend_analyzer import TrendAnalyzer
        analyzer = TrendAnalyzer()
        series = [100] * 29 + [1]
        with patch.object(analyzer, '_get_daily_series', return_value=series):
            result = analyzer.detect_anomalies('SKU-A', period_days=30)
        assert len(result) > 0
        assert result[-1]['type'] == 'drop'

    def test_no_anomalies_stable_data(self):
        """안정적인 데이터는 이상치가 없어야 한다."""
        from src.forecasting.trend_analyzer import TrendAnalyzer
        analyzer = TrendAnalyzer()
        series = [10] * 30
        with patch.object(analyzer, '_get_daily_series', return_value=series):
            result = analyzer.detect_anomalies('SKU-A', period_days=30)
        assert result == []

    def test_insufficient_data_returns_empty(self):
        """데이터가 부족하면 빈 리스트를 반환해야 한다."""
        from src.forecasting.trend_analyzer import TrendAnalyzer
        analyzer = TrendAnalyzer()
        with patch.object(analyzer, '_get_daily_series', return_value=[1, 2]):
            result = analyzer.detect_anomalies('SKU-A', period_days=30)
        assert result == []
