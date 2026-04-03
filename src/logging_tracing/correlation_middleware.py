"""src/logging_tracing/correlation_middleware.py — Flask trace_id 주입 미들웨어."""
from __future__ import annotations

from typing import Optional

from .trace_context import TraceContext, Span
from .log_aggregator import LogAggregator
from .structured_logger import StructuredLogger


class CorrelationMiddleware:
    """Flask before_request/after_request에서 trace_id 주입."""

    def __init__(self,
                 logger: Optional[StructuredLogger] = None,
                 aggregator: Optional[LogAggregator] = None) -> None:
        self.ctx = TraceContext()
        self.logger = logger or StructuredLogger()
        self.aggregator = aggregator or LogAggregator()

    def init_app(self, app) -> None:
        """Flask 앱에 미들웨어 등록."""
        app.before_request(self._before)
        app.after_request(self._after)

    def _before(self):
        """요청 시작 시 trace_id 생성."""
        from flask import g, request
        headers = dict(request.headers)
        span = self.ctx.from_headers(headers) or self.ctx.new_trace(
            operation=f"{request.method} {request.path}"
        )
        g.trace_id = span.trace_id
        g.span_id = span.span_id
        g.trace_span = span

    def _after(self, response):
        """응답에 trace_id 헤더 추가."""
        from flask import g
        trace_id = getattr(g, "trace_id", "")
        span_id = getattr(g, "span_id", "")
        if trace_id:
            response.headers["X-Trace-Id"] = trace_id
        if span_id:
            response.headers["X-Span-Id"] = span_id
        return response
