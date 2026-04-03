"""src/images/optimizer.py — Phase 46: 이미지 최적화 (리사이즈, 포맷 변환 — mock)."""
import logging
from typing import Dict, List

logger = logging.getLogger(__name__)

RESIZE_SPECS: Dict[str, dict] = {
    'thumbnail': {'width': 150, 'height': 150},
    'medium': {'width': 600, 'height': 600},
    'large': {'width': 1200, 'height': 1200},
}


class ImageOptimizer:
    """이미지 최적화 mock.

    리사이즈 스펙: thumbnail (150x150), medium (600x600), large (1200x1200)
    실제 변환 없이 변환 결과 시뮬레이션.
    """

    def resize(self, image: dict, spec: str) -> dict:
        """리사이즈 시뮬레이션."""
        if spec not in RESIZE_SPECS:
            raise ValueError(f"지원하지 않는 스펙: {spec}. 사용 가능: {list(RESIZE_SPECS.keys())}")
        target = RESIZE_SPECS[spec]
        return {
            'original_id': image.get('id'),
            'original_url': image.get('url'),
            'spec': spec,
            'width': target['width'],
            'height': target['height'],
            'url': f"{image.get('url', '')}?w={target['width']}&h={target['height']}",
            'simulated': True,
        }

    def convert_format(self, image: dict, target_format: str) -> dict:
        """포맷 변환 시뮬레이션 (jpg, webp, png 등)."""
        target_format = target_format.lower()
        original_url = image.get('url', '')
        new_url = original_url.rsplit('.', 1)[0] + f'.{target_format}'
        return {
            'original_id': image.get('id'),
            'original_format': image.get('format', 'unknown'),
            'target_format': target_format,
            'url': new_url,
            'simulated': True,
        }

    def generate_variants(self, image: dict) -> List[dict]:
        """모든 스펙의 변환 결과 생성."""
        return [self.resize(image, spec) for spec in RESIZE_SPECS]

    def get_specs(self) -> Dict[str, dict]:
        return dict(RESIZE_SPECS)
