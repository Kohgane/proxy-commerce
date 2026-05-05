"""src/seller_console/collectors/generic_og.py — 범용 Open Graph 수집기 (Phase 128).

og:title, og:image, og:description, product:price:amount, product:price:currency 추출.
JSON-LD Product schema도 시도.
BeautifulSoup4 없으면 stdlib html.parser + 정규식 폴백.
"""
from __future__ import annotations

import json
import logging
import re
from decimal import Decimal, InvalidOperation
from typing import Optional
from urllib.parse import urljoin, urlparse

from .base import BaseCollector, CollectorResult

logger = logging.getLogger(__name__)

_USER_AGENT = "Mozilla/5.0 (compatible; KohganeBot/1.0; +https://kohganepercentiii.com)"

# HTML 파싱 최대 길이 (ReDoS 및 메모리 과다 사용 방지)
_MAX_HTML_LENGTH = 500_000

# 허용 URL 스키마 (SSRF 방지)
_ALLOWED_SCHEMES = frozenset({"http", "https"})
# 내부 IP 블록 방지를 위한 프라이빗 IP 패턴
_PRIVATE_HOST_RE = re.compile(
    r"^(localhost|127\.|10\.|172\.(1[6-9]|2\d|3[01])\.|192\.168\.|::1|0\.0\.0\.0)",
    re.IGNORECASE,
)


