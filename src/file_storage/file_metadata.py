"""src/file_storage/file_metadata.py — 파일 메타데이터."""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


@dataclass
class FileMetadata:
    """파일 메타데이터."""
    key: str
    filename: str
    content_type: str
    size: int
    checksum: str = ""
    created_at: str = field(default_factory=_now_iso)
    metadata_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tags: dict = field(default_factory=dict)

    @staticmethod
    def compute_checksum(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def to_dict(self) -> dict:
        return {
            "metadata_id": self.metadata_id,
            "key": self.key,
            "filename": self.filename,
            "content_type": self.content_type,
            "size": self.size,
            "checksum": self.checksum,
            "created_at": self.created_at,
            "tags": self.tags,
        }
