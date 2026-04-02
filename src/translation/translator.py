"""번역 요청 관리자."""

import logging
import uuid
from datetime import datetime

from .providers import GoogleTranslateProvider

logger = logging.getLogger(__name__)

STATUS_PENDING = 'pending'
STATUS_TRANSLATING = 'translating'
STATUS_REVIEW = 'review'
STATUS_APPROVED = 'approved'


class TranslationManager:
    """번역 요청 관리 — 생성/상태조회/승인."""

    def __init__(self, provider=None):
        self._provider = provider or GoogleTranslateProvider()
        self._requests: dict = {}

    def create_request(self, product_id: str, text: str, src_lang: str, tgt_lang: str) -> dict:
        """번역 요청 생성.

        Args:
            product_id: 상품 ID
            text: 번역할 텍스트
            src_lang: 소스 언어 코드
            tgt_lang: 타겟 언어 코드

        Returns:
            생성된 번역 요청 딕셔너리
        """
        request_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        try:
            translated = self._provider.translate(text, src_lang, tgt_lang)
            status = STATUS_REVIEW
        except Exception as exc:
            logger.error("번역 실행 오류: %s", exc)
            translated = None
            status = STATUS_PENDING

        req = {
            'request_id': request_id,
            'product_id': product_id,
            'original_text': text,
            'translated_text': translated,
            'src_lang': src_lang,
            'tgt_lang': tgt_lang,
            'status': status,
            'created_at': now,
            'updated_at': now,
        }
        self._requests[request_id] = req
        logger.info("번역 요청 생성: %s (%s->%s)", request_id, src_lang, tgt_lang)
        return req

    def get_status(self, request_id: str) -> dict | None:
        """번역 요청 상태 조회."""
        return self._requests.get(request_id)

    def approve(self, request_id: str) -> bool:
        """번역 요청 승인."""
        req = self._requests.get(request_id)
        if not req:
            return False
        req['status'] = STATUS_APPROVED
        req['updated_at'] = datetime.now().isoformat()
        logger.info("번역 승인: %s", request_id)
        return True

    def get_all(self) -> list:
        """모든 번역 요청 목록."""
        return list(self._requests.values())
