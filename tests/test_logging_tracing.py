"""tests/test_logging_tracing.py — Phase 53: 로깅/추적 테스트."""
import pytest
from flask import Flask
from src.logging_tracing.structured_logger import StructuredLogger
from src.logging_tracing.trace_context import TraceContext
from src.logging_tracing.request_tracer import RequestTracer
from src.logging_tracing.log_aggregator import LogAggregator
from src.logging_tracing.correlation_middleware import CorrelationMiddleware


class TestStructuredLogger:
    def setup_method(self):
        self.logger = StructuredLogger()

    def test_get_log_record(self):
        record = self.logger.get_log_record('INFO', 'test message')
        assert record['level'] == 'INFO'
        assert record['message'] == 'test message'
        assert 'timestamp' in record

    def test_log_with_trace_id(self):
        record = self.logger.get_log_record('ERROR', 'err', trace_id='trace-123')
        assert record['trace_id'] == 'trace-123'

    def test_log_with_extra(self):
        record = self.logger.get_log_record('DEBUG', 'msg', extra={'key': 'val'})
        assert record['key'] == 'val'

    def test_log_levels(self):
        for level in ('debug', 'info', 'warning', 'error'):
            record = self.logger.get_log_record(level, 'msg')
            assert record['level'] == level.upper()

    def test_log_outputs_json(self, capsys):
        self.logger.log('INFO', 'hello')
        captured = capsys.readouterr()
        import json
        parsed = json.loads(captured.err)
        assert parsed['message'] == 'hello'


class TestTraceContext:
    def setup_method(self):
        self.ctx = TraceContext()

    def test_generate_trace_id(self):
        trace_id = self.ctx.generate_trace_id()
        assert isinstance(trace_id, str)
        assert len(trace_id) == 36  # UUID format

    def test_generate_span_id(self):
        span_id = self.ctx.generate_span_id()
        assert isinstance(span_id, str)
        assert len(span_id) == 8

    def test_unique_trace_ids(self):
        ids = {self.ctx.generate_trace_id() for _ in range(10)}
        assert len(ids) == 10

    def test_set_get_trace_id(self):
        self.ctx.set_current_trace_id('my-trace')
        assert self.ctx.get_current_trace_id() == 'my-trace'

    def test_empty_trace_id(self):
        self.ctx.set_current_trace_id('')
        assert self.ctx.get_current_trace_id() == ''


class TestRequestTracer:
    def setup_method(self):
        self.tracer = RequestTracer()

    def test_start_trace(self):
        trace = self.tracer.start_trace('t1')
        assert trace['trace_id'] == 't1'
        assert trace['start_time'] is not None

    def test_end_trace(self):
        self.tracer.start_trace('t2')
        trace = self.tracer.end_trace('t2')
        assert trace['duration_ms'] is not None
        assert trace['duration_ms'] >= 0

    def test_end_missing_trace(self):
        result = self.tracer.end_trace('no-such')
        assert result == {}

    def test_trace_request_decorator(self):
        @self.tracer.trace_request
        def my_view():
            return 'response'

        result = my_view()
        assert result == 'response'


class TestLogAggregator:
    def setup_method(self):
        self.agg = LogAggregator()

    def test_add_and_get_logs(self):
        self.agg.add_log({'level': 'INFO', 'message': 'test', 'service': 'proxy-commerce'})
        logs = self.agg.get_logs()
        assert len(logs) == 1

    def test_filter_by_level(self):
        self.agg.add_log({'level': 'INFO', 'message': 'info msg'})
        self.agg.add_log({'level': 'ERROR', 'message': 'err msg'})
        errors = self.agg.get_logs(level='ERROR')
        assert len(errors) == 1

    def test_filter_by_service(self):
        self.agg.add_log({'level': 'INFO', 'message': 'msg', 'service': 'svc-a'})
        self.agg.add_log({'level': 'INFO', 'message': 'msg', 'service': 'svc-b'})
        result = self.agg.get_logs(service='svc-a')
        assert len(result) == 1

    def test_filter_by_trace_id(self):
        self.agg.add_log({'level': 'INFO', 'message': 'msg', 'trace_id': 'abc'})
        self.agg.add_log({'level': 'INFO', 'message': 'msg', 'trace_id': 'xyz'})
        result = self.agg.get_logs(trace_id='abc')
        assert len(result) == 1

    def test_clear(self):
        self.agg.add_log({'level': 'INFO', 'message': 'msg'})
        self.agg.clear()
        assert len(self.agg.get_logs()) == 0

    def test_max_logs_limit(self):
        agg = LogAggregator(max_logs=5)
        for i in range(10):
            agg.add_log({'level': 'INFO', 'message': f'msg {i}'})
        logs = agg.get_logs(limit=1000)
        assert len(logs) <= 5

    def test_limit_param(self):
        for i in range(20):
            self.agg.add_log({'level': 'INFO', 'message': f'msg {i}'})
        logs = self.agg.get_logs(limit=5)
        assert len(logs) == 5


class TestCorrelationMiddleware:
    def setup_method(self):
        self.app = Flask(__name__)
        self.middleware = CorrelationMiddleware()
        self.middleware.init_app(self.app)

        @self.app.get('/test')
        def test_view():
            from flask import g
            return g.trace_id or 'no-trace'

    def test_injects_trace_id(self):
        with self.app.test_client() as client:
            resp = client.get('/test', headers={'X-Trace-ID': 'custom-trace'})
            assert resp.data.decode() == 'custom-trace'

    def test_generates_trace_id_if_missing(self):
        with self.app.test_client() as client:
            resp = client.get('/test')
            trace_id = resp.data.decode()
            assert len(trace_id) > 0

    def test_adds_trace_header_to_response(self):
        with self.app.test_client() as client:
            resp = client.get('/test', headers={'X-Trace-ID': 'test-trace'})
            assert resp.headers.get('X-Trace-ID') == 'test-trace'
