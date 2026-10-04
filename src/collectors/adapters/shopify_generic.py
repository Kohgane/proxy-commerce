"""Z4(오너 2026-10-04) — 범용 Shopify 수집기: 브랜드 공식몰(sewtites.com·barryking.com·csosborne.com·crimsonhides.com 등).

등록 어댑터가 없는 도메인의 `/products/<handle>` 주소면 **먼저** Shopify 공식 `/products/<handle>.json`을 부른다.
응답에 `product`가 있으면 Shopify — 제목·가격·이미지·옵션·variants(옵션 조합·가격·재고)를 그대로 담는다.
JSON이 아니거나 `product`가 없으면 `NotShopify` — 호출부가 범용 수집기로 넘기고, 그것도 못 읽으면 「미지원 사이트」.
"""
from __future__ import annotations

import logging
import re
from decimal import Decimal
from typing import Optional

from ..universal_scraper import ScrapedProduct, _extract_domain, _parse_price
from .pleasures_adapter import _fetch_shopify_json, _shopify_product_json_url

logger = logging.getLogger(__name__)


class NotShopify(Exception):
    pass


def looks_like_shopify_product(url: str) -> bool:
    return bool(_shopify_product_json_url(url))


def parse_product(product: dict, url: str) -> ScrapedProduct:
    domain = _extract_domain(url)
    title = str(product.get("title") or "")
    desc = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", str(product.get("body_html") or ""))).strip()
    imgs = [str(i.get("src")) for i in (product.get("images") or []) if isinstance(i, dict) and i.get("src")]
    variants = [v for v in (product.get("variants") or []) if isinstance(v, dict)]
    prices = [p for p in (_parse_price(str(v.get("price") or "")) for v in variants) if p is not None]
    price: Optional[Decimal] = min(prices) if prices else None
    opts = [{"name": str(o.get("name") or ""), "values": [str(x) for x in (o.get("values") or [])]}
            for o in (product.get("options") or []) if isinstance(o, dict) and o.get("name") and o.get("values")]
    if len(opts) == 1 and opts[0]["name"].lower() == "title" and opts[0]["values"] == ["Default Title"]:
        opts = []                                           # Shopify 단일 상품의 자리표시 옵션
    skus = []
    for v in variants:
        spec = [str(v.get(k)) for k in ("option1", "option2", "option3") if v.get(k) and v.get(k) != "Default Title"]
        skus.append({"spec": spec, "price": str(v.get("price") or ""), "sku": str(v.get("sku") or ""),
                     "available": bool(v.get("available", True))})
    sp = ScrapedProduct(source_url=url, domain=domain, title=title, description=desc, images=imgs[:20],
                        price=price, currency="", brand=str(product.get("vendor") or ""),
                        sku=(str(variants[0].get("sku") or "") or None) if variants else None,
                        in_stock=any(s["available"] for s in skus) if skus else None,
                        options=opts, extraction_method="adapter:shopify-json",
                        confidence=0.95 if title and imgs else 0.7,
                        raw_meta={"skus": skus, "variants": len(variants), "shopify": True})
    return sp


class ShopifyGenericAdapter:
    name = "shopify-generic"

    def fetch(self, url: str) -> ScrapedProduct:
        json_url = _shopify_product_json_url(url)
        if not json_url:
            raise NotShopify("상품 주소 모양(/products/…)이 아님")
        data = _fetch_shopify_json(json_url)
        if not (isinstance(data, dict) and isinstance(data.get("product"), dict)):
            raise NotShopify("Shopify 상품 JSON이 아님")
        sp = parse_product(data["product"], url)
        logger.info("[Shopify] %s → %s · 옵션 %d · variants %d", sp.domain, sp.title[:40], len(sp.options or []),
                    len((sp.raw_meta or {}).get("skus") or []))
        return sp
