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


def find_actual_market_price(
    *,
    gtin: str = "",
    sku: str = "",
    product_name: str = "",
    brand: str = "",
) -> list[MarketPrice]:
    """동일/유사 상품의 KRW 실측가 목록을 반환한다.

    검증된 실데이터가 없으면 빈 목록을 반환한다.
    """
    live = all(
        [
            os.getenv("NAVER_SHOPPING_SEARCH_CLIENT_ID"),
            os.getenv("NAVER_SHOPPING_SEARCH_CLIENT_SECRET"),
            os.getenv("COUPANG_SEARCH_API_KEY"),
            os.getenv("GOOGLE_SHOPPING_API_KEY"),
        ]
    )
    if not live:
        return []

    # 실데이터 수집 경로가 명시적으로 연결되기 전까지는 합성 데이터를 생성하지 않는다.
    # (가격 결정 로직에서 "데이터 없음"으로 안전 처리)
    return _dedupe_and_filter([])
