"""src/file_storage/file_uploader.py — 파일 업로드 (청크 업로드, 중복 검사)."""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from .file_metadata import FileMetadata
from .storage_backend import StorageBackend


class FileUploader:
    """파일 업로드 처리 (청크 업로드, 진행률, 중복 검사)."""

    CHUNK_SIZE = 1 * 1024 * 1024  # 1MB

    def __init__(self, backend: StorageBackend) -> None:
        self._backend = backend
        self._pending_chunks: Dict[str, Dict[int, bytes]] = {}
        self._upload_sessions: Dict[str, dict] = {}

    def upload(self, key: str, data: bytes, filename: str,
               content_type: str = "application/octet-stream",
               check_duplicate: bool = True) -> FileMetadata:
        """단일 파일 업로드."""
        # 중복 검사
        if check_duplicate and self._backend.exists(key):
            existing = self._backend.get_metadata(key)
            if existing:
                checksum = FileMetadata.compute_checksum(data)
                if existing.checksum == checksum:
                    return existing
        metadata = FileMetadata(
            key=key,
            filename=filename,
            content_type=content_type,
            size=len(data),
        )
        return self._backend.put(key, data, metadata)

    def start_chunked_upload(self, key: str, filename: str,
                              content_type: str, total_size: int) -> str:
        """청크 업로드 세션 시작."""
        upload_id = str(uuid.uuid4())
        self._pending_chunks[upload_id] = {}
        self._upload_sessions[upload_id] = {
            "upload_id": upload_id,
            "key": key,
            "filename": filename,
            "content_type": content_type,
            "total_size": total_size,
            "uploaded_bytes": 0,
            "progress_pct": 0.0,
        }
        return upload_id

    def upload_chunk(self, upload_id: str, chunk_index: int, chunk_data: bytes) -> dict:
        """청크 업로드."""
        if upload_id not in self._pending_chunks:
            raise KeyError(f"업로드 세션 없음: {upload_id}")
        self._pending_chunks[upload_id][chunk_index] = chunk_data
        session = self._upload_sessions[upload_id]
        session["uploaded_bytes"] += len(chunk_data)
        total = session.get("total_size", 1) or 1
        session["progress_pct"] = round(
            min(session["uploaded_bytes"] / total * 100, 100.0), 2
        )
        return dict(session)

    def complete_chunked_upload(self, upload_id: str) -> FileMetadata:
        """청크 업로드 완료 및 파일 합치기."""
        if upload_id not in self._pending_chunks:
            raise KeyError(f"업로드 세션 없음: {upload_id}")
        chunks = self._pending_chunks[upload_id]
        session = self._upload_sessions[upload_id]
        data = b"".join(chunks[i] for i in sorted(chunks.keys()))
        metadata = FileMetadata(
            key=session["key"],
            filename=session["filename"],
            content_type=session["content_type"],
            size=len(data),
        )
        result = self._backend.put(session["key"], data, metadata)
        del self._pending_chunks[upload_id]
        del self._upload_sessions[upload_id]
        return result

    def get_progress(self, upload_id: str) -> dict:
        """업로드 진행률 조회."""
        if upload_id not in self._upload_sessions:
            raise KeyError(f"업로드 세션 없음: {upload_id}")
        return dict(self._upload_sessions[upload_id])
