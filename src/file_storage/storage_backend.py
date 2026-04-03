"""src/file_storage/storage_backend.py — 스토리지 백엔드 추상 인터페이스."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from .file_metadata import FileMetadata


class StorageBackend(ABC):
    """스토리지 백엔드 추상 인터페이스."""

    @abstractmethod
    def put(self, key: str, data: bytes, metadata: FileMetadata) -> FileMetadata:
        """파일 저장."""

    @abstractmethod
    def get(self, key: str) -> Optional[bytes]:
        """파일 조회."""

    @abstractmethod
    def delete(self, key: str) -> None:
        """파일 삭제."""

    @abstractmethod
    def exists(self, key: str) -> bool:
        """파일 존재 여부."""

    @abstractmethod
    def list(self, prefix: str = "") -> List[FileMetadata]:
        """파일 목록 조회."""

    @abstractmethod
    def get_metadata(self, key: str) -> Optional[FileMetadata]:
        """파일 메타데이터 조회."""
