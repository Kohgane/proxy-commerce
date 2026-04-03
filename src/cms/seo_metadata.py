"""src/cms/seo_metadata.py — SEO 메타데이터 관리."""
from __future__ import annotations

from typing import Dict, List, Optional


class SEOMetadata:
    """콘텐츠별 SEO 메타데이터."""

    def __init__(self) -> None:
        self._meta: Dict[str, dict] = {}

    def set(self, content_id: str, title: str = "", description: str = "",
            keywords: List[str] | None = None) -> dict:
        meta = {
            "content_id": content_id,
            "title": title,
            "description": description,
            "keywords": keywords or [],
        }
        self._meta[content_id] = meta
        return dict(meta)

    def get(self, content_id: str) -> Optional[dict]:
        m = self._meta.get(content_id)
        return dict(m) if m else None

    def delete(self, content_id: str) -> None:
        self._meta.pop(content_id, None)
