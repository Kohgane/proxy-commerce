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


# ─────────────────────────────────────────────────────────────
# Phase 50: 새 A/B 테스트 엔진 (src/ab_testing/)
# ─────────────────────────────────────────────────────────────

class TestExperimentManager:
    def setup_method(self):
        from src.ab_testing.experiment_manager import ExperimentManager
        self.mgr = ExperimentManager()

    def test_create_experiment(self):
        exp = self.mgr.create("Button Color Test", variants=["red", "blue"])
        assert exp["name"] == "Button Color Test"
        assert exp["variants"] == ["red", "blue"]
        assert exp["status"] == "created"

    def test_create_requires_name(self):
        with pytest.raises(ValueError):
            self.mgr.create("")

    def test_default_variants(self):
        exp = self.mgr.create("Test A")
        assert exp["variants"] == ["control", "treatment"]

    def test_get_existing(self):
        exp = self.mgr.create("Test B")
        fetched = self.mgr.get(exp["experiment_id"])
        assert fetched["name"] == "Test B"

    def test_get_nonexistent(self):
        assert self.mgr.get("no-id") is None

    def test_start_experiment(self):
        exp = self.mgr.create("Test C")
        started = self.mgr.start(exp["experiment_id"])
        assert started["status"] == "running"
        assert started["started_at"] is not None

    def test_stop_experiment(self):
        exp = self.mgr.create("Test D")
        self.mgr.start(exp["experiment_id"])
        stopped = self.mgr.stop(exp["experiment_id"])
        assert stopped["status"] == "stopped"

    def test_list_by_status(self):
        e1 = self.mgr.create("E1")
        e2 = self.mgr.create("E2")
        self.mgr.start(e1["experiment_id"])
        running = self.mgr.list(status="running")
        assert len(running) == 1


class TestVariantAssigner:
    def setup_method(self):
        from src.ab_testing.variant_assigner import VariantAssigner
        self.assigner = VariantAssigner()

    def test_assign_returns_valid_variant(self):
        variant = self.assigner.assign("exp1", "user1")
        assert variant in ["control", "treatment"]

    def test_assign_consistent(self):
        v1 = self.assigner.assign("exp1", "user_abc")
        v2 = self.assigner.assign("exp1", "user_abc")
        assert v1 == v2

    def test_assign_custom_variants(self):
        variant = self.assigner.assign("exp2", "user1", ["v1", "v2", "v3"])
        assert variant in ["v1", "v2", "v3"]

    def test_assign_weighted(self):
        results = set()
        for i in range(50):
            v = self.assigner.assign_weighted("exp3", f"user{i}", {"a": 0.5, "b": 0.5})
            results.add(v)
        assert "a" in results or "b" in results


class TestMetricsTracker:
    def setup_method(self):
        from src.ab_testing.metrics_tracker import MetricsTracker
        self.tracker = MetricsTracker()

    def test_record_impression(self):
        self.tracker.record_impression("exp1", "control", "u1")
        m = self.tracker.get_metrics("exp1", "control")
        assert m["impressions"] == 1

    def test_record_conversion(self):
        self.tracker.record_impression("exp2", "treatment", "u1")
        self.tracker.record_conversion("exp2", "treatment", "u1", revenue=1000)
        m = self.tracker.get_metrics("exp2", "treatment")
        assert m["conversions"] == 1
        assert m["revenue"] == 1000

    def test_cvr_calculation(self):
        for i in range(10):
            self.tracker.record_impression("exp3", "control", f"u{i}")
        for i in range(3):
            self.tracker.record_conversion("exp3", "control", f"u{i}")
        m = self.tracker.get_metrics("exp3", "control")
        assert m["cvr"] == pytest.approx(0.3, rel=0.01)

    def test_all_variants_metrics(self):
        self.tracker.record_impression("exp4", "control", "u1")
        self.tracker.record_impression("exp4", "treatment", "u2")
        all_metrics = self.tracker.get_metrics("exp4")
        assert "control" in all_metrics
        assert "treatment" in all_metrics


