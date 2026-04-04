"""src/mobile_api/mobile_response.py — 모바일 응답 포매터."""
from __future__ import annotations

import base64
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

_IMAGE_SIZES = {
    'thumbnail': (100, 100),
    'medium': (400, 400),
    'large': (800, 800),
}


class MobileResponseFormatter:
    """표준 모바일 API 응답 포맷터."""

    @staticmethod
    def success(data: Any = None, message: Optional[str] = None, meta: Optional[dict] = None) -> dict:
        resp: dict = {'success': True, 'data': data, 'api_version': 'v1'}
        if message:
            resp['message'] = message
        resp['meta'] = meta or {}
        return resp

    @staticmethod
    def error(error_code: str, message: str, details: Any = None, status_code: int = 400) -> dict:
        resp: dict = {
            'success': False,
            'error': {'code': error_code, 'message': message},
            'api_version': 'v1',
            'meta': {},
        }
        if details is not None:
            resp['error']['details'] = details
        resp['status_code'] = status_code
        return resp

    @staticmethod
    def paginated(items: list, next_cursor: Optional[str] = None,
                  has_more: bool = False, total: Optional[int] = None) -> dict:
        meta: dict = {'has_more': has_more, 'next_cursor': next_cursor}
        if total is not None:
            meta['total'] = total
        return {
            'success': True,
            'data': items,
            'meta': meta,
            'api_version': 'v1',
        }

    @staticmethod
    def format_image_url(url: str, size: str = 'medium') -> str:
        w, h = _IMAGE_SIZES.get(size, (400, 400))
        sep = '&' if '?' in url else '?'
        return f'{url}{sep}w={w}&h={h}'

    @classmethod
    def format_product(cls, product_dict: dict, size: str = 'medium') -> dict:
        p = dict(product_dict)
        p['images'] = [cls.format_image_url(img, size) for img in p.get('images', [])]
        return p

    @staticmethod
    def cursor_encode(offset: int) -> str:
        return base64.b64encode(str(offset).encode()).decode()

    @staticmethod
    def cursor_decode(cursor: str) -> int:
        try:
            return int(base64.b64decode(cursor.encode()).decode())
        except Exception:
            return 0
