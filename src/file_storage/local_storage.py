"""src/file_storage/local_storage.py — 로컬 스토리지 (인메모리 mock)."""
from __future__ import annotations

from typing import Dict, List, Optional

from .file_metadata import FileMetadata
from .storage_backend import StorageBackend


class LocalStorage(StorageBackend):
    """로컬 파일시스템 mock — 인메모리 dict로 구현."""

    def __init__(self) -> None:
        self._store: Dict[str, bytes] = {}
        self._meta: Dict[str, FileMetadata] = {}

    def put(self, key: str, data: bytes, metadata: FileMetadata) -> FileMetadata:
        metadata.checksum = FileMetadata.compute_checksum(data)
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
