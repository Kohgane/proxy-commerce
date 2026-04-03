"""src/file_storage/file_organizer.py — 파일 경로 관리."""
from __future__ import annotations

from datetime import datetime, timezone


class FileOrganizer:
    """파일 경로 자동 관리 (날짜별, 타입별)."""

    CONTENT_TYPE_DIRS = {
        "image/": "images",
        "video/": "videos",
        "audio/": "audio",
        "application/pdf": "documents",
        "text/": "text",
    }

    def generate_key(self, filename: str, content_type: str = "",
                     prefix: str = "") -> str:
        """파일 키 자동 생성 (날짜/타입 기반)."""
        now = datetime.now(tz=timezone.utc)
        date_path = now.strftime("%Y/%m/%d")
        type_dir = self._get_type_dir(content_type)
        parts = [p for p in [prefix, type_dir, date_path, filename] if p]
        return "/".join(parts)

    def _get_type_dir(self, content_type: str) -> str:
        for prefix, dirname in self.CONTENT_TYPE_DIRS.items():
            if content_type.startswith(prefix):
                return dirname
        return "files"

    def organize_by_date(self, keys: list) -> dict:
        """키 목록을 날짜별로 정리."""
        result: dict = {}
        for key in keys:
            parts = key.split("/")
            if len(parts) >= 3:
                date_key = "/".join(parts[:3])
            else:
                date_key = "unknown"
            result.setdefault(date_key, []).append(key)
        return result

    def organize_by_type(self, keys: list) -> dict:
        """키 목록을 타입별로 정리."""
        result: dict = {}
        for key in keys:
            parts = key.split("/")
            type_dir = parts[0] if parts else "unknown"
            result.setdefault(type_dir, []).append(key)
        return result
