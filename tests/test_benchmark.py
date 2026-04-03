"""tests/test_benchmark.py — Phase 54: 벤치마크 테스트."""
import pytest
from unittest.mock import MagicMock
from src.benchmark.load_profile import LoadProfile
from src.benchmark.response_analyzer import ResponseAnalyzer
from src.benchmark.benchmark_report import BenchmarkReport
from src.benchmark.regression_detector import RegressionDetector
from src.benchmark.benchmark_runner import BenchmarkRunner


def make_profile(**kwargs):
    defaults = dict(
        concurrent_users=2,
        duration_seconds=2,
        ramp_up_seconds=1,
        target_url='http://localhost:8000/health',
    )
    defaults.update(kwargs)
    return LoadProfile(**defaults)


class TestLoadProfile:
    def test_create(self):
        p = make_profile()
        assert p.concurrent_users == 2
        assert p.method == 'GET'

    def test_to_dict(self):
        p = make_profile()
        d = p.to_dict()
        assert d['target_url'] == 'http://localhost:8000/health'
        assert 'concurrent_users' in d

    def test_custom_method(self):
        p = make_profile(method='POST', body={'key': 'val'})
        assert p.method == 'POST'
        assert p.body == {'key': 'val'}


class TestResponseAnalyzer:
    def setup_method(self):
        self.analyzer = ResponseAnalyzer()

    def test_analyze_basic(self):
        result = self.analyzer.analyze([10.0, 20.0, 30.0, 40.0, 50.0])
        assert result['count'] == 5
        assert result['min'] == 10.0
        assert result['max'] == 50.0

    def test_analyze_empty(self):
        result = self.analyzer.analyze([])
        assert result['count'] == 0
        assert result['p50'] == 0

    def test_percentiles(self):
        times = list(range(1, 101))  # 1-100
        result = self.analyzer.analyze(times)
        assert result['p50'] <= 55
        assert result['p95'] <= 100
        assert result['p99'] <= 100

    def test_mean(self):
        result = self.analyzer.analyze([10.0, 20.0, 30.0])
        assert result['mean'] == 20.0

    def test_single_value(self):
        result = self.analyzer.analyze([42.0])
        assert result['p50'] == 42.0
        assert result['mean'] == 42.0


class TestBenchmarkReport:
    def setup_method(self):
        self.report = BenchmarkReport()

    def test_generate(self):
        profile = make_profile()
        stats = {'p50': 10.0, 'p95': 20.0, 'p99': 30.0, 'mean': 15.0, 'min': 5.0, 'max': 35.0, 'count': 100}
        result = self.report.generate(profile, stats, [])
        assert 'profile' in result
        assert 'stats' in result
        assert result['error_count'] == 0

    def test_error_rate(self):
        profile = make_profile()
        stats = {'count': 90, 'p50': 10, 'p95': 20, 'mean': 15}
        result = self.report.generate(profile, stats, ['err'] * 10)
        assert result['error_rate'] == pytest.approx(0.1, abs=0.01)

    def test_summary_text(self):
        profile = make_profile()
        stats = {'p50': 10, 'p95': 20, 'p99': 30, 'mean': 15, 'count': 50}
        result = self.report.generate(profile, stats, [])
        assert 'summary_text' in result
        assert len(result['summary_text']) > 0


class TestRegressionDetector:
    def setup_method(self):
        self.detector = RegressionDetector()

    def _make_result(self, p95=100.0, mean=50.0):
        return {'stats': {'p50': 30.0, 'p95': p95, 'p99': 120.0, 'mean': mean}}

    def test_no_baseline(self):
        result = self.detector.compare('test', self._make_result())
        assert result['degraded'] is False
        assert result['reason'] == 'no baseline'

    def test_no_regression(self):
        self.detector.store_result('test', self._make_result(p95=100))
        comparison = self.detector.compare('test', self._make_result(p95=110))
        assert comparison['degraded'] is False

    def test_regression_detected(self):
        self.detector.store_result('test', self._make_result(p95=100))
        comparison = self.detector.compare('test', self._make_result(p95=130))
        assert comparison['degraded'] is True

    def test_store_and_list(self):
        self.detector.store_result('run1', self._make_result())
        self.detector.store_result('run2', self._make_result())
        results = self.detector.list_results()
        assert 'run1' in results
        assert 'run2' in results

    def test_custom_threshold(self):
        detector = RegressionDetector(threshold=0.5)
        detector.store_result('test', self._make_result(p95=100))
        comparison = detector.compare('test', self._make_result(p95=140))
        assert comparison['degraded'] is False


class TestBenchmarkRunner:
    def setup_method(self):
        self.mock_request = MagicMock(return_value=50.0)
        self.runner = BenchmarkRunner(request_func=self.mock_request)

    def test_run_returns_report(self):
        profile = make_profile(concurrent_users=2, duration_seconds=1)
        result = self.runner.run(profile)
        assert 'profile' in result
        assert 'stats' in result
        assert 'error_count' in result

    def test_run_calls_request(self):
        profile = make_profile(concurrent_users=2, duration_seconds=1)
        self.runner.run(profile)
        assert self.mock_request.call_count > 0

    def test_run_with_errors(self):
        def failing_request(url, method='GET', body=None):
            raise Exception('connection refused')
        runner = BenchmarkRunner(request_func=failing_request)
        profile = make_profile(concurrent_users=2, duration_seconds=1)
        result = runner.run(profile)
        assert result['error_count'] > 0

    def test_run_collects_response_times(self):
        profile = make_profile(concurrent_users=2, duration_seconds=1)
        result = self.runner.run(profile)
        assert result['stats']['count'] > 0
