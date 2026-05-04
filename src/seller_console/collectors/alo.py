"""src/seller_console/collectors/alo.py — Alo Yoga 수집기 (Phase 128).

requests + BeautifulSoup4 스크래핑.
JSON-LD product schema 우선 추출.
robots.txt 존중 + User-Agent 명시.
BeautifulSoup4 없으면 GenericOgCollector 폴백.
"""
from __future__ import annotations

import json
import logging
import re
from decimal import Decimal, InvalidOperation
from typing import Optional

from .base import BaseCollector, CollectorResult
from .generic_og import GenericOgCollector, _fetch_html, _parse_og_bs4

logger = logging.getLogger(__name__)

_USER_AGENT = "Mozilla/5.0 (compatible; KohganeBot/1.0; +https://kohganepercentiii.com)"


def _parse_alo_html(html: str) -> dict:
    """Alo Yoga 상품 페이지 HTML 파싱.

    JSON-LD schema → OG 메타 순으로 시도.
    """
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")

        result: dict = {}

        # JSON-LD Product 스키마 우선
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
                schemas = data if isinstance(data, list) else [data]
                for schema in schemas:
                    if schema.get("@type") == "Product":
                        result["title"] = schema.get("name", "")
                        result["description"] = schema.get("description", "")
                        brand = schema.get("brand", {})
                        result["brand"] = brand.get("name", "") if isinstance(brand, dict) else str(brand)
                        result["sku"] = schema.get("sku", "")
                        imgs = schema.get("image", [])
                        if isinstance(imgs, str):
                            imgs = [imgs]
                        result["images"] = imgs
                        offers = schema.get("offers", {})
                        if isinstance(offers, list):
                            offers = offers[0] if offers else {}
                        if offers:
                            result["price"] = str(offers.get("price", ""))
                            result["currency"] = offers.get("priceCurrency", "USD")
                        return result
            except (json.JSONDecodeError, AttributeError):
                pass

        # OG 메타 폴백
        return _parse_og_bs4(html)

    except ImportError:
        # BeautifulSoup4 없음 — generic_og 폴백
        return {}


class AloCollector(BaseCollector):
    """Alo Yoga (aloyoga.com) 상품 수집기."""

    name = "alo_scrape"

    def collect(self, url: str) -> CollectorResult:
        """Alo Yoga URL에서 상품 정보 수집."""
        try:
            from bs4 import BeautifulSoup  # noqa: F401 — 가용성 확인
        except ImportError:
            logger.warning("BeautifulSoup4 없음 — GenericOgCollector 폴백")
            result = GenericOgCollector().collect(url)
            result.source = "alo_og"
            result.warnings.append("beautifulsoup4 미설치 — OG 메타 폴백 사용")
            return result

        html = _fetch_html(url, timeout=self.timeout)
        if html is None:
            return CollectorResult(
                success=False,
                url=url,
                source="alo_scrape",
                error="Alo Yoga 페이지 로드 실패",
            )

        data = _parse_alo_html(html)

        price: Optional[Decimal] = None
        if data.get("price"):
            from .generic_og import _parse_price
            price = _parse_price(str(data["price"]))

        images = list(dict.fromkeys(data.get("images", [])))

        return CollectorResult(
            success=True,
            url=url,
            source="alo_scrape",
            title=data.get("title"),
            description=data.get("description"),
            images=images[:10],
            price=price,
            currency=data.get("currency") or "USD",
            brand=data.get("brand") or "Alo Yoga",
            sku=data.get("sku"),
        )
