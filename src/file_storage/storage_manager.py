"""src/file_storage/storage_manager.py — 파일 스토리지 통합 관리."""
from __future__ import annotations

from typing import List, Optional

from .file_metadata import FileMetadata
from .file_organizer import FileOrganizer
from .file_quota import FileQuota
from .file_uploader import FileUploader
from .local_storage import LocalStorage
from .storage_backend import StorageBackend


class StorageManager:
    """파일 스토리지 통합 관리자."""

    def __init__(self, backend: Optional[StorageBackend] = None) -> None:
        self._backend: StorageBackend = backend or LocalStorage()
        self._organizer = FileOrganizer()
        self._quota = FileQuota()
        self._uploader = FileUploader(self._backend)

    def upload(self, key: str, data: bytes, filename: str,
               content_type: str = "application/octet-stream",
               owner_id: str = "default") -> FileMetadata:
        """파일 업로드."""
        size = len(data)
        if not self._quota.check_quota(owner_id, size):
            raise ValueError(f"스토리지 할당량 초과: {owner_id}")
        meta = self._uploader.upload(key, data, filename, content_type)
        self._quota.add_usage(owner_id, size)
        return meta

    def download(self, key: str) -> Optional[bytes]:
        return self._backend.get(key)

    def delete(self, key: str, owner_id: str = "default") -> None:
        meta = self._backend.get_metadata(key)
        if meta:
            self._quota.subtract_usage(owner_id, meta.size)
        self._backend.delete(key)

    def list(self, prefix: str = "") -> List[FileMetadata]:
        return self._backend.list(prefix)

    def get_metadata(self, key: str) -> Optional[FileMetadata]:
        return self._backend.get_metadata(key)

    def get_quota(self, owner_id: str) -> dict:
        return self._quota.get_summary(owner_id)

    def set_quota(self, owner_id: str, max_bytes: int) -> None:
        self._quota.set_quota(owner_id, max_bytes)

    def generate_key(self, filename: str, content_type: str = "",
                     prefix: str = "") -> str:
        return self._organizer.generate_key(filename, content_type, prefix)

    def get_uploader(self) -> FileUploader:
        return self._uploader
