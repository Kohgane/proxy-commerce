"""src/editor/market_sanitizer.py — 마켓별 HTML 제약에 맞춘 sanitize."""

import re
from urllib.parse import urlparse
from bs4 import BeautifulSoup


# 마켓별 금지 태그 목록
MARKET_BLOCKED_TAGS = {
    'coupang': ['script', 'iframe', 'form', 'object', 'embed', 'link', 'meta', 'style'],
    'smartstore': ['script', 'iframe', 'object', 'embed', 'link', 'meta'],
    'shopify': ['script', 'iframe', 'form'],
}

# 마켓별 금지 속성 패턴
MARKET_BLOCKED_ATTRS = {
    'coupang': ['on\\w+'],          # onclick, onload 등 이벤트 핸들러
    'smartstore': ['on\\w+', 'href'],  # 이벤트 핸들러 + 외부 링크
    'shopify': ['on\\w+'],
}


class MarketSanitizer:
    """마켓별 HTML 제약에 맞춘 sanitize 및 유효성 검사."""

    def sanitize(self, html: str, market: str) -> str:
        """마켓별 HTML 정제.

        마켓별 정책:
        - 쿠팡: script/iframe/form 태그 제거, 인라인 스타일만 허용
        - 스마트스토어: script 제거, 네이버 규격 준수, 외부 링크 제거
        - Shopify: Liquid-safe HTML

        Args:
            html: 원본 HTML 문자열
            market: 마켓명 ('coupang', 'smartstore', 'shopify')

        Returns:
            정제된 HTML 문자열
        """
        soup = BeautifulSoup(html, 'html.parser')
        blocked_tags = MARKET_BLOCKED_TAGS.get(market, [])
        blocked_attr_patterns = MARKET_BLOCKED_ATTRS.get(market, [])

        # 금지 태그 제거
        for tag_name in blocked_tags:
            for tag in soup.find_all(tag_name):
                tag.decompose()

        # 금지 속성 제거
        for tag in soup.find_all(True):
            attrs_to_remove = []
            for attr in list(tag.attrs):
                for pattern in blocked_attr_patterns:
                    if re.fullmatch(pattern, attr, re.IGNORECASE):
                        attrs_to_remove.append(attr)
                        break
            for attr in attrs_to_remove:
                del tag.attrs[attr]

        # 마켓별 추가 처리
        if market == 'coupang':
            # 인라인 스타일 외 <style> 태그 제거 (blocked_tags에 이미 포함)
            pass
        elif market == 'smartstore':
            # 외부 링크 제거 (href 속성 제거로 처리됨)
            pass
        elif market == 'shopify':
            # Liquid 템플릿 구문 이스케이프 — {{ }} 제거
            result = str(soup)
            result = result.replace('{{', '&#123;&#123;').replace('}}', '&#125;&#125;')
            return result

        return str(soup)

    def validate(self, html: str, market: str) -> dict:
        """HTML 유효성 검사.

        Args:
            html: 검사할 HTML 문자열
            market: 마켓명

        Returns:
            {'passed': bool, 'warnings': list[str]}
        """
        warnings = []
        blocked_tags = MARKET_BLOCKED_TAGS.get(market, [])
        soup = BeautifulSoup(html, 'html.parser')

        for tag_name in blocked_tags:
            if soup.find(tag_name):
                warnings.append(f'금지된 태그 발견: <{tag_name}>')

        # 이벤트 핸들러 속성 확인
        for tag in soup.find_all(True):
            for attr in tag.attrs:
                if re.match(r'^on', attr, re.IGNORECASE):
                    warnings.append(f'이벤트 핸들러 속성 발견: {attr} (태그: <{tag.name}>)')

        # 마켓별 추가 검사
        if market == 'smartstore':
            # 외부 링크 확인
            for a_tag in soup.find_all('a', href=True):
                href = a_tag.get('href', '')
                if href.startswith('http'):
                    domain = urlparse(href).netloc
                    if 'naver' not in domain and 'naver.com' not in domain:
                        warnings.append(f'외부 링크 발견: {href}')

        if market == 'shopify':
            # Liquid 구문 확인
            if '{{' in html or '{%' in html:
                warnings.append('Liquid 템플릿 구문이 포함되어 있습니다.')

        passed = len(warnings) == 0
        return {'passed': passed, 'warnings': warnings}
