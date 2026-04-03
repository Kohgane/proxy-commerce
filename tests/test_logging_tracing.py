"""tests/test_logging_tracing.py — 구조화된 로깅 + 분산 추적 테스트 (Phase 53)."""
from __future__ import annotations

import io
import json
import os
import sys

import pytest
from flask import Flask

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ─────────────────────────────────────────────────────────────
# StructuredLogger
# ─────────────────────────────────────────────────────────────

class TestStructuredLogger:
    def setup_method(self):
        from src.logging_tracing.structured_logger import StructuredLogger
        self.buf = io.StringIO()
        self.logger = StructuredLogger(service="test-service", output=self.buf)

    def _get_last_log(self) -> dict:
        self.buf.seek(0)
        lines = [l.strip() for l in self.buf.getvalue().splitlines() if l.strip()]
        return json.loads(lines[-1]) if lines else {}

    def test_info_log(self):
        entry = self.logger.info("Test message")
        assert entry["level"] == "INFO"
        assert entry["message"] == "Test message"
        assert entry["service"] == "test-service"

    def test_error_log(self):
        entry = self.logger.error("Error occurred", error_code=500)
        assert entry["level"] == "ERROR"

    def test_log_includes_timestamp(self):
        entry = self.logger.info("msg")
        assert "timestamp" in entry
        assert "T" in entry["timestamp"]  # ISO format

    def test_log_with_trace_id(self):
        entry = self.logger.info("traced", trace_id="abc-123", span_id="span-1")
        assert entry["trace_id"] == "abc-123"
        assert entry["span_id"] == "span-1"

    def test_log_with_extra_fields(self):
        entry = self.logger.info("with extra", user_id="u1", action="login")
        assert entry.get("user_id") == "u1"
        assert entry.get("action") == "login"

    def test_min_level_filter(self):
        from src.logging_tracing.structured_logger import StructuredLogger
        buf = io.StringIO()
        logger = StructuredLogger(service="test", output=buf, min_level="WARNING")
        result = logger.info("should be filtered")
        assert result == {}

    def test_warning_log(self):
        entry = self.logger.warning("warn msg")
        assert entry["level"] == "WARNING"

    def test_debug_log(self):
        entry = self.logger.debug("debug msg")
        assert entry["level"] == "DEBUG"

    def test_output_is_json(self):
        self.logger.info("json test")
        log = self._get_last_log()
        assert "level" in log
        assert "message" in log


# ─────────────────────────────────────────────────────────────
# TraceContext
# ─────────────────────────────────────────────────────────────

class TestTraceContext:
    def setup_method(self):
        from src.logging_tracing.trace_context import TraceContext
        self.ctx = TraceContext()

    def test_new_trace(self):
        span = self.ctx.new_trace("test-op")
        assert span.trace_id
        assert span.span_id
        assert span.parent_span_id is None

    def test_new_span(self):
        parent = self.ctx.new_trace("parent-op")
        child = self.ctx.new_span(parent, "child-op")
        assert child.trace_id == parent.trace_id
        assert child.span_id != parent.span_id
        assert child.parent_span_id == parent.span_id

    def test_from_headers_with_trace_id(self):
        headers = {"X-Trace-Id": "test-trace-123", "X-Span-Id": "parent-span"}
        span = self.ctx.from_headers(headers)
        assert span is not None
        assert span.trace_id == "test-trace-123"
        assert span.parent_span_id == "parent-span"

    def test_from_headers_without_trace_id(self):
        span = self.ctx.from_headers({})
        assert span is None

    def test_to_headers(self):
        span = self.ctx.new_trace("op")
        headers = self.ctx.to_headers(span)
        assert "X-Trace-Id" in headers
        assert "X-Span-Id" in headers

    def test_unique_trace_ids(self):
        t1 = self.ctx.new_trace()
        t2 = self.ctx.new_trace()
        assert t1.trace_id != t2.trace_id


# ─────────────────────────────────────────────────────────────
# LogAggregator
# ─────────────────────────────────────────────────────────────