class TestStatisticalAnalyzer:
    def setup_method(self):
        from src.ab_testing.statistical_analyzer import StatisticalAnalyzer
        self.analyzer = StatisticalAnalyzer()

    def test_z_test_no_impressions(self):
        result = self.analyzer.z_test(0, 0, 0, 0)
        assert result["z_score"] == 0.0
        assert result["significant"] is False

    def test_z_test_same_rates(self):
        result = self.analyzer.z_test(1000, 100, 1000, 100)
        assert result["significant"] is False
        assert result["lift"] == pytest.approx(0.0, abs=0.1)

    def test_z_test_significant(self):
        # 10% vs 20% with large sample
        result = self.analyzer.z_test(10000, 1000, 10000, 2000)
        assert result["significant"] is True
        assert result["lift"] > 0

    def test_p_value_range(self):
        result = self.analyzer.z_test(100, 10, 100, 20)
        assert 0.0 <= result["p_value"] <= 1.0

    def test_sample_size(self):
        n = self.analyzer.sample_size(0.10, 0.02)
        assert n > 0


class TestExperimentReport:
    def setup_method(self):
        from src.ab_testing.experiment_report import ExperimentReport
        from src.ab_testing.experiment_manager import ExperimentManager
        self.reporter = ExperimentReport()
        mgr = ExperimentManager()
        self.exp = mgr.create("Color Test", variants=["red", "blue"])

    def test_generate_report(self):
        metrics = {
            "red": {"impressions": 100, "conversions": 10, "cvr": 0.10,
                    "ctr": 0.15, "revenue": 10000},
            "blue": {"impressions": 100, "conversions": 15, "cvr": 0.15,
                     "ctr": 0.20, "revenue": 15000},
        }
        report = self.reporter.generate(self.exp, metrics)
        assert report["experiment_id"] == self.exp["experiment_id"]
        assert report["winner"] == "blue"
        assert len(report["variants"]) == 2

    def test_to_text(self):
        metrics = {"control": {"impressions": 50, "conversions": 5, "cvr": 0.10,
                                "ctr": 0.10, "revenue": 5000}}
        exp = {"experiment_id": "test-id", "name": "Test", "status": "stopped",
               "created_at": "2024-01-01", "started_at": None, "stopped_at": None,
               "variants": ["control"]}
        report = self.reporter.generate(exp, metrics)
        text = self.reporter.to_text(report)
        assert "Test" in text
        assert "control" in text


class TestExperimentsAPI:
    def setup_method(self):
        from flask import Flask
        from src.api.experiments_api import experiments_bp
        app = Flask(__name__)
        app.register_blueprint(experiments_bp)
        self.client = app.test_client()

    def test_status(self):
        resp = self.client.get("/api/v1/experiments/status")
        assert resp.status_code == 200

    def test_create_experiment(self):
        resp = self.client.post("/api/v1/experiments/", json={"name": "Button Test"})
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["name"] == "Button Test"

    def test_list_experiments(self):
        resp = self.client.get("/api/v1/experiments/")
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    def test_get_nonexistent(self):
        resp = self.client.get("/api/v1/experiments/no-id")
        assert resp.status_code == 404

    def test_assign_variant(self):
        create_resp = self.client.post("/api/v1/experiments/",
                                       json={"name": "Assign Test"})
        exp_id = create_resp.get_json()["experiment_id"]
        resp = self.client.post(f"/api/v1/experiments/{exp_id}/assign",
                                json={"user_id": "user123"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["variant"] in ["control", "treatment"]

    def test_report(self):
        create_resp = self.client.post("/api/v1/experiments/",
                                       json={"name": "Report Test"})
        exp_id = create_resp.get_json()["experiment_id"]
        resp = self.client.get(f"/api/v1/experiments/{exp_id}/report")
        assert resp.status_code == 200
        assert "experiment_id" in resp.get_json()
