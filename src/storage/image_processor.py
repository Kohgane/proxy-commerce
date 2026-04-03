"""src/storage/image_processor.py — 이미지 처리기 (메타데이터 변환만 수행)."""
from __future__ import annotations

from .file_metadata import FileMetadata


class ImageProcessor:
    """이미지 크기 조정 / 썸네일 생성 (메타데이터 반환, 실제 처리 없음)."""

    def resize(self, metadata: FileMetadata, width: int, height: int) -> FileMetadata:
        """이미지 크기 조정 메타데이터를 반환."""
        new_name = f"resized_{width}x{height}_{metadata.name}"
        return FileMetadata(
            name=new_name,
            size=metadata.size,
            content_type=metadata.content_type,
            owner_id=metadata.owner_id,
            hash=metadata.hash,
        )

    def thumbnail(self, metadata: FileMetadata, size: int = 128) -> FileMetadata:
        """썸네일 메타데이터를 반환."""
        new_name = f"thumb_{size}_{metadata.name}"
        estimated_size = min(metadata.size, size * size * 3)
        return FileMetadata(
            name=new_name,
            size=estimated_size,
            content_type=metadata.content_type,
            owner_id=metadata.owner_id,
            hash=metadata.hash,
        )
