"""src/images/image_manager.py — Phase 46: 이미지 CRUD + 메타데이터 관리."""
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class ImageManager:
    """이미지 등록/삭제/조회, 메타데이터 (크기, 포맷, 원본 URL, alt 텍스트)."""

    def __init__(self):
        self._images: Dict[str, dict] = {}

    def register(self, url: str, **kwargs) -> dict:
        """이미지 등록."""
        image_id = kwargs.get('id') or str(uuid.uuid4())[:8]
        image = {
            'id': image_id,
            'url': url,
            'alt_text': kwargs.get('alt_text', ''),
            'format': kwargs.get('format', self._detect_format(url)),
            'width': int(kwargs.get('width', 0)),
            'height': int(kwargs.get('height', 0)),
            'size_bytes': int(kwargs.get('size_bytes', 0)),
            'product_id': kwargs.get('product_id'),
            'created_at': datetime.now(timezone.utc).isoformat(),
        }
        self._images[image_id] = image
        logger.info("이미지 등록: %s", image_id)
        return image

    def get(self, image_id: str) -> Optional[dict]:
        return self._images.get(image_id)

    def list_all(self, product_id: Optional[str] = None) -> List[dict]:
        images = list(self._images.values())
        if product_id is not None:
            images = [i for i in images if i.get('product_id') == product_id]
        return images

    def update(self, image_id: str, **kwargs) -> dict:
        image = self._images.get(image_id)
        if image is None:
            raise KeyError(f"이미지 없음: {image_id}")
        for key in ('alt_text', 'width', 'height', 'size_bytes'):
            if key in kwargs:
                image[key] = kwargs[key]
        return image

    def delete(self, image_id: str) -> bool:
        if image_id not in self._images:
            return False
        del self._images[image_id]
        return True

    @staticmethod
    def _detect_format(url: str) -> str:
        url_lower = url.lower()
        for fmt in ('jpg', 'jpeg', 'png', 'webp', 'gif', 'svg'):
            if url_lower.endswith(f'.{fmt}'):
                return fmt
        return 'unknown'
