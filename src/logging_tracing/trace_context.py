"""src/logging_tracing/trace_context.py — 추적 컨텍스트."""
import threading
import uuid
import logging

logger = logging.getLogger(__name__)

_local = threading.local()


class TraceContext:
    """스레드 로컬 추적 ID 관리."""

    def generate_trace_id(self) -> str:
        return str(uuid.uuid4())

    def generate_span_id(self) -> str:
        return uuid.uuid4().hex[:8]

    def get_current_trace_id(self) -> str:
        return getattr(_local, 'trace_id', '')

    def set_current_trace_id(self, trace_id: str) -> None:
        _local.trace_id = trace_id
