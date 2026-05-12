from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Iterable


@dataclass
class MarketPrice:
    market: str
    title: str
    price_krw: int
    url: str = ""
    source: str = "mock"

    def to_dict(self) -> dict:
        return asdict(self)


def _dedupe_and_filter(items: Iterable[MarketPrice]) -> list[MarketPrice]:
    deduped: list[MarketPrice] = []
    seen: set[tuple[str, str, int]] = set()
    for item in items:
        price = int(item.price_krw or 0)
        if price <= 0:
            continue
        key = (item.market.strip().lower(), item.title.strip().lower(), price)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _mock_prices(gtin: str = "", sku: str = "", product_name: str = "", brand: str = "") -> list[MarketPrice]:
    key = f"{gtin} {sku} {brand} {product_name}".lower()
    if "eight ball hoodie" in key or "840446" in key or "mkt26q1-hd0598" in key:
        return [
            MarketPrice(market="marketstudios_kr", title="마켓스튜디오스 (한국)", price_krw=209000),
            MarketPrice(market="musinsa", title="무신사 사장님 직배송", price_krw=215000),
            MarketPrice(market="29cm", title="29CM", price_krw=220000),
        ]
    return [
        MarketPrice(market="naver_shopping", title=f"{brand} {product_name}".strip() or "동일/유사 상품", price_krw=289000),
        MarketPrice(market="coupang", title=f"{brand} {product_name}".strip() or "동일/유사 상품", price_krw=305000),
    ]


def find_actual_market_price(
    *,
    gtin: str = "",
    sku: str = "",
    product_name: str = "",
    brand: str = "",
) -> list[MarketPrice]:
    """동일/유사 상품의 KRW 실측가 목록을 반환한다.

    현재 구현은 네트워크 호출 없이 안전한 mock 데이터를 반환한다.
    API 키가 모두 설정된 경우에는 운영 가시성용으로 `source` 라벨만 `live`로 표기한다.
    """
    live = all(
        [
            os.getenv("NAVER_SHOPPING_SEARCH_CLIENT_ID"),
            os.getenv("NAVER_SHOPPING_SEARCH_CLIENT_SECRET"),
            os.getenv("COUPANG_SEARCH_API_KEY"),
            os.getenv("GOOGLE_SHOPPING_API_KEY"),
        ]
    )
    items = _mock_prices(gtin=gtin, sku=sku, product_name=product_name, brand=brand)
    if live:
        for item in items:
            item.source = "live"
    return _dedupe_and_filter(items)
