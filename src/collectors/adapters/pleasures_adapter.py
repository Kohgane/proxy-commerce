"""src/collectors/adapters/pleasures_adapter.py — Pleasures Now 어댑터 (Phase 135).

도메인: pleasuresnow.com (Shopify 기반 스트릿웨어)
Shopify 공식 /products/<slug>.json 엔드포인트 활용.
variants/options/images 모두 추출.
"""
from __future__ import annotations

import json
import logging
import os
import re
from decimal import Decimal
from typing import Optional
from urllib.parse import urlparse

from .base_adapter import BrandAdapter
from ..universal_scraper import ScrapedProduct, _extract_domain, _fetch_html, _parse_price, _is_safe_url

logger = logging.getLogger(__name__)

_DRY_RUN = os.getenv("ADAPTER_DRY_RUN", "0") == "1"
_TIMEOUT = int(os.getenv("SCRAPER_TIMEOUT_SEC", "15"))


def _shopify_product_json_url(url: str) -> Optional[str]:
    """Shopify 상품 URL에서 .json 엔드포인트 URL 구성.

    https://pleasuresnow.com/products/some-slug → https://pleasuresnow.com/products/some-slug.json
    """
    try:
        parsed = urlparse(url)
        path = parsed.path.rstrip("/")
        if "/products/" in path:
            # slug 추출
            m = re.search(r"/products/([^/?#]+)", path)
            if m:
                slug = m.group(1)
                return f"{parsed.scheme}://{parsed.netloc}/products/{slug}.json"
    except Exception:
        pass
    return None


def _fetch_shopify_json(json_url: str) -> Optional[dict]:
    """Shopify /products/<slug>.json 엔드포인트에서 상품 데이터 fetch."""
    if _DRY_RUN:
        return None
    if not _is_safe_url(json_url):
        return None
    try:
        import requests
        resp = requests.get(
            json_url,
            headers={"User-Agent": "KohganePercentiii/1.0"},
            timeout=_TIMEOUT,
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception as exc:
        logger.warning("Shopify JSON fetch 실패: %s — %s", json_url, exc)
    return None


class PleasuresAdapter(BrandAdapter):
    """Pleasures Now (pleasuresnow.com) 전용 어댑터 — Shopify 기반."""

    name = "pleasures"
    domain = "pleasuresnow.com"

    def fetch(self, url: str) -> ScrapedProduct:
        """Shopify /products/<slug>.json 우선, HTML 파싱 폴백."""
        domain = _extract_domain(url)

        if _DRY_RUN:
            return ScrapedProduct(
                source_url=url, domain=domain,
                title="Pleasures DRY_RUN 상품", description="테스트",
                images=["https://example.com/pleasures.jpg"],
                price=Decimal("65.00"), currency="USD",
                brand="Pleasures", extraction_method="adapter:pleasures", confidence=1.0,
                options=[{"name": "Size", "values": ["S", "M", "L"]}],
            )

        # 1. Shopify JSON API
        json_url = _shopify_product_json_url(url)
        if json_url:
            product_data = _fetch_shopify_json(json_url)
            if product_data and "product" in product_data:
                return self._parse_shopify_json(product_data["product"], url, domain)

        # 2. HTML 폴백
        html = _fetch_html(url)
        if not html:
            return ScrapedProduct(
                source_url=url, domain=domain,
                title="", description="",
                extraction_method="adapter:pleasures", confidence=0.0,
            )

        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
        except ImportError:
            return ScrapedProduct(source_url=url, domain=domain, title="", description="", confidence=0.0)

        return self._parse_html(soup, url, domain)

    def _parse_shopify_json(self, product: dict, url: str, domain: str) -> ScrapedProduct:
        """Shopify /products/<slug>.json product 객체 파싱."""
        title = product.get("title", "")
        desc_html = product.get("body_html", "") or ""
        # HTML 태그 제거
        desc = re.sub(r"<[^>]+>", " ", desc_html).strip()
        vendor = product.get("vendor", "Pleasures")

        # 이미지
        imgs = [img.get("src", "") for img in product.get("images", []) if img.get("src")]
        imgs = [i for i in imgs if i][:10]

        # 가격 (첫 번째 variant)
        variants = product.get("variants", [])
        price_val = None
        currency = "USD"
        if variants:
            price_raw = str(variants[0].get("price", ""))
            price_val = _parse_price(price_raw)

        # 옵션
        options = []
        for opt in product.get("options", []):
            opt_name = opt.get("name", "")
            opt_values = opt.get("values", [])
            if opt_name and opt_values:
                options.append({"name": opt_name, "values": opt_values})

        sku = variants[0].get("sku", "") if variants else ""

        in_stock = any(v.get("available", False) for v in variants)

        confidence = 0.95 if title and imgs else 0.75

        return ScrapedProduct(
            source_url=url, domain=domain,
            title=title, description=desc,
            images=imgs, price=price_val, currency=currency,
            brand=vendor, sku=sku or None,
            in_stock=in_stock,
            options=options,
            extraction_method="adapter:pleasures:shopify-json", confidence=confidence,
        )

    def _parse_html(self, soup, url: str, domain: str) -> ScrapedProduct:
        """HTML 폴백 파싱 (JSON-LD 우선)."""
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
                schemas = data if isinstance(data, list) else [data]
                for schema in schemas:
                    if schema.get("@type") != "Product":
                        continue
                    title = schema.get("name", "")
                    if not title:
                        continue
                    desc = schema.get("description", "")
                    imgs = schema.get("image", [])
                    if isinstance(imgs, str):
                        imgs = [imgs]
                    offers = schema.get("offers") or {}
                    if isinstance(offers, list):
                        offers = offers[0] if offers else {}
                    price_val = _parse_price(str(offers.get("price", "")))
                    currency = offers.get("priceCurrency", "USD") or "USD"
                    return ScrapedProduct(
                        source_url=url, domain=domain,
                        title=title, description=desc,
                        images=imgs[:10], price=price_val, currency=currency,
                        brand="Pleasures",
                        extraction_method="adapter:pleasures:html", confidence=0.8,
                    )
            except (json.JSONDecodeError, AttributeError):
                continue

        title = soup.find("h1")
        title = title.get_text(strip=True) if title else ""

        return ScrapedProduct(
            source_url=url, domain=domain,
            title=title, description="",
            extraction_method="adapter:pleasures:html", confidence=0.4 if title else 0.1,
        )