def _is_safe_url(url: str) -> bool:
    """SSRF 방지: http/https 스키마, 내부 IP 차단."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in _ALLOWED_SCHEMES:
            return False
        host = parsed.hostname or ""
        if _PRIVATE_HOST_RE.match(host):
            logger.warning("내부 호스트 차단 (SSRF 방지): %s", host)
            return False
        return True
    except Exception:
        return False


def _fetch_html(url: str, timeout: float = 10.0) -> Optional[str]:
    """URL에서 HTML 텍스트 fetch.

    SSRF 방지: http/https만 허용, 내부 IP 차단.
    """
    if not _is_safe_url(url):
        logger.warning("안전하지 않은 URL 거부: %s", url[:100])
        return None
    try:
        import requests
        resp = requests.get(url, headers={"User-Agent": _USER_AGENT}, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
        return resp.text
    except Exception as exc:
        logger.warning("HTML fetch 실패 (%s): %s", url[:100], exc)
        return None


def _parse_price(price_str: str) -> Optional[Decimal]:
    """가격 문자열을 Decimal로 변환. 숫자와 점(.)만 허용.

    예: "$29.99" → Decimal("29.99"), "1,234.56" → Decimal("1234.56")
    음수나 잘못된 형식은 None 반환.
    소수점은 최대 6자리 허용 (JPY 등 소수점 없는 통화부터 가상화폐까지 대응).
    """
    try:
        # 쉼표 제거 후 숫자와 점만 남김
        cleaned = price_str.replace(",", "")
        # 양의 정수 또는 소수 (최대 6자리 소수점)
        m = re.fullmatch(r"\d+(?:\.\d{1,6})?", cleaned.strip())
        if m:
            val = Decimal(m.group())
            return val if val > 0 else None
    except (InvalidOperation, Exception):
        pass
    return None


def _parse_og_bs4(html: str) -> dict:
    """BeautifulSoup4로 OG 메타태그 파싱."""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")

        result: dict = {}

        # Open Graph 태그
        for tag in soup.find_all("meta"):
            prop = tag.get("property", "") or tag.get("name", "")
            content = tag.get("content", "")
            if not content:
                continue
            prop_lower = prop.lower()
            if prop_lower == "og:title":
                result["title"] = content
            elif prop_lower == "og:description":
                result["description"] = content
            elif prop_lower in ("og:image", "og:image:url"):
                result.setdefault("images", [])
                result["images"].append(content)
            elif prop_lower == "product:price:amount":
                result["price"] = content
            elif prop_lower == "product:price:currency":
                result["currency"] = content
            elif prop_lower == "og:site_name":
                result["site_name"] = content

        # JSON-LD Product schema
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
                schemas = data if isinstance(data, list) else [data]
                for schema in schemas:
                    if schema.get("@type") == "Product":
                        if not result.get("title") and schema.get("name"):
                            result["title"] = schema["name"]
                        if not result.get("description") and schema.get("description"):
                            result["description"] = schema["description"]
                        if not result.get("brand") and schema.get("brand"):
                            brand = schema["brand"]
                            result["brand"] = brand.get("name", brand) if isinstance(brand, dict) else str(brand)
                        if not result.get("sku") and schema.get("sku"):
                            result["sku"] = schema["sku"]
                        # 이미지
                        imgs = schema.get("image", [])
                        if isinstance(imgs, str):
                            imgs = [imgs]
                        result.setdefault("images", [])
                        result["images"].extend(imgs)
                        # 가격
                        offers = schema.get("offers", {})
                        if isinstance(offers, list):
                            offers = offers[0] if offers else {}
                        if offers and not result.get("price"):
                            result["price"] = str(offers.get("price", ""))
                            result["currency"] = offers.get("priceCurrency", "")
            except (json.JSONDecodeError, AttributeError):
                pass

        return result

    except ImportError:
        return _parse_og_regex(html)


def _parse_og_regex(html: str) -> dict:
    """stdlib html.parser + 정규식으로 OG 메타태그 파싱 (BeautifulSoup4 없을 때).

    html.parser 기반으로 안전하게 파싱. 정규식 ReDoS 방지.
    """
    result: dict = {}

    # html.parser 기반 파싱 (정규식 대신 표준 라이브러리 사용)
    try:
        from html.parser import HTMLParser

        class _MetaParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.metas: list = []
                self.scripts: list = []
                self._in_json_ld = False
                self._json_ld_buf = []

            def handle_starttag(self, tag, attrs):
                attr_dict = dict(attrs)
                if tag == "meta":
                    self.metas.append(attr_dict)
                elif tag == "script":
                    t = attr_dict.get("type", "")
                    if "application/ld+json" in t:
                        self._in_json_ld = True
                        self._json_ld_buf = []

            def handle_endtag(self, tag):
                if tag == "script" and self._in_json_ld:
                    self.scripts.append("".join(self._json_ld_buf))
                    self._in_json_ld = False
                    self._json_ld_buf = []

            def handle_data(self, data):
                if self._in_json_ld:
                    self._json_ld_buf.append(data)

        parser = _MetaParser()
        # 입력 길이를 제한해 매우 큰 HTML 처리 방지 (DoS 방지)
        parser.feed(html[:_MAX_HTML_LENGTH])

        for attrs in parser.metas:
            prop = attrs.get("property", "") or attrs.get("name", "")
            content = attrs.get("content", "")
            if not content or not prop:
                continue
            prop_lower = prop.lower()
            if prop_lower == "og:title":
                result["title"] = content
            elif prop_lower == "og:description":
                result["description"] = content
            elif prop_lower in ("og:image", "og:image:url"):
                result.setdefault("images", [])
                result["images"].append(content)
            elif prop_lower == "product:price:amount":
                result["price"] = content
            elif prop_lower == "product:price:currency":
                result["currency"] = content
            elif prop_lower == "og:site_name":
                result["site_name"] = content

        # JSON-LD 파싱
        for script_text in parser.scripts:
            try:
                data = json.loads(script_text)
                schemas = data if isinstance(data, list) else [data]
                for schema in schemas:
                    if schema.get("@type") == "Product":
                        if not result.get("title") and schema.get("name"):
                            result["title"] = schema["name"]
                        if not result.get("brand") and schema.get("brand"):
                            brand = schema["brand"]
                            result["brand"] = brand.get("name", brand) if isinstance(brand, dict) else str(brand)
                        if not result.get("price"):
                            offers = schema.get("offers", {})
                            if isinstance(offers, list):
                                offers = offers[0] if offers else {}
                            if offers:
                                result["price"] = str(offers.get("price", ""))
                                result.setdefault("currency", offers.get("priceCurrency", ""))
                        if not result.get("sku"):
                            result["sku"] = schema.get("sku", "")
                        imgs = schema.get("image", [])
                        if isinstance(imgs, str):
                            imgs = [imgs]
                        if imgs and not result.get("images"):
                            result["images"] = list(imgs)
                        break
            except (json.JSONDecodeError, AttributeError):
                continue

    except Exception as exc:
        logger.debug("html.parser 파싱 실패, 빈 결과 반환: %s", exc)

    return result


class GenericOgCollector(BaseCollector):
    """범용 Open Graph / JSON-LD 수집기."""

    name = "generic_og"

    def collect(self, url: str) -> CollectorResult:
        """URL에서 OG 메타태그 + JSON-LD 파싱으로 상품 정보 수집."""
        html = _fetch_html(url, timeout=self.timeout)
        if html is None:
            return CollectorResult(
                success=False,
                url=url,
                source="generic_og",
                error="페이지 로드 실패",
            )

        data = _parse_og_bs4(html)

        price: Optional[Decimal] = None
        if data.get("price"):
            price = _parse_price(str(data["price"]))

        images = list(dict.fromkeys(data.get("images", [])))  # 중복 제거

        return CollectorResult(
            success=True,
            url=url,
            source="generic_og",
            title=data.get("title"),
            description=data.get("description"),
            images=images[:10],  # 최대 10장
            price=price,
            currency=data.get("currency") or "USD",
            brand=data.get("brand"),
            sku=data.get("sku"),
        )
