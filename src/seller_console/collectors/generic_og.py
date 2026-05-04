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
from urllib.parse import urljoin

from .base import BaseCollector, CollectorResult

logger = logging.getLogger(__name__)

_USER_AGENT = "Mozilla/5.0 (compatible; KohganeBot/1.0; +https://kohganepercentiii.com)"


def _fetch_html(url: str, timeout: float = 10.0) -> Optional[str]:
    """URL에서 HTML 텍스트 fetch."""
    try:
        import requests
        resp = requests.get(url, headers={"User-Agent": _USER_AGENT}, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
        return resp.text
    except Exception as exc:
        logger.warning("HTML fetch 실패 (%s): %s", url, exc)
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
    """stdlib html.parser + 정규식으로 OG 메타태그 파싱 (BeautifulSoup4 없을 때)."""
    result: dict = {}

    # meta 태그 파싱
    meta_re = re.compile(r'<meta\s+([^>]+)>', re.IGNORECASE | re.DOTALL)
    attr_re = re.compile(r'(\w[\w\-:]*)\s*=\s*(?:"([^"]*?)"|\'([^\']*?)\'|([^\s>]*))', re.IGNORECASE)

    for meta_match in meta_re.finditer(html):
        attrs_str = meta_match.group(1)
        attrs = {}
        for m in attr_re.finditer(attrs_str):
            key = m.group(1).lower()
            val = m.group(2) or m.group(3) or m.group(4) or ""
            attrs[key] = val

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

    # JSON-LD 간단 추출
    ld_re = re.compile(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.IGNORECASE | re.DOTALL)
    for m in ld_re.finditer(html):
        try:
            data = json.loads(m.group(1))
            schemas = data if isinstance(data, list) else [data]
            for schema in schemas:
                if schema.get("@type") == "Product":
                    if not result.get("title") and schema.get("name"):
                        result["title"] = schema["name"]
                    if not result.get("brand") and schema.get("brand"):
                        brand = schema["brand"]
                        result["brand"] = brand.get("name", brand) if isinstance(brand, dict) else str(brand)
                    if not result.get("sku") and schema.get("sku"):
                        result["sku"] = schema["sku"]
        except (json.JSONDecodeError, AttributeError, TypeError):
            pass

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
            try:
                # 통화 기호 및 쉼표 제거
                price_str = re.sub(r"[^\d.]", "", str(data["price"]).replace(",", ""))
                if price_str:
                    price = Decimal(price_str)
            except InvalidOperation:
                pass

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
