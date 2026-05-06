"""src/collectors/adapters/lululemon_adapter.py — lululemon 어댑터 (Phase 135).

JSON-LD Product schema 우선, OG 메타 폴백.
"""
from __future__ import annotations

import json
import logging
import os
from decimal import Decimal
from typing import Optional

from .base_adapter import BrandAdapter
from ..universal_scraper import ScrapedProduct, _extract_domain, _fetch_html, _parse_price

logger = logging.getLogger(__name__)

_DRY_RUN = os.getenv("ADAPTER_DRY_RUN", "0") == "1"


class LululemonAdapter(BrandAdapter):
    """lululemon (lululemon.com) 전용 어댑터."""

    name = "lululemon"
    domain = "lululemon.com"

    def fetch(self, url: str) -> ScrapedProduct:
        """lululemon 상품 페이지에서 메타 추출."""
        domain = _extract_domain(url)

        if _DRY_RUN:
            return ScrapedProduct(
                source_url=url, domain=domain,
                title="lululemon DRY_RUN 상품", description="테스트",
                images=["https://example.com/lulu.jpg"],
                price=Decimal("128.00"), currency="USD",
                brand="lululemon", extraction_method="adapter:lululemon", confidence=1.0,
            )

        html = _fetch_html(url)
        if not html:
            return ScrapedProduct(
                source_url=url, domain=domain,
                title="", description="",
                extraction_method="adapter:lululemon", confidence=0.0,
            )

        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
        except ImportError:
            return ScrapedProduct(source_url=url, domain=domain, title="", description="", confidence=0.0)

        return self._parse(soup, url, domain)

    def _parse(self, soup, url: str, domain: str) -> ScrapedProduct:
        # JSON-LD 우선
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
                schemas = data if isinstance(data, list) else [data]
                for schema in schemas:
                    if schema.get("@type") != "Product":
                        continue
                    title = schema.get("name", "")
                    desc = schema.get("description", "")
                    brand_raw = schema.get("brand") or {}
                    brand = brand_raw.get("name", "lululemon") if isinstance(brand_raw, dict) else "lululemon"
                    sku = schema.get("sku", "")
                    imgs = schema.get("image", [])
                    if isinstance(imgs, str):
                        imgs = [imgs]
                    offers = schema.get("offers") or {}
                    if isinstance(offers, list):
                        offers = offers[0] if offers else {}
                    price_val = _parse_price(str(offers.get("price", "")))
                    currency = offers.get("priceCurrency", "USD") or "USD"
                    if not title:
                        continue
                    return ScrapedProduct(
                        source_url=url, domain=domain,
                        title=title, description=desc,
                        images=imgs[:10], price=price_val, currency=currency,
                        brand=brand, sku=sku or None,
                        extraction_method="adapter:lululemon", confidence=0.9,
                    )
            except (json.JSONDecodeError, AttributeError):
                continue

        # CSS 폴백
        title = ""
        h1 = soup.find("h1")
        if h1:
            title = h1.get_text(strip=True)

        desc = ""
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc:
            desc = meta_desc.get("content", "")

        price_val = None
        price_el = soup.select_one("[data-lulu-price], .price, .product-price")
        if price_el:
            price_val = _parse_price(price_el.get_text(strip=True))

        imgs = []
        for img in soup.select(".product-gallery img, .pdp-image img"):
            src = img.get("src", "") or img.get("data-src", "")
            if src and src.startswith("http"):
                imgs.append(src)
        imgs = list(dict.fromkeys(imgs))[:10]

        confidence = 0.5 if title else 0.2
        if imgs:
            confidence = min(confidence + 0.2, 1.0)
        if price_val:
            confidence = min(confidence + 0.1, 1.0)

        return ScrapedProduct(
            source_url=url, domain=domain,
            title=title, description=desc,
            images=imgs, price=price_val, currency="USD",
            brand="lululemon",
            extraction_method="adapter:lululemon", confidence=confidence,
        )
