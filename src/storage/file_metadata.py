"""src/storage/file_metadata.py — FileMetadata 데이터클래스."""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _md5(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


@dataclass
class FileMetadata:
    """파일 메타데이터."""

    name: str
    size: int
    content_type: str
    owner_id: str
    data: bytes = field(default=b"", repr=False)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    hash: str = field(default="")
    uploaded_at: str = field(default_factory=_now_iso)

    def __post_init__(self) -> None:
        if not self.hash and self.data:
            self.hash = _md5(self.data)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "size": self.size,
            "content_type": self.content_type,
            "hash": self.hash,
            "uploaded_at": self.uploaded_at,
            "owner_id": self.owner_id,
        }
