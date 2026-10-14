"""견적 서비스 — URL 허용목록 검사 → 가져오기 → 파싱 → 환율 → 견적.

SSRF 방지: 허용 도메인(무신사)만 서버가 가져온다. 임의 URL은 거부.
국제배송비는 env PROXY_INTL_SHIP_TABLE_JSON(국가별 [[최대kg, USD], ...])에서만 읽는다.
표가 없거나 무게를 모르면 total을 만들지 않고 pending_shipping으로 정직하게 돌려준다(추정 금지).
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from .musinsa import parse_musinsa
from .quote_core import FIRST_ORDER_CAP_USD, build_quote

logger = logging.getLogger(__name__)

ALLOWED_HOSTS = {
    "www.musinsa.com": parse_musinsa,
    "musinsa.com": parse_musinsa,
    "m.musinsa.com": parse_musinsa,
    "store.musinsa.com": parse_musinsa,
}


def host_parser(url: str):
    try:
        u = urlparse(url)
    except ValueError:
        return None
    if u.scheme not in ("http", "https") or u.username or u.password:
        return None
    return ALLOWED_HOSTS.get((u.hostname or "").lower())


def lookup_intl_ship(country: str, weight_kg: Optional[float]) -> Optional[float]:
    raw = os.getenv("PROXY_INTL_SHIP_TABLE_JSON", "")
    if not raw or weight_kg is None:
        return None
    try:
        tiers = json.loads(raw).get((country or "").upper())
        for max_kg, usd in sorted(tiers or [], key=lambda t: t[0]):
            if weight_kg <= max_kg:
                return float(usd)
    except (ValueError, TypeError, AttributeError):
        logger.warning("PROXY_INTL_SHIP_TABLE_JSON 파싱 실패")
    return None


def fetch_html(url: str) -> Optional[str]:
    from src.collectors.universal_scraper import _fetch_html
    return _fetch_html(url)


def current_fx() -> Optional[float]:
    """실시간 환율만 인정 — 고정/목 값이면 None (가짜 견적 방지)."""
    from src.seller_console.data_aggregator import get_fx_rates
    fx = get_fx_rates()
    if fx.get("is_mock"):
        return None
    v = fx.get("USD")
    return float(v) if v else None


def make_quote(url: str, country: str = "US", weight_kg: Optional[float] = None,
               duty_rate: Optional[float] = None) -> Dict[str, Any]:
    parser = host_parser(url)
    if parser is None:
        return {"ok": False, "status": "unsupported_site",
                "message": "We currently quote items from Musinsa only."}
    html = fetch_html(url)
    item = parser(html) if html else None
    if not item:
        return {"ok": False, "status": "manual_review",
                "message": "We could not read this page automatically. We will quote it by hand."}
    fx = current_fx()
    if fx is None:
        return {"ok": False, "status": "manual_review",
                "message": "Live exchange rate unavailable. We will quote it by hand."}
    ship = lookup_intl_ship(country, weight_kg)
    base = {"title": item["title"], "price_krw": item["price_krw"], "country": country.upper()}
    if ship is None:
        return {"ok": True, "status": "pending_shipping", **base,
                "message": "International shipping is confirmed by weight; we will email the final total."}
    q = build_quote(item["price_krw"], item["kr_ship_krw"], ship, fx,
                    title=item["title"], duty_rate=duty_rate)
    if q.blocked:
        return {"ok": False, "status": "prohibited", **base,
                "message": "This item falls in a category we cannot ship."}
    if q.over_cap:
        return {"ok": False, "status": "over_cap", **base,
                "message": f"First orders are capped at ${FIRST_ORDER_CAP_USD}."}
    return {"ok": True, "status": "quoted", **base, "total_usd": str(q.total_usd),
            "lines": q.lines(), "valid_hours": 48}
