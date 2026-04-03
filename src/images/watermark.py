"""src/images/watermark.py — Phase 46: 워터마크 추가 (텍스트/이미지 — mock)."""
import logging

logger = logging.getLogger(__name__)

POSITIONS = {'top_left', 'top_right', 'bottom_left', 'bottom_right', 'center'}


class WatermarkService:
    """텍스트 워터마크 설정 및 적용 시뮬레이션 (mock)."""

    def __init__(self):
        self._config = {
            'text': '',
            'position': 'bottom_right',
            'font_size': 24,
            'opacity': 0.5,
        }

    def configure(self, text: str = '', position: str = 'bottom_right',
                  font_size: int = 24, opacity: float = 0.5):
        """워터마크 설정."""
        if position not in POSITIONS:
            raise ValueError(f"지원하지 않는 위치: {position}. 사용 가능: {POSITIONS}")
        if not (0.0 <= opacity <= 1.0):
            raise ValueError("투명도는 0.0~1.0 사이여야 합니다")
        self._config = {
            'text': text,
            'position': position,
            'font_size': int(font_size),
            'opacity': float(opacity),
        }
        return self._config

    def apply(self, image: dict) -> dict:
        """워터마크 적용 시뮬레이션."""
        return {
            'original_id': image.get('id'),
            'original_url': image.get('url'),
            'watermark_text': self._config['text'],
            'position': self._config['position'],
            'font_size': self._config['font_size'],
            'opacity': self._config['opacity'],
            'url': image.get('url', '') + '?wm=1',
            'simulated': True,
        }

    def get_config(self) -> dict:
        return dict(self._config)
