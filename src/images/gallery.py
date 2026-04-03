"""src/images/gallery.py — Phase 46: 상품 갤러리 관리."""
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

MAX_GALLERY_IMAGES = 10


class ProductGallery:
    """상품별 이미지 갤러리 (순서 관리, 대표 이미지 설정, 최대 10장)."""

    def __init__(self):
        # {product_id: [image_id, ...]}
        self._galleries: Dict[str, List[str]] = {}
        # {product_id: image_id}
        self._primary: Dict[str, str] = {}

    def add_image(self, product_id: str, image_id: str) -> List[str]:
        """갤러리에 이미지 추가."""
        gallery = self._galleries.setdefault(product_id, [])
        if image_id in gallery:
            return gallery
        if len(gallery) >= MAX_GALLERY_IMAGES:
            raise ValueError(f"갤러리 최대 이미지 수 초과: {MAX_GALLERY_IMAGES}")
        gallery.append(image_id)
        # 첫 번째 이미지는 자동으로 대표 이미지
        if len(gallery) == 1:
            self._primary[product_id] = image_id
        return gallery

    def remove_image(self, product_id: str, image_id: str) -> bool:
        gallery = self._galleries.get(product_id, [])
        if image_id not in gallery:
            return False
        gallery.remove(image_id)
        # 대표 이미지가 삭제된 경우 재설정
        if self._primary.get(product_id) == image_id:
            self._primary[product_id] = gallery[0] if gallery else None
        return True

    def get_gallery(self, product_id: str) -> List[str]:
        return list(self._galleries.get(product_id, []))

    def set_primary(self, product_id: str, image_id: str):
        """대표 이미지 설정."""
        gallery = self._galleries.get(product_id, [])
        if image_id not in gallery:
            raise ValueError(f"갤러리에 없는 이미지: {image_id}")
        self._primary[product_id] = image_id

    def get_primary(self, product_id: str) -> Optional[str]:
        return self._primary.get(product_id)

    def reorder(self, product_id: str, ordered_ids: List[str]):
        """이미지 순서 변경."""
        gallery = self._galleries.get(product_id, [])
        # 기존 이미지들이 모두 포함된 경우만 적용
        if set(ordered_ids) != set(gallery):
            raise ValueError("순서 변경 시 모든 이미지 ID를 포함해야 합니다")
        self._galleries[product_id] = list(ordered_ids)
