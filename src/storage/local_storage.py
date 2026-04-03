"""src/storage/local_storage.py — 인메모리 로컬 스토리지 구현."""
from __future__ import annotations

import uuid
from typing import Dict, List, Optional

from .storage_backend import StorageBackend


class LocalStorageBackend(StorageBackend):
    """인메모리 로컬 스토리지 (테스트용)."""

    def __init__(self) -> None:
        self._store: Dict[str, dict] = {}

    def upload(self, filename: str, data: bytes, content_type: str) -> str:
        file_id = str(uuid.uuid4())
        self._store[file_id] = {
            "file_id": file_id,
            "filename": filename,
            "data": data,
            "content_type": content_type,
            "size": len(data),
        }
        return file_id

    def download(self, file_id: str) -> Optional[bytes]:
        entry = self._store.get(file_id)
        return entry["data"] if entry else None

    def delete(self, file_id: str) -> bool:
        if file_id in self._store:
            del self._store[file_id]
            return True
        return False

    def list_files(self, prefix: str = "") -> List[Dict]:
        result = []
        for entry in self._store.values():
            if entry["filename"].startswith(prefix):
                result.append({k: v for k, v in entry.items() if k != "data"})
        return result