class TestLogAggregator:
    def setup_method(self):
        from src.logging_tracing.log_aggregator import LogAggregator
        self.agg = LogAggregator(max_size=100)

    def test_add_and_count(self):
        self.agg.add({"level": "INFO", "message": "test", "trace_id": "t1"})
        assert self.agg.count() == 1

    def test_search_by_trace_id(self):
        self.agg.add({"level": "INFO", "message": "req1", "trace_id": "abc"})
        self.agg.add({"level": "INFO", "message": "req2", "trace_id": "xyz"})
        results = self.agg.search(trace_id="abc")
        assert len(results) == 1

    def test_search_by_level(self):
        self.agg.add({"level": "INFO", "message": "info log", "trace_id": ""})
        self.agg.add({"level": "ERROR", "message": "error log", "trace_id": ""})
        errors = self.agg.search(level="ERROR")
        assert len(errors) == 1
        assert errors[0]["level"] == "ERROR"

    def test_search_by_keyword(self):
        self.agg.add({"level": "INFO", "message": "order created", "trace_id": ""})
        self.agg.add({"level": "INFO", "message": "payment failed", "trace_id": ""})
        results = self.agg.search(keyword="order")
        assert len(results) == 1

    def test_get_by_trace(self):
        self.agg.add({"level": "INFO", "message": "start", "trace_id": "t99"})
        self.agg.add({"level": "INFO", "message": "end", "trace_id": "t99"})
        self.agg.add({"level": "INFO", "message": "other", "trace_id": "t00"})
        logs = self.agg.get_by_trace("t99")
        assert len(logs) == 2

    def test_recent(self):
        for i in range(10):
            self.agg.add({"level": "INFO", "message": f"log {i}", "trace_id": ""})
        recent = self.agg.recent(n=5)
        assert len(recent) == 5

    def test_clear(self):
        self.agg.add({"level": "INFO", "message": "test", "trace_id": ""})
        self.agg.clear()
        assert self.agg.count() == 0

    def test_max_size(self):
        agg = __import__("src.logging_tracing.log_aggregator",
                          fromlist=["LogAggregator"]).LogAggregator(max_size=5)
        for i in range(10):
            agg.add({"level": "INFO", "message": f"log {i}", "trace_id": ""})
        assert agg.count() == 5


# ─────────────────────────────────────────────────────────────
# CorrelationMiddleware
# ─────────────────────────────────────────────────────────────

class TestCorrelationMiddleware:
    def setup_method(self):
        from src.logging_tracing.correlation_middleware import CorrelationMiddleware
        self.app = Flask(__name__)
        self.mw = CorrelationMiddleware()
        self.mw.init_app(self.app)

        @self.app.get("/test")
        def test_route():
            from flask import g
            return {"trace_id": getattr(g, "trace_id", ""), "ok": True}

        self.client = self.app.test_client()

    def test_adds_trace_id_to_response_headers(self):
        resp = self.client.get("/test")
        assert resp.status_code == 200
        assert "X-Trace-Id" in resp.headers

    def test_propagates_existing_trace_id(self):
        resp = self.client.get("/test", headers={"X-Trace-Id": "custom-trace-123"})
        assert resp.headers.get("X-Trace-Id") == "custom-trace-123"

    def test_generates_trace_id_if_missing(self):
        resp = self.client.get("/test")
        trace_id = resp.headers.get("X-Trace-Id")
        assert trace_id is not None
        assert len(trace_id) > 0


# ─────────────────────────────────────────────────────────────
# Traces API Blueprint
# ─────────────────────────────────────────────────────────────

class TestTracesAPI:
    def setup_method(self):
        from src.api.traces_api import traces_bp
        app = Flask(__name__)
        app.register_blueprint(traces_bp)
        self.client = app.test_client()

    def test_status(self):
        resp = self.client.get("/api/v1/traces/status")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "ok"

    def test_search_empty(self):
        resp = self.client.get("/api/v1/traces/")
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_get_nonexistent_trace(self):
        resp = self.client.get("/api/v1/traces/no-such-trace")
        assert resp.status_code == 404

    def test_stats(self):
        resp = self.client.get("/api/v1/traces/stats")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "total_logs" in data
