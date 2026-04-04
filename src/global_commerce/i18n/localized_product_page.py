"""src/global_commerce/i18n/localized_product_page.py — 로케일별 상품 페이지 생성 (Phase 93)."""
from __future__ import annotations

import logging
from typing import Optional

from .i18n_manager import I18nManager
from .locale_detector import LocaleDetector

logger = logging.getLogger(__name__)

# 로케일별 기본 메타 설정
_LOCALE_META: dict = {
    'ko': {'lang': 'ko', 'og_locale': 'ko_KR', 'currency': 'KRW'},
    'en': {'lang': 'en', 'og_locale': 'en_US', 'currency': 'USD'},
    'ja': {'lang': 'ja', 'og_locale': 'ja_JP', 'currency': 'JPY'},
    'zh': {'lang': 'zh', 'og_locale': 'zh_CN', 'currency': 'CNY'},
}


class LocalizedProductPage:
    """로케일별 상품 페이지 데이터 생성 (SEO 메타 포함)."""

    def __init__(self, i18n_manager: Optional[I18nManager] = None,
                 locale_detector: Optional[LocaleDetector] = None,
                 base_url: str = 'https://example.com'):
        self._i18n = i18n_manager or I18nManager()
        self._detector = locale_detector or LocaleDetector()
        self._base_url = base_url.rstrip('/')

    def build(self, sku: str, locale: str, price: float = 0.0,
              image_url: str = '') -> dict:
        """로케일별 상품 페이지 데이터 생성.

        Args:
            sku: 상품 SKU
            locale: 로케일 코드
            price: 상품 가격
            image_url: 상품 이미지 URL

        Returns:
            페이지 데이터 딕셔너리 (SEO 메타 포함)
        """
        content = self._i18n.get_content(sku, locale)
        if content is None:
            return {'error': f'상품을 찾을 수 없습니다: {sku}', 'sku': sku}

        effective_locale = content.get('locale', locale)
        meta = _LOCALE_META.get(effective_locale, _LOCALE_META['ko'])
        canonical_url = f"{self._base_url}/products/{sku}?locale={effective_locale}"

        seo_meta = {
            'title': content['title'],
            'description': content['description'][:160] if content.get('description') else '',
            'canonical': canonical_url,
            'og_title': content['title'],
            'og_description': content['description'][:200] if content.get('description') else '',
            'og_url': canonical_url,
            'og_locale': meta['og_locale'],
            'og_image': image_url,
            'lang': meta['lang'],
            'hreflang': {loc: f"{self._base_url}/products/{sku}?locale={loc}"
                         for loc in self._i18n.supported_locales()},
        }

        return {
            'sku': sku,
            'locale': effective_locale,
            'title': content['title'],
            'description': content['description'],
            'features': content.get('features', []),
            'price': price,
            'currency': meta['currency'],
            'image_url': image_url,
            'seo': seo_meta,
            'is_fallback': content.get('_fallback', False),
            'available_locales': self._i18n.list_locales(sku),
        }

    def detect_locale(self, accept_language: str = '', user_preference: str = '') -> str:
        """요청에서 로케일 감지."""
        return self._detector.detect(
            accept_language=accept_language,
            user_preference=user_preference or None,
        )
