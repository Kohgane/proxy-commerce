"""번역 제공자 — ABC + Google/Manual 구현."""

import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class TranslationProvider(ABC):
    """번역 제공자 추상 기반 클래스."""

    @abstractmethod
    def translate(self, text: str, src_lang: str, tgt_lang: str) -> str:
        """텍스트 번역."""


class GoogleTranslateProvider(TranslationProvider):
    """Google 번역 제공자 (mock 구현)."""

    def translate(self, text: str, src_lang: str, tgt_lang: str) -> str:
        """Google Translate API mock."""
        logger.info("Google 번역: %s->%s", src_lang, tgt_lang)
        return f"[{tgt_lang}] {text}"


class ManualTranslationProvider(TranslationProvider):
    """수동 번역 제공자."""

    def translate(self, text: str, src_lang: str, tgt_lang: str) -> str:
        """수동 번역 — 번역 보류."""
        logger.info("수동 번역 대기: %s->%s", src_lang, tgt_lang)
        return text
