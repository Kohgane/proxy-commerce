"""src/seo/url_optimizer.py — URL 슬러그 최적화.

제품명을 SEO 친화적인 URL 슬러그로 변환한다.
"""

import re


class URLOptimizer:
    """URL 슬러그 생성 및 관리."""

    def __init__(self):
        # 슬러그 중복 방지용 인메모리 레지스트리
        self._registry: dict = {}

    def _slugify(self, text: str) -> str:
        """텍스트를 URL 슬러그로 변환한다."""
        # 소문자 변환
        slug = text.lower()
        # 공백 → 하이픈
        slug = slug.replace(" ", "-")
        # 알파벳·숫자·하이픈 이외 문자 제거
        slug = re.sub(r"[^a-z0-9\-]", "", slug)
        # 연속 하이픈 → 단일 하이픈
        slug = re.sub(r"-+", "-", slug)
        # 양쪽 하이픈 제거
        slug = slug.strip("-")
        return slug or "product"

    def _has_korean(self, text: str) -> bool:
        """한국어 문자가 포함되어 있는지 확인한다."""
        return any(0xAC00 <= ord(c) <= 0xD7A3 for c in text)

    def _ensure_unique(self, slug: str) -> str:
        """슬러그가 레지스트리에서 유일하도록 접미사를 추가한다."""
        if slug not in self._registry:
            return slug
        counter = 1
        while f"{slug}-{counter}" in self._registry:
            counter += 1
        return f"{slug}-{counter}"

    def generate_slug(self, product_name: str, language: str = "en") -> str:
        """제품명을 고유 URL 슬러그로 변환한다.

        한국어가 포함된 경우 영문 변환을 시도하고 한국어 문자를 제거한다.

        Args:
            product_name: 제품명.
            language: 언어 코드 (기본 "en").

        Returns:
            고유 URL 슬러그 문자열.
        """
        # 한국어가 포함된 경우 한국어 문자 제거 후 나머지 영문 처리
        if self._has_korean(product_name):
            cleaned = re.sub(r"[\uAC00-\uD7A3]+", " ", product_name)
        else:
            cleaned = product_name

        slug = self._slugify(cleaned)
        unique_slug = self._ensure_unique(slug)
        self._registry[unique_slug] = True
        return unique_slug

    def normalize_url(self, url: str) -> str:
        """URL을 정규화한다.

        소문자 변환, 중복 슬래시 제거, 말미 슬래시 제거.

        Args:
            url: 정규화할 URL.

        Returns:
            정규화된 URL 문자열.
        """
        url = url.lower()
        # 프로토콜 보존
        if "://" in url:
            proto, rest = url.split("://", 1)
            rest = re.sub(r"/+", "/", rest)
            url = f"{proto}://{rest}"
        else:
            url = re.sub(r"/+", "/", url)
        # 말미 슬래시 제거 (루트 경로 "/" 제외)
        if url.endswith("/") and url.count("/") > (3 if "://" in url else 1):
            url = url.rstrip("/")
        return url

    def reset(self) -> None:
        """슬러그 레지스트리를 초기화한다 (테스트용)."""
        self._registry.clear()
