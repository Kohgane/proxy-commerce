"""src/images/cdn_uploader.py — Phase 46: CDN 업로드 추상화 (Cloudinary, S3 — mock)."""
import abc
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict

logger = logging.getLogger(__name__)


class CDNUploader(abc.ABC):
    """CDN 업로드 추상 기반 클래스."""

    @abc.abstractmethod
    def upload(self, image_url: str, **kwargs) -> dict:
        """이미지 업로드."""

    @abc.abstractmethod
    def delete(self, public_id: str) -> bool:
        """이미지 삭제."""

    @abc.abstractmethod
    def get_url(self, public_id: str, **kwargs) -> str:
        """이미지 URL 조회."""


class CloudinaryUploader(CDNUploader):
    """Cloudinary mock 구현."""

    def __init__(self, cloud_name: str = 'mock_cloud',
                 api_key: str = 'mock_key', api_secret: str = 'mock_secret'):
        self._cloud_name = cloud_name
        self._uploads: Dict[str, dict] = {}

    def upload(self, image_url: str, folder: str = 'products', **kwargs) -> dict:
        public_id = f"{folder}/{uuid.uuid4().hex[:12]}"
        record = {
            'public_id': public_id,
            'original_url': image_url,
            'cdn_url': f"https://res.cloudinary.com/{self._cloud_name}/image/upload/{public_id}",
            'provider': 'cloudinary',
            'uploaded_at': datetime.now(timezone.utc).isoformat(),
        }
        self._uploads[public_id] = record
        logger.info("[Cloudinary mock] 업로드: %s", public_id)
        return record

    def delete(self, public_id: str) -> bool:
        if public_id not in self._uploads:
            return False
        del self._uploads[public_id]
        return True

    def get_url(self, public_id: str, width: int = 0, height: int = 0, **kwargs) -> str:
        base = f"https://res.cloudinary.com/{self._cloud_name}/image/upload"
        transforms = []
        if width:
            transforms.append(f"w_{width}")
        if height:
            transforms.append(f"h_{height}")
        transform_str = ','.join(transforms)
        if transform_str:
            return f"{base}/{transform_str}/{public_id}"
        return f"{base}/{public_id}"


class S3Uploader(CDNUploader):
    """AWS S3 mock 구현."""

    def __init__(self, bucket: str = 'mock-bucket', region: str = 'ap-northeast-2'):
        self._bucket = bucket
        self._region = region
        self._uploads: Dict[str, dict] = {}

    def upload(self, image_url: str, key_prefix: str = 'products', **kwargs) -> dict:
        key = f"{key_prefix}/{uuid.uuid4().hex[:12]}"
        record = {
            'public_id': key,
            'original_url': image_url,
            'cdn_url': f"https://{self._bucket}.s3.{self._region}.amazonaws.com/{key}",
            'provider': 's3',
            'uploaded_at': datetime.now(timezone.utc).isoformat(),
        }
        self._uploads[key] = record
        logger.info("[S3 mock] 업로드: %s", key)
        return record

    def delete(self, public_id: str) -> bool:
        if public_id not in self._uploads:
            return False
        del self._uploads[public_id]
        return True

    def get_url(self, public_id: str, **kwargs) -> str:
        return f"https://{self._bucket}.s3.{self._region}.amazonaws.com/{public_id}"
