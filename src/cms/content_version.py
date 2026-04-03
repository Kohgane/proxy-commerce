"""src/cms/content_version.py — 콘텐츠 버전 히스토리."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class ContentVersion:
    """콘텐츠 버전 관리 (스냅샷 목록)."""

    def __init__(self) -> None:
        self._versions: Dict[str, List[dict]] = {}

    def snapshot(self, content_id: str, content: dict) -> dict:
        if content_id not in self._versions:
            self._versions[content_id] = []
        version_number = len(self._versions[content_id]) + 1
        entry = {
            "version": version_number,
            "content_id": content_id,
            "snapshot": dict(content),
            "timestamp": _now_iso(),
        }
        self._versions[content_id].append(entry)
        return dict(entry)

    def get_history(self, content_id: str) -> List[dict]:
        return list(self._versions.get(content_id, []))

    def get_version(self, content_id: str, version: int) -> dict | None:
        history = self._versions.get(content_id, [])
        for entry in history:
            if entry["version"] == version:
                return dict(entry)
        return None
