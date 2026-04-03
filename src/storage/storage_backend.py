"""src/storage/storage_backend.py — StorageBackend ABC."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List, Optional


class StorageBackend(ABC):
    """파일 스토리지 추상 기반 클래스."""

    @abstractmethod
    def upload(self, filename: str, data: bytes, content_type: str) -> str:
        """파일을 업로드하고 file_id를 반환."""

    @abstractmethod
    def download(self, file_id: str) -> Optional[bytes]:
        """file_id로 파일 데이터를 반환."""

    @abstractmethod
    def delete(self, file_id: str) -> bool:
        """파일 삭제. 성공 여부 반환."""

    @abstractmethod
    def list_files(self, prefix: str = "") -> List[Dict]:
        """prefix로 시작하는 파일 목록 반환."""
