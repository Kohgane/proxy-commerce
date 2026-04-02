"""src/dashboard/websocket_handler.py — SSE 기반 실시간 알림 핸들러.

Phase 25: Server-Sent Events (SSE) real-time notification handler.
Flask-SocketIO 없이 순수 SSE(generator-based)로 구현.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
from typing import Generator

logger = logging.getLogger(__name__)


class SSEHandler:
    """SSE 기반 실시간 이벤트 핸들러.

    사용법::

        handler = SSEHandler()

        # Flask 뷰에서 스트림 반환
        @app.route('/admin/events')
        def sse_stream():
            from flask import Response, stream_with_context
            return Response(
                stream_with_context(handler.get_stream()),
                mimetype='text/event-stream',
                headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
            )

        # 다른 곳에서 이벤트 발행
        handler.push_event('order_update', {'order_id': '123', 'status': 'completed'})
    """

    def __init__(self, maxsize: int = 100) -> None:
        self._subscribers: list[queue.Queue] = []
        self._lock = threading.Lock()
        self._maxsize = maxsize

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_stream(self) -> Generator[str, None, None]:
        """새 구독자를 등록하고 SSE 포맷 문자열을 yield 하는 제너레이터."""
        q: queue.Queue = queue.Queue(maxsize=self._maxsize)
        with self._lock:
            self._subscribers.append(q)
        logger.debug("SSE subscriber added (total=%d)", len(self._subscribers))
        try:
            yield ": connected\n\n"
            while True:
                try:
                    data = q.get(timeout=30)
                    if data is None:
                        break
                    yield data
                except queue.Empty:
                    yield ": keepalive\n\n"
        finally:
            with self._lock:
                try:
                    self._subscribers.remove(q)
                except ValueError:
                    pass
            logger.debug("SSE subscriber removed (total=%d)", len(self._subscribers))

    def push_event(self, event_type: str, data: object) -> None:
        """모든 구독자에게 이벤트를 발행한다.

        Args:
            event_type: SSE ``event:`` 필드 값 (예: ``"order_update"``).
            data: JSON 직렬화 가능한 페이로드.
        """
        try:
            payload = json.dumps(data, ensure_ascii=False, default=str)
        except (TypeError, ValueError) as exc:
            logger.warning("SSE push_event serialization error: %s", exc)
            payload = str(data)

        message = f"event: {event_type}\ndata: {payload}\n\n"

        dead: list[queue.Queue] = []
        with self._lock:
            subscribers = list(self._subscribers)

        for q in subscribers:
            try:
                q.put_nowait(message)
            except queue.Full:
                logger.warning("SSE queue full — dropping subscriber")
                dead.append(q)

        if dead:
            with self._lock:
                for q in dead:
                    try:
                        self._subscribers.remove(q)
                    except ValueError:
                        pass

    def close_all(self) -> None:
        """모든 구독자 스트림을 종료한다."""
        with self._lock:
            subscribers = list(self._subscribers)
        for q in subscribers:
            try:
                q.put_nowait(None)
            except queue.Full:
                pass


# 모듈 레벨 기본 인스턴스
default_sse_handler = SSEHandler()
