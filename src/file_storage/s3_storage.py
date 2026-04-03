"""src/file_storage/s3_storage.py — AWS S3 호환 스토리지 (mock)."""
from __future__ import annotations

from typing import Dict, List, Optional

from .file_metadata import FileMetadata
from .storage_backend import StorageBackend


class S3Storage(StorageBackend):
    """AWS S3 호환 스토리지 mock."""

    def __init__(self, bucket: str = "default-bucket") -> None:
        self.bucket = bucket
        self._store: Dict[str, bytes] = {}
        self._meta: Dict[str, FileMetadata] = {}

    def put(self, key: str, data: bytes, metadata: FileMetadata) -> FileMetadata:
        metadata.checksum = FileMetadata.compute_checksum(data)
        metadata.tags["s3_bucket"] = self.bucket
        self._store[key] = data
        self._meta[key] = metadata
        return metadata

    def get(self, key: str) -> Optional[bytes]:
        return self._store.get(key)

    def delete(self, key: str) -> None:
        self._store.pop(key, None)
        self._meta.pop(key, None)

    def exists(self, key: str) -> bool:
        return key in self._store

    def list(self, prefix: str = "") -> List[FileMetadata]:
        return [m for k, m in self._meta.items() if k.startswith(prefix)]

    def get_metadata(self, key: str) -> Optional[FileMetadata]:
        return self._meta.get(key)

    def get_s3_url(self, key: str) -> str:
        return f"s3://{self.bucket}/{key}"
