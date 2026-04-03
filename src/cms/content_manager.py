"""src/cms/content_manager.py — CMS 콘텐츠 CRUD."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class ContentManager:
    """콘텐츠 아이템 CRUD 관리."""

    def __init__(self) -> None:
        self._items: Dict[str, dict] = {}

    def create(self, title: str, body: str, content_type: str = "page",
               status: str = "draft") -> dict:
        content_id = str(uuid.uuid4())
        item = {
            "content_id": content_id,
            "title": title,
            "body": body,
            "content_type": content_type,
            "status": status,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }
        self._items[content_id] = item
        return dict(item)

    def get(self, content_id: str) -> Optional[dict]:
        item = self._items.get(content_id)
        return dict(item) if item else None

    def update(self, content_id: str, **kwargs) -> dict:
        if content_id not in self._items:
            raise KeyError(f"콘텐츠 없음: {content_id}")
        for k, v in kwargs.items():
            if k not in ("content_id", "created_at"):
                self._items[content_id][k] = v
        self._items[content_id]["updated_at"] = _now_iso()
        return dict(self._items[content_id])

    def delete(self, content_id: str) -> None:
        if content_id not in self._items:
            raise KeyError(f"콘텐츠 없음: {content_id}")
        del self._items[content_id]

    def list_all(self) -> List[dict]:
        return [dict(i) for i in self._items.values()]
