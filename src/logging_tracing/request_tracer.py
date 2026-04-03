"""src/logging_tracing/request_tracer.py — Flask 미들웨어로 요청 추적."""
from __future__ import annotations

import time
from typing import Optional

from .structured_logger import StructuredLogger
from .trace_context import TraceContext, Span
from .log_aggregator import LogAggregator


class RequestTracer:
    """Flask middleware로 요청 시작/종료 자동 추적."""

    def __init__(self,
                 logger: Optional[StructuredLogger] = None,
                 aggregator: Optional[LogAggregator] = None) -> None:
        self.logger = logger or StructuredLogger()
        self.aggregator = aggregator or LogAggregator()
        self.ctx = TraceContext()

    def before_request(self, request) -> Span:
        """요청 시작 처리. Span 반환."""
        headers = dict(request.headers)
        span = self.ctx.from_headers(headers) or self.ctx.new_trace(
            operation=f"{request.method} {request.path}"
        )
        request._trace_span = span
        request._trace_start = time.time()

        entry = self.logger.info(
            f"요청 시작: {request.method} {request.path}",
            trace_id=span.trace_id,
            span_id=span.span_id,
            method=request.method,
            path=request.path,
        )
        self.aggregator.add(entry)
        return span

    def after_request(self, request, response, span: Optional[Span] = None) -> None:
        """요청 종료 처리."""
        if span is None:
            span = getattr(request, "_trace_span", None)
        start = getattr(request, "_trace_start", time.time())
        elapsed_ms = round((time.time() - start) * 1000, 2)

        entry = self.logger.info(
            f"요청 완료: {request.method} {request.path}",
            trace_id=span.trace_id if span else "",
            span_id=span.span_id if span else "",
            status_code=response.status_code,
            elapsed_ms=elapsed_ms,
        )
        self.aggregator.add(entry)
