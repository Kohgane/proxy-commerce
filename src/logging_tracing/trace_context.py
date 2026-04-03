"""src/logging_tracing/trace_context.py — 요청별 trace_id/span_id 생성."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Span:
    trace_id: str
    span_id: str
    parent_span_id: Optional[str] = None
    operation: str = ""
    service: str = "proxy-commerce"


class TraceContext:
    """요청별 고유 trace_id/span_id 생성 및 전파."""

    def new_trace(self, operation: str = "", service: str = "proxy-commerce") -> Span:
        """새로운 트레이스 생성."""
        return Span(
            trace_id=str(uuid.uuid4()),
            span_id=str(uuid.uuid4()),
            operation=operation,
            service=service,
        )

    def new_span(self, parent: Span, operation: str = "") -> Span:
        """기존 트레이스에서 새 스팬 생성."""
        return Span(
            trace_id=parent.trace_id,
            span_id=str(uuid.uuid4()),
            parent_span_id=parent.span_id,
            operation=operation,
            service=parent.service,
        )

    def from_headers(self, headers: dict) -> Optional[Span]:
        """HTTP 헤더에서 트레이스 정보 파싱."""
        trace_id = headers.get("X-Trace-Id") or headers.get("x-trace-id")
        span_id = headers.get("X-Span-Id") or headers.get("x-span-id")
        if not trace_id:
            return None
        return Span(
            trace_id=trace_id,
            span_id=str(uuid.uuid4()),
            parent_span_id=span_id,
        )

    def to_headers(self, span: Span) -> dict:
        """스팬 정보를 HTTP 헤더로 변환 (전파용)."""
        return {
            "X-Trace-Id": span.trace_id,
            "X-Span-Id": span.span_id,
            **({"X-Parent-Span-Id": span.parent_span_id} if span.parent_span_id else {}),
        }
