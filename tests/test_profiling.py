"""tests/test_profiling.py — 타이머/메트릭/리소스 모니터링 테스트."""
import os
import sys
import time
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.profiling.timer import profile_time, TimingContext  # noqa: E402
from src.profiling.api_metrics import ApiMetrics, EndpointMetrics, get_metrics  # noqa: E402
from src.profiling.resource_monitor import ResourceMonitor  # noqa: E402


# ── TimingContext 테스트 ──────────────────────────────────────

class TestTimingContext:
    def test_measures_elapsed_time(self):
        with patch("src.profiling.timer._PROFILING_ENABLED", 1):
            with TimingContext("test_op") as ctx:
                time.sleep(0.01)
        assert ctx.elapsed_ms >= 5  # 최소 5ms

    def test_elapsed_ms_accessible_after_exit(self):
        with TimingContext("test") as ctx:
            pass
        assert isinstance(ctx.elapsed_ms, float)
        assert ctx.elapsed_ms >= 0

    def test_label_set_correctly(self):
        ctx = TimingContext("my_label")
        assert ctx.label == "my_label"

    def test_slow_threshold_default(self):
        ctx = TimingContext("test")
        from src.profiling.timer import _SLOW_THRESHOLD_MS
        assert ctx.slow_threshold_ms == _SLOW_THRESHOLD_MS

    def test_custom_threshold(self):
        ctx = TimingContext("test", slow_threshold_ms=100)
        assert ctx.slow_threshold_ms == 100

    def test_no_exception_on_exit_with_error(self):
        """컨텍스트 내에서 예외가 발생해도 elapsed_ms는 측정되어야 한다."""
        try:
            with TimingContext("test") as ctx:
                raise ValueError("테스트 예외")
        except ValueError:
            pass
        assert ctx.elapsed_ms >= 0

    def test_repr(self):
        with TimingContext("label_test") as ctx:
            pass
        r = repr(ctx)
        assert "label_test" in r
        assert "elapsed_ms" in r


# ── profile_time 데코레이터 테스트 ────────────────────────────

class TestProfileTimeDecorator:
    def test_function_executes_normally(self):
        @profile_time
        def add(a, b):
            return a + b

        assert add(1, 2) == 3

    def test_with_label_kwarg(self):
        @profile_time(label="custom_label")
        def multiply(a, b):
            return a * b

        assert multiply(3, 4) == 12

    def test_with_slow_threshold(self):
        @profile_time(slow_threshold_ms=1)
        def slow_fn():
            return "done"

        result = slow_fn()
        assert result == "done"

    def test_preserves_function_name(self):
        @profile_time
        def my_function():
            """독스트링"""

        assert my_function.__name__ == "my_function"

    def test_returns_value_when_profiling_disabled(self):
        with patch("src.profiling.timer._PROFILING_ENABLED", 0):
            @profile_time
            def fn():
                return 42
            assert fn() == 42


# ── EndpointMetrics 테스트 ────────────────────────────────────

class TestEndpointMetrics:
    def test_initial_state(self):
        m = EndpointMetrics()
        assert m.request_count == 0
        assert m.error_count == 0
        assert m.avg_response_ms == 0.0
        assert m.error_rate == 0.0

    def test_record_success(self):
        m = EndpointMetrics()
        m.record(100.0, is_error=False)
        assert m.request_count == 1
        assert m.error_count == 0
        assert m.avg_response_ms == 100.0

    def test_record_error(self):
        m = EndpointMetrics()
        m.record(50.0, is_error=True)
        assert m.error_count == 1
        assert m.error_rate == 1.0

    def test_avg_response_ms(self):
        m = EndpointMetrics()
        m.record(100.0)
        m.record(200.0)
        assert m.avg_response_ms == 150.0

    def test_to_dict(self):
        m = EndpointMetrics()
        m.record(100.0)
        d = m.to_dict()
        assert "request_count" in d
        assert "avg_response_ms" in d
        assert "error_rate" in d

    def test_reset(self):
        m = EndpointMetrics()
        m.record(100.0)
        m.reset()
        assert m.request_count == 0


# ── ApiMetrics 테스트 ─────────────────────────────────────────

class TestApiMetrics:
    def setup_method(self):
        """각 테스트 전 메트릭 초기화."""
        get_metrics().reset()

    def test_record_endpoint(self):
        metrics = get_metrics()
        with patch("src.profiling.api_metrics._METRICS_ENABLED", 1):
            metrics.record_endpoint("GET /health", 50.0)
        summary = metrics.get_endpoint_metrics()
        assert "GET /health" in summary

    def test_record_external(self):
        metrics = get_metrics()
        with patch("src.profiling.api_metrics._METRICS_ENABLED", 1):
            metrics.record_external("shopify", 200.0)
        ext = metrics.get_external_metrics()
        assert "shopify" in ext

    def test_get_summary(self):
        summary = get_metrics().get_summary()
        assert "uptime_seconds" in summary
        assert "endpoints" in summary
        assert "external_apis" in summary

    def test_metrics_disabled(self):
        with patch("src.profiling.api_metrics._METRICS_ENABLED", 0):
            metrics = get_metrics()
            metrics.reset()
            metrics.record_endpoint("GET /test", 100.0)
        # 비활성화 상태에서는 기록되지 않아야 함
        assert "GET /test" not in metrics.get_endpoint_metrics()

    def test_reset_clears_data(self):
        metrics = get_metrics()
        with patch("src.profiling.api_metrics._METRICS_ENABLED", 1):
            metrics.record_endpoint("GET /reset_test", 100.0)
        metrics.reset()
        assert "GET /reset_test" not in metrics.get_endpoint_metrics()

    def test_singleton_pattern(self):
        m1 = ApiMetrics()
        m2 = ApiMetrics()
        assert m1 is m2


# ── ResourceMonitor 테스트 ────────────────────────────────────

class TestResourceMonitor:
    def test_get_active_thread_count(self):
        monitor = ResourceMonitor()
        count = monitor.get_active_thread_count()
        assert isinstance(count, int)
        assert count >= 1  # 최소 메인 스레드

    def test_get_memory_usage_mb_returns_number_or_none(self):
        monitor = ResourceMonitor()
        mem = monitor.get_memory_usage_mb()
        # None이거나 양수 float
        assert mem is None or (isinstance(mem, float) and mem > 0)

    def test_get_snapshot_keys(self):
        monitor = ResourceMonitor()
        snap = monitor.get_snapshot()
        assert "memory_mb" in snap
        assert "active_threads" in snap
        assert "cache" in snap

    def test_get_cache_stats_without_cache(self):
        monitor = ResourceMonitor(cache=None)
        assert monitor.get_cache_stats() is None

    def test_get_cache_stats_with_mock_cache(self):
        class MockCache:
            max_size = 100

            def __len__(self):
                return 50

        monitor = ResourceMonitor(cache=MockCache())
        stats = monitor.get_cache_stats()
        assert stats is not None
        assert stats["size"] == 50
        assert stats["max_size"] == 100
        assert stats["usage_pct"] == 50.0

    def test_repr(self):
        monitor = ResourceMonitor()
        r = repr(monitor)
        assert "ResourceMonitor" in r
