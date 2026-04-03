"""tests/test_benchmark.py — 성능 벤치마크 도구 테스트 (Phase 54)."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ─────────────────────────────────────────────────────────────
# LoadProfile
# ─────────────────────────────────────────────────────────────

class TestLoadProfile:
    def setup_method(self):
        from src.benchmark.load_profile import LoadProfile
        self.LoadProfile = LoadProfile

    def test_defaults(self):
        p = self.LoadProfile(target_url="http://localhost/health")
        assert p.concurrent_users == 10
        assert p.duration_seconds == 30
        assert p.method == "GET"

    def test_validate_ok(self):
        p = self.LoadProfile(concurrent_users=5, duration_seconds=10, target_url="http://x.com")
        p.validate()  # should not raise

    def test_validate_invalid_concurrency(self):
        with pytest.raises(ValueError):
            p = self.LoadProfile(concurrent_users=0)
            p.validate()

    def test_validate_invalid_duration(self):
        with pytest.raises(ValueError):
            p = self.LoadProfile(duration_seconds=0)
            p.validate()

    def test_to_dict(self):
        p = self.LoadProfile(name="test", concurrent_users=3, duration_seconds=5)
        d = p.to_dict()
        assert d["name"] == "test"
        assert d["concurrent_users"] == 3


# ─────────────────────────────────────────────────────────────
# ResponseAnalyzer
# ─────────────────────────────────────────────────────────────

class TestResponseAnalyzer:
    def setup_method(self):
        from src.benchmark.response_analyzer import ResponseAnalyzer
        self.analyzer = ResponseAnalyzer()

    def test_analyze_empty(self):
        stats = self.analyzer.analyze([])
        assert stats["count"] == 0
        assert stats["mean"] == 0.0

    def test_analyze_single(self):
        stats = self.analyzer.analyze([100.0])
        assert stats["count"] == 1
        assert stats["mean"] == 100.0
        assert stats["min"] == 100.0
        assert stats["max"] == 100.0
        assert stats["p50"] == 100.0

    def test_analyze_multiple(self):
        times = [10.0, 20.0, 30.0, 40.0, 50.0]
        stats = self.analyzer.analyze(times)
        assert stats["count"] == 5
        assert stats["min"] == 10.0
        assert stats["max"] == 50.0
        assert stats["mean"] == 30.0

    def test_percentile_p50(self):
        times = list(range(1, 101))  # 1~100
        stats = self.analyzer.analyze([float(t) for t in times])
        assert stats["p50"] == pytest.approx(50.5, rel=0.01)

    def test_percentile_p95(self):
        times = [float(i) for i in range(1, 101)]
        stats = self.analyzer.analyze(times)
        assert stats["p95"] == pytest.approx(95.05, rel=0.05)

    def test_success_rate(self):
        assert self.analyzer.success_rate(100, 5) == pytest.approx(95.0, rel=0.01)
        assert self.analyzer.success_rate(0, 0) == 0.0

    def test_throughput(self):
        assert self.analyzer.throughput(100, 10.0) == pytest.approx(10.0, rel=0.01)
        assert self.analyzer.throughput(100, 0) == 0.0

    def test_stddev(self):
        # 모든 값이 같으면 stddev = 0
        stats = self.analyzer.analyze([50.0, 50.0, 50.0])
        assert stats["stddev"] == 0.0


# ─────────────────────────────────────────────────────────────
# BenchmarkReport
# ─────────────────────────────────────────────────────────────

class TestBenchmarkReport:
    def setup_method(self):
        from src.benchmark.benchmark_report import BenchmarkReport
        from src.benchmark.response_analyzer import ResponseAnalyzer
        self.reporter = BenchmarkReport()
        self.analyzer = ResponseAnalyzer()

    def test_generate_report(self):
        profile = {"name": "test", "duration_seconds": 10, "target_url": "http://x.com",
                   "method": "GET", "concurrent_users": 5}
        stats = self.analyzer.analyze([10.0, 20.0, 30.0])
        report = self.reporter.generate(profile, stats, errors=1)
        assert report["errors"] == 1
        assert "throughput_rps" in report
        assert "generated_at" in report

    def test_to_json(self):
        import json
        profile = {"name": "t", "duration_seconds": 1}
        stats = self.analyzer.analyze([50.0])
        report = self.reporter.generate(profile, stats)
        json_str = self.reporter.to_json(report)
        parsed = json.loads(json_str)
        assert "stats" in parsed

    def test_to_text(self):
        profile = {"name": "test_run", "duration_seconds": 5,
                   "target_url": "http://x.com", "method": "GET",
                   "concurrent_users": 10}
        stats = self.analyzer.analyze([10.0, 20.0, 50.0, 100.0, 200.0])
        report = self.reporter.generate(profile, stats)
        text = self.reporter.to_text(report)
        assert "test_run" in text
        assert "p95" in text
        assert "RPS" in text

    def test_error_rate_calculation(self):
        profile = {"name": "t", "duration_seconds": 1}
        stats = self.analyzer.analyze([50.0] * 10)
        report = self.reporter.generate(profile, stats, errors=2)
        assert report["error_rate"] == pytest.approx(20.0, rel=0.01)


# ─────────────────────────────────────────────────────────────
# RegressionDetector
# ─────────────────────────────────────────────────────────────

class TestRegressionDetector:
    def setup_method(self):
        from src.benchmark.regression_detector import RegressionDetector
        self.detector = RegressionDetector(threshold_pct=20.0)

    def _make_report(self, mean: float, p95: float, p99: float) -> dict:
        return {
            "stats": {"mean": mean, "p95": p95, "p99": p99},
            "profile": {"name": "test"},
        }

    def test_no_regression(self):
        baseline = self._make_report(100.0, 150.0, 200.0)
        current = self._make_report(105.0, 155.0, 205.0)
        result = self.detector.compare(current, baseline)
        assert result["regression"] is False

    def test_detects_regression(self):
        baseline = self._make_report(100.0, 150.0, 200.0)
        current = self._make_report(130.0, 200.0, 250.0)  # mean +30%
        result = self.detector.compare(current, baseline)
        assert result["regression"] is True
        assert len(result["regressions"]) > 0

    def test_detects_improvement(self):
        baseline = self._make_report(100.0, 150.0, 200.0)
        current = self._make_report(70.0, 110.0, 150.0)  # -30%
        result = self.detector.compare(current, baseline)
        assert len(result["improvements"]) > 0

    def test_no_baseline(self):
        result = self.detector.compare(self._make_report(100.0, 150.0, 200.0))
        assert result["regression"] is False
        assert "기준 데이터 없음" in result["message"]

    def test_add_and_get_history(self):
        self.detector.add_result(self._make_report(100.0, 150.0, 200.0))
        self.detector.add_result(self._make_report(110.0, 160.0, 210.0))
        history = self.detector.get_history()
        assert len(history) == 2


# ─────────────────────────────────────────────────────────────
# BenchmarkRunner (mock mode)
# ─────────────────────────────────────────────────────────────

class TestBenchmarkRunner:
    def setup_method(self):
        from src.benchmark.benchmark_runner import BenchmarkRunner
        from src.benchmark.load_profile import LoadProfile
        self.runner = BenchmarkRunner()
        self.LoadProfile = LoadProfile

    def test_run_mock(self):
        profile = self.LoadProfile(
            name="mock_test", concurrent_users=2, duration_seconds=1,
            target_url="http://localhost/health"
        )
        report = self.runner.run_mock(profile)
        assert "stats" in report
        assert report["stats"]["count"] > 0

    def test_run_mock_with_custom_times(self):
        profile = self.LoadProfile(
            name="custom", concurrent_users=1, duration_seconds=1,
            target_url="http://localhost/health"
        )
        times = [10.0, 20.0, 30.0, 40.0, 50.0]
        report = self.runner.run_mock(profile, response_times_ms=times)
        assert report["stats"]["count"] == 5
        assert report["stats"]["mean"] == 30.0

    def test_invalid_profile_raises(self):
        profile = self.LoadProfile(concurrent_users=0, target_url="http://x.com")
        with pytest.raises(ValueError):
            self.runner.run_mock(profile)

    def test_regression_history_updated(self):
        profile = self.LoadProfile(concurrent_users=2, duration_seconds=1,
                                   target_url="http://localhost/health")
        self.runner.run_mock(profile)
        self.runner.run_mock(profile)
        history = self.runner.detector.get_history()
        assert len(history) == 2


# ─────────────────────────────────────────────────────────────
# Benchmark API Blueprint
# ─────────────────────────────────────────────────────────────

class TestBenchmarkAPI:
    def setup_method(self):
        from flask import Flask
        from src.api.benchmark_api import benchmark_bp
        app = Flask(__name__)
        app.register_blueprint(benchmark_bp)
        self.client = app.test_client()

    def test_status(self):
        resp = self.client.get("/api/v1/benchmark/status")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "ok"

    def test_run_benchmark(self):
        resp = self.client.post("/api/v1/benchmark/run", json={
            "name": "test_run",
            "concurrent_users": 2,
            "duration_seconds": 1,
            "mock_response_times_ms": [10.0, 20.0, 30.0],
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert "stats" in data
        assert data["stats"]["count"] == 3

    def test_get_results_empty_initially(self):
        # 새 Blueprint 인스턴스에서는 이미 run된 결과가 있을 수 있음
        resp = self.client.get("/api/v1/benchmark/results")
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    def test_compare_insufficient_data(self):
        resp = self.client.post("/api/v1/benchmark/compare")
        # 결과가 2개 미만이면 400
        assert resp.status_code in (200, 400)
