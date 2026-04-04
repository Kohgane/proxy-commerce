"""src/global_commerce/i18n/translation_sync.py — 번역 상태 동기화 (Phase 93)."""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

SUPPORTED_LOCALES = ('ko', 'en', 'ja', 'zh')


class TranslationSync:
    """기존 src/translation/ 모듈과 연동하여 번역 상태 동기화."""

    def __init__(self, translation_manager=None):
        self._translation_manager = translation_manager
        # {sku: {locale: sync_status}}
        self._sync_state: Dict[str, Dict[str, str]] = {}

    def sync_product(self, sku: str, source_locale: str, target_locale: str,
                     title: str, description: str) -> dict:
        """상품 번역 요청 및 상태 동기화.

        Args:
            sku: 상품 SKU
            source_locale: 원본 언어
            target_locale: 대상 언어
            title: 번역할 제목
            description: 번역할 설명

        Returns:
            번역 동기화 결과
        """
        result = {
            'sku': sku,
            'source_locale': source_locale,
            'target_locale': target_locale,
            'status': 'pending',
            'request_ids': [],
        }

        if self._translation_manager is not None:
            try:
                req_title = self._translation_manager.create_request(
                    product_id=sku,
                    text=title,
                    src_lang=source_locale,
                    tgt_lang=target_locale,
                )
                req_desc = self._translation_manager.create_request(
                    product_id=sku,
                    text=description,
                    src_lang=source_locale,
                    tgt_lang=target_locale,
                )
                result['request_ids'] = [req_title['request_id'], req_desc['request_id']]
                result['status'] = 'submitted'
            except Exception as exc:
                logger.error("번역 요청 실패: sku=%s %s→%s: %s", sku, source_locale, target_locale, exc)
                result['status'] = 'error'
                result['error'] = str(exc)
        else:
            result['status'] = 'no_provider'

        if sku not in self._sync_state:
            self._sync_state[sku] = {}
        self._sync_state[sku][target_locale] = result['status']
        return result

    def get_sync_status(self, sku: str, locale: Optional[str] = None) -> dict:
        """번역 동기화 상태 조회.

        Args:
            sku: 상품 SKU
            locale: 특정 로케일 (None이면 모든 로케일)

        Returns:
            동기화 상태 딕셔너리
        """
        if sku not in self._sync_state:
            if locale:
                return {'sku': sku, 'locale': locale, 'status': 'not_synced'}
            return {'sku': sku, 'statuses': {}}
        if locale:
            return {
                'sku': sku,
                'locale': locale,
                'status': self._sync_state[sku].get(locale, 'not_synced'),
            }
        return {'sku': sku, 'statuses': dict(self._sync_state[sku])}

    def list_pending(self) -> List[dict]:
        """번역 대기 중인 항목 목록 반환."""
        pending = []
        for sku, locales in self._sync_state.items():
            for locale, status in locales.items():
                if status == 'pending':
                    pending.append({'sku': sku, 'locale': locale, 'status': status})
        return pending
