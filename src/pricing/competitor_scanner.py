from __future__ import annotations

import os
import time
from statistics import quantiles

_CACHE: dict[str, dict] = {}
_TTL_SEC = int(float(os.getenv("PRICING_COMPETITOR_SCAN_TTL_HOURS", "12")) * 3600)


def _cache_key(query: str, market: str, limit: int) -> str:
    return f"{query.strip().lower()}|{market.strip().lower()}|{limit}"


def _filter_iqr(items: list[dict]) -> list[dict]:
    prices = [int(i["price_krw"]) for i in items if i.get("price_krw")]
    if len(prices) < 5:
        return items
    q1, _, q3 = quantiles(prices, n=4, method="inclusive")
    iqr = q3 - q1
    low, high = q1 - (1.5 * iqr), q3 + (1.5 * iqr)
    return [i for i in items if low <= int(i.get("price_krw", 0)) <= high]


def scan_competitor_prices(
    *,
    product_name: str,
    brand: str = "",
    market: str = "smartstore",
    limit: int = 8,
) -> list[dict]:
    query = " ".join([x for x in [brand.strip(), product_name.strip()] if x]).strip() or product_name.strip()
    key = _cache_key(query, market, limit)
    now = time.time()
    cached = _CACHE.get(key)
    if cached and cached.get("expires_at", 0) > now:
        return cached.get("items", [])

    items: list[dict] = []

    # 1) Phase 144 키워드 최적화 모듈(있으면)에서 검색 키워드 우선 활용
    try:
        from src.ads.keyword_optimizer import extract_keywords  # type: ignore

        keywords = extract_keywords(query) or [query]
        query = " ".join(keywords[:4]).strip() or query
    except Exception:
        pass

    # 2) 마켓 검색 API (기존 competitor_scout 재사용)
    try:
        from src.pricing.competitor_scout import CompetitorScout

        rows = CompetitorScout().collect_for_sku("ai-listing", query, limit=limit)
        for row in rows:
            items.append(
                {
                    "market": market,
                    "title": row.get("query") or query,
                    "price_krw": int(row.get("competitor_price_krw") or 0),
                    "url": row.get("link") or "",
                }
            )
    except Exception:
        pass

    # 3) 실데이터가 없으면 합성 가격을 만들지 않는다.
    if not items:
        _CACHE[key] = {"items": [], "expires_at": now + _TTL_SEC}
        return []

    items = _filter_iqr(items)[:limit]
    _CACHE[key] = {"items": items, "expires_at": now + _TTL_SEC}
    return items
