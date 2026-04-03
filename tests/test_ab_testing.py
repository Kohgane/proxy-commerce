"""tests/test_ab_testing.py — Phase 50: A/B 테스트 테스트."""
import pytest
from src.ab_testing.experiment_manager import ExperimentManager
from src.ab_testing.variant_assigner import VariantAssigner
from src.ab_testing.metrics_tracker import MetricsTracker
from src.ab_testing.statistical_analyzer import StatisticalAnalyzer
from src.ab_testing.experiment_report import ExperimentReport


class TestExperimentManager:
    def setup_method(self):
        self.mgr = ExperimentManager()

    def test_create_experiment(self):
        exp = self.mgr.create('Test Exp', ['control', 'treatment'])
        assert exp['name'] == 'Test Exp'
        assert exp['status'] == 'draft'
        assert 'id' in exp

    def test_get_experiment(self):
        exp = self.mgr.create('Exp A', ['A', 'B'])
        found = self.mgr.get(exp['id'])
        assert found is not None

    def test_get_missing(self):
        assert self.mgr.get('no-such') is None

    def test_start_experiment(self):
        exp = self.mgr.create('Exp B', ['A', 'B'])
        started = self.mgr.start(exp['id'])
        assert started['status'] == 'running'
        assert started['start_time'] is not None

    def test_stop_experiment(self):
        exp = self.mgr.create('Exp C', ['A', 'B'])
        self.mgr.start(exp['id'])
        stopped = self.mgr.stop(exp['id'])
        assert stopped['status'] == 'stopped'
        assert stopped['end_time'] is not None

    def test_start_missing(self):
        with pytest.raises(KeyError):
            self.mgr.start('bad-id')

    def test_list_experiments(self):
        self.mgr.create('E1', ['a', 'b'])
        self.mgr.create('E2', ['a', 'b'])
        experiments = self.mgr.list_experiments()
        assert len(experiments) == 2


class TestVariantAssigner:
    def setup_method(self):
        self.assigner = VariantAssigner()

    def test_assign_returns_variant(self):
        variant = self.assigner.assign('exp1', 'user1', ['control', 'treatment'])
        assert variant in ['control', 'treatment']

    def test_consistent_assignment(self):
        v1 = self.assigner.assign('exp1', 'user1', ['control', 'treatment'])
        v2 = self.assigner.assign('exp1', 'user1', ['control', 'treatment'])
        assert v1 == v2

    def test_different_users_may_differ(self):
        results = set()
        for i in range(20):
            v = self.assigner.assign('exp1', f'user{i}', ['control', 'treatment'])
            results.add(v)
        assert len(results) > 1

    def test_empty_variants(self):
        assert self.assigner.assign('exp1', 'u1', []) is None


class TestMetricsTracker:
    def setup_method(self):
        self.tracker = MetricsTracker()

    def test_track_event(self):
        self.tracker.track_event('exp1', 'control', 'impression')
        metrics = self.tracker.get_metrics('exp1')
        assert metrics['control']['impressions'] == 1

    def test_multiple_events(self):
        self.tracker.track_event('exp1', 'control', 'impression', 5)
        self.tracker.track_event('exp1', 'control', 'conversion', 2)
        metrics = self.tracker.get_metrics('exp1')
        assert metrics['control']['impressions'] == 5
        assert metrics['control']['conversions'] == 2

    def test_multiple_variants(self):
        self.tracker.track_event('exp1', 'A', 'impression')
        self.tracker.track_event('exp1', 'B', 'impression')
        metrics = self.tracker.get_metrics('exp1')
        assert 'A' in metrics
        assert 'B' in metrics

    def test_empty_metrics(self):
        assert self.tracker.get_metrics('no-exp') == {}


class TestStatisticalAnalyzer:
    def setup_method(self):
        self.analyzer = StatisticalAnalyzer()

    def test_significant_result(self):
        result = self.analyzer.z_test(100, 1000, 200, 1000)
        assert result['is_significant'] is True
        assert result['z_score'] != 0

    def test_not_significant(self):
        result = self.analyzer.z_test(100, 1000, 105, 1000)
        assert result['is_significant'] is False

    def test_zero_totals(self):
        result = self.analyzer.z_test(0, 0, 0, 0)
        assert result['p_value'] == 1.0
        assert result['is_significant'] is False

    def test_p_value_range(self):
        result = self.analyzer.z_test(50, 100, 60, 100)
        assert 0 <= result['p_value'] <= 1

    def test_symmetric(self):
        r1 = self.analyzer.z_test(100, 1000, 150, 1000)
        r2 = self.analyzer.z_test(150, 1000, 100, 1000)
        assert abs(r1['z_score']) == abs(r2['z_score'])


class TestExperimentReport:
    def setup_method(self):
        self.report = ExperimentReport()

    def test_generate_missing(self):
        result = self.report.generate('no-such-exp')
        assert 'error' in result

    def test_generate_empty_metrics(self):
        mgr = self.report._exp_mgr
        exp = mgr.create('Report Exp', ['control', 'treatment'])
        result = self.report.generate(exp['id'])
        assert result['experiment_id'] == exp['id']
        assert 'metrics' in result
