"""src/logging_tracing/correlation_middleware.py — 상관 미들웨어."""
import logging

logger = logging.getLogger(__name__)


class CorrelationMiddleware:
    """Flask before/after request 훅으로 trace_id 주입."""

    def init_app(self, app) -> None:
        from .trace_context import TraceContext

        @app.before_request
        def inject_trace_id():
            from flask import g, request
            ctx = TraceContext()
            trace_id = request.headers.get('X-Trace-ID') or ctx.generate_trace_id()
            ctx.set_current_trace_id(trace_id)
            g.trace_id = trace_id

        @app.after_request
        def add_trace_header(response):
            from flask import g
            trace_id = getattr(g, 'trace_id', '')
            if trace_id:
                response.headers['X-Trace-ID'] = trace_id
            return response
