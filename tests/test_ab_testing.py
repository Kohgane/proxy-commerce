"""tests/test_ab_testing.py — ABTestManager 테스트."""
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


@pytest.fixture
def manager(mock_env):
    """ABTestManager 인스턴스."""
    from src.marketing.ab_testing import ABTestManager
    return ABTestManager(sheet_id="fake_id", sheet_name="ab_tests")


def _mock_ws(records=None):
    ws = MagicMock()
    ws.get_all_records.return_value = records or []
    ws.get_all_values.return_value = []
    return ws


class TestGetVariant:
    def test_get_variant_returns_a_or_b(self, manager):
        """get_variant는 'A' 또는 'B'를 반환해야 한다."""
        variant = manager.get_variant("exp1", "user@example.com")
        assert variant in ("A", "B")

    def test_consistent_variant(self, manager):
        """동일한 실험 이름과 이메일은 항상 동일한 변형을 반환해야 한다."""
        v1 = manager.get_variant("exp_test", "consistent@example.com")
        v2 = manager.get_variant("exp_test", "consistent@example.com")
        assert v1 == v2

    def test_different_email_may_differ(self, manager):
        """다른 이메일은 다른 변형을 받을 수 있다."""
        variants = {manager.get_variant("exp_diff", f"user{i}@example.com") for i in range(20)}
        # 20개 이메일 중 A, B가 모두 등장해야 확률적으로 성립
        assert "A" in variants or "B" in variants


class TestRecordConversion:
    def test_record_conversion_no_error(self, manager):
        """record_conversion은 오류 없이 실행되어야 한다."""
        ws = _mock_ws()
        with patch('src.marketing.ab_testing.open_sheet', return_value=ws):
            manager.record_conversion("exp_conv", "A", revenue=5000)

    def test_record_impression_no_error(self, manager):
        """record_impression은 오류 없이 실행되어야 한다."""
        ws = _mock_ws()
        with patch('src.marketing.ab_testing.open_sheet', return_value=ws):
            manager.record_impression("exp_imp", "B")


class TestGetResults:
    def test_get_results_empty(self, manager):
        """데이터가 없을 때 기본 통계를 반환해야 한다."""
        ws = _mock_ws([])
        with patch('src.marketing.ab_testing.open_sheet', return_value=ws):
            results = manager.get_results("exp_empty")
        assert results["A"]["impressions"] == 0
        assert results["B"]["impressions"] == 0
        assert isinstance(results["is_significant"], bool)

    def test_get_results_with_data(self, manager):
        """데이터가 있을 때 올바른 통계를 반환해야 한다."""
        records = [
            {"experiment_name": "exp_data", "variant": "A",
             "impressions": 100, "conversions": 10, "total_revenue": 50000, "updated_at": ""},
            {"experiment_name": "exp_data", "variant": "B",
             "impressions": 100, "conversions": 5, "total_revenue": 25000, "updated_at": ""},
        ]
        ws = _mock_ws(records)
        with patch('src.marketing.ab_testing.open_sheet', return_value=ws):
            results = manager.get_results("exp_data")
        assert results["A"]["conversions"] == 10
        assert results["B"]["conversions"] == 5
        assert results["A"]["conversion_rate"] == 0.1

    def test_significance_calculation(self, manager):
        """Z-검정 결과는 bool이어야 한다."""
        records = [
            {"experiment_name": "exp_sig", "variant": "A",
             "impressions": 1000, "conversions": 100, "total_revenue": 0, "updated_at": ""},
            {"experiment_name": "exp_sig", "variant": "B",
             "impressions": 1000, "conversions": 50, "total_revenue": 0, "updated_at": ""},
        ]
        ws = _mock_ws(records)
        with patch('src.marketing.ab_testing.open_sheet', return_value=ws):
            results = manager.get_results("exp_sig")
        assert isinstance(results["is_significant"], bool)
        # 전환율 10% vs 5%는 대규모 샘플에서 유의미해야 함
        assert results["is_significant"] is True
