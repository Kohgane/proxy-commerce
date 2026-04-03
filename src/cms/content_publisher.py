"""src/cms/content_publisher.py — 콘텐츠 발행/비발행/예약."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class ContentPublisher:
    """콘텐츠 발행 상태 관리."""

    def __init__(self, manager=None) -> None:
        self._manager = manager

    def publish(self, content_id: str) -> dict:
        if self._manager:
            return self._manager.update(content_id, status="published", published_at=_now_iso())
        return {"content_id": content_id, "status": "published"}

    def unpublish(self, content_id: str) -> dict:
        if self._manager:
            return self._manager.update(content_id, status="draft")
        return {"content_id": content_id, "status": "draft"}

    def schedule(self, content_id: str, publish_at: str) -> dict:
        if self._manager:
            return self._manager.update(content_id, status="scheduled", publish_at=publish_at)
        return {"content_id": content_id, "status": "scheduled", "publish_at": publish_at}
