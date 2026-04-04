"""src/global_commerce/i18n/locale_detector.py — 로케일 감지 (Phase 93)."""
from __future__ import annotations

import logging
import re
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

SUPPORTED_LOCALES = ('ko', 'en', 'ja', 'zh')
DEFAULT_LOCALE = 'ko'

# Accept-Language 헤더 예: "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"
_ACCEPT_LANG_RE = re.compile(r'([a-zA-Z]{2,3})(?:-[a-zA-Z0-9]+)*(?:;q=([\d.]+))?')


class LocaleDetector:
    """사용자 로케일 결정 — Accept-Language 헤더 파싱 + 사용자 설정 기반."""

    def __init__(self, supported: Tuple[str, ...] = SUPPORTED_LOCALES, default: str = DEFAULT_LOCALE):
        self._supported = supported
        self._default = default

    def detect_from_header(self, accept_language: str) -> str:
        """Accept-Language 헤더에서 최적 로케일 결정.

        Args:
            accept_language: HTTP Accept-Language 헤더 값

        Returns:
            최적 로케일 코드
        """
        if not accept_language:
            return self._default

        candidates: list = []
        for match in _ACCEPT_LANG_RE.finditer(accept_language):
            lang = match.group(1).lower()
            quality_str = match.group(2)
            quality = float(quality_str) if quality_str else 1.0
            candidates.append((lang, quality))

        # 품질 값 내림차순 정렬
        candidates.sort(key=lambda x: x[1], reverse=True)

        for lang, _ in candidates:
            if lang in self._supported:
                return lang
            # 언어 코드 앞 2자 비교 (예: zh-TW → zh)
            short = lang[:2]
            if short in self._supported:
                return short

        return self._default

    def detect_from_user_preference(self, preference: Optional[str]) -> str:
        """사용자 설정 로케일 반환 (지원하지 않으면 기본 로케일).

        Args:
            preference: 사용자가 설정한 로케일 코드

        Returns:
            최적 로케일 코드
        """
        if preference and preference.lower() in self._supported:
            return preference.lower()
        return self._default

    def detect(self, accept_language: str = '', user_preference: Optional[str] = None) -> str:
        """사용자 설정 → Accept-Language → 기본값 순서로 로케일 결정.

        Args:
            accept_language: HTTP Accept-Language 헤더 값
            user_preference: 사용자 설정 로케일

        Returns:
            최적 로케일 코드
        """
        if user_preference:
            detected = self.detect_from_user_preference(user_preference)
            if detected != self._default or user_preference.lower() == self._default:
                return detected
        if accept_language:
            return self.detect_from_header(accept_language)
        return self._default

    @property
    def supported(self) -> Tuple[str, ...]:
        return self._supported

    @property
    def default(self) -> str:
        return self._default
