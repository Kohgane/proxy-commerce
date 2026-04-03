"""src/storage/s3_storage.py — S3 스토리지 모의 구현."""
from __future__ import annotations

import uuid
from typing import Dict, List, Optional

from .storage_backend import StorageBackend


class S3StorageBackend(StorageBackend):
    """AWS S3 스토리지 모의 구현 (실제 AWS 호출 없음)."""

    def __init__(self, bucket: str = "mock-bucket", region: str = "ap-northeast-2") -> None:
        self.bucket = bucket
        self.region = region
        self._store: Dict[str, dict] = {}

    def upload(self, filename: str, data: bytes, content_type: str) -> str:
        file_id = f"s3://{self.bucket}/{uuid.uuid4()}/{filename}"
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
