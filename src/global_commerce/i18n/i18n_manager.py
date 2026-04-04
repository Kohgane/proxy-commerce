"""src/global_commerce/i18n/i18n_manager.py — 다국어 콘텐츠 관리 (Phase 93)."""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

SUPPORTED_LOCALES = ('ko', 'en', 'ja', 'zh')
DEFAULT_LOCALE = 'ko'


class I18nManager:
    """다국어 상품 콘텐츠 관리 — 로케일별 저장/조회, 폴백 지원."""

    def __init__(self, default_locale: str = DEFAULT_LOCALE):
        if default_locale not in SUPPORTED_LOCALES:
            raise ValueError(f"지원하지 않는 로케일: {default_locale}. 지원: {SUPPORTED_LOCALES}")
        self._default_locale = default_locale
        # {sku: {locale: {field: value}}}
        self._store: Dict[str, Dict[str, dict]] = {}

    @property
    def default_locale(self) -> str:
        return self._default_locale

    def set_default_locale(self, locale: str) -> None:
        if locale not in SUPPORTED_LOCALES:
            raise ValueError(f"지원하지 않는 로케일: {locale}")
        self._default_locale = locale

    def set_content(self, sku: str, locale: str, title: str, description: str,
                    features: Optional[List[str]] = None) -> dict:
        """로케일별 상품 정보 저장.

        Args:
            sku: 상품 SKU
            locale: 로케일 코드 (ko/en/ja/zh)
            title: 상품 제목
            description: 상품 설명
            features: 상품 특징 목록

        Returns:
            저장된 콘텐츠 딕셔너리
        """
        if locale not in SUPPORTED_LOCALES:
            raise ValueError(f"지원하지 않는 로케일: {locale}")
        content = {
            'sku': sku,
            'locale': locale,
            'title': title,
            'description': description,
            'features': features or [],
        }
        if sku not in self._store:
            self._store[sku] = {}
        self._store[sku][locale] = content
        logger.info("콘텐츠 저장: sku=%s locale=%s", sku, locale)
        return content

    def get_content(self, sku: str, locale: str) -> Optional[dict]:
        """로케일별 상품 정보 조회 — 해당 로케일 없으면 기본 로케일로 폴백.

        Args:
            sku: 상품 SKU
            locale: 요청 로케일

        Returns:
            콘텐츠 딕셔너리 또는 None
        """
        if sku not in self._store:
            return None
        sku_data = self._store[sku]
        if locale in sku_data:
            return sku_data[locale]
        # 폴백: 기본 로케일
        if self._default_locale in sku_data:
            logger.debug("폴백 로케일 사용: sku=%s %s→%s", sku, locale, self._default_locale)
            fallback = dict(sku_data[self._default_locale])
            fallback['_fallback'] = True
            fallback['_requested_locale'] = locale
            return fallback
        # 어떤 로케일이든 첫 번째 반환 (정렬하여 결정적 순서 보장)
        first_locale = min(sku_data.keys())
        fallback = dict(sku_data[first_locale])
        fallback['_fallback'] = True
        fallback['_requested_locale'] = locale
        return fallback

    def list_locales(self, sku: str) -> List[str]:
        """상품에 등록된 로케일 목록 반환."""
        if sku not in self._store:
            return []
        return list(self._store[sku].keys())

    def supported_locales(self) -> tuple:
        """지원하는 로케일 목록 반환."""
        return SUPPORTED_LOCALES

    def delete_content(self, sku: str, locale: str) -> bool:
        """로케일별 콘텐츠 삭제."""
        if sku in self._store and locale in self._store[sku]:
            del self._store[sku][locale]
            if not self._store[sku]:
                del self._store[sku]
            return True
        return False

    def list_skus(self) -> List[str]:
        """콘텐츠가 등록된 SKU 목록 반환."""
        return list(self._store.keys())
