"""src/logging_tracing/request_tracer.py — 요청 추적."""
import functools
import logging
import time
from typing import Callable

logger = logging.getLogger(__name__)


class RequestTracer:
    """Flask 라우트 핸들러 추적 데코레이터."""

    def __init__(self):
        self._traces = {}

    def start_trace(self, trace_id: str) -> dict:
        trace = {'trace_id': trace_id, 'start_time': time.time(), 'end_time': None, 'duration_ms': None}
        self._traces[trace_id] = trace
        return trace

    def end_trace(self, trace_id: str) -> dict:
        trace = self._traces.get(trace_id)
        if trace:
            trace['end_time'] = time.time()
            trace['duration_ms'] = round((trace['end_time'] - trace['start_time']) * 1000, 2)
        return trace or {}

    def trace_request(self, func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            from .trace_context import TraceContext
            ctx = TraceContext()
            trace_id = ctx.generate_trace_id()
            ctx.set_current_trace_id(trace_id)
            self.start_trace(trace_id)
            try:
                result = func(*args, **kwargs)
            finally:
                self.end_trace(trace_id)
            return result
        return wrapper
