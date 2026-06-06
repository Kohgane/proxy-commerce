"""src/seller_console/market_status.py — 마켓별 상품 상태 데이터 모델 (Phase 127).

- 활성 / 품절 / 오류 / 가격이상 / 정지
- 마켓별 어댑터 + Google Sheets 캐시 + 실시간 폴백 구조
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from datetime import datetime
from typing import List, Literal, Optional

# 지원 마켓
Marketplace = Literal[
    "coupang",
    "smartstore",
    "11st",
    "kohganemultishop",
    "woocommerce",
    "shopify",
    "amazon",
    "ebay",
    "shopee",
]

# 상품 상태
ProductState = Literal["active", "out_of_stock", "error", "price_anomaly", "suspended"]

_CURRENCY_SYMBOLS = {
    "KRW": "₩",
    "USD": "$",
    "JPY": "¥",
    "EUR": "€",
    "SGD": "S$",
    "GBP": "£",
    "CNY": "¥",
}

_CURRENCY_DECIMALS = {
    "KRW": 0,
    "JPY": 0,
    "USD": 2,
    "EUR": 2,
    "SGD": 2,
    "GBP": 2,
    "CNY": 2,
}


def format_currency_amount(amount: Optional[float], currency: str) -> str:
    if amount is None:
        return "—"
    cur = (currency or "KRW").upper()
    decimals = _CURRENCY_DECIMALS.get(cur, 2)
    symbol = _CURRENCY_SYMBOLS.get(cur, f"{cur} ")
    return f"{symbol}{amount:,.{decimals}f}"


def convert_amount(amount: float, from_currency: str, to_currency: str) -> tuple[Optional[float], bool]:
    src = (from_currency or "KRW").upper()
    dst = (to_currency or "KRW").upper()
    if src == dst:
        return float(amount), True
    try:
        from src.price import _build_fx_rates, _from_krw, _to_krw

        amount_dec = Decimal(str(amount))
        fx_rates = _build_fx_rates()
        krw = _to_krw(amount_dec, src, fx_rates)
        converted = _from_krw(krw, dst, fx_rates)
        return float(converted), True
    except Exception:
        return None, False


def marketplace_meta(marketplace: str) -> dict:
    try:
        from src.markets.adapters.base import get_marketplace_meta

        return get_marketplace_meta(marketplace)
    except Exception:
        return {
            "market": marketplace,
            "label": marketplace,
            "country": "KR",
            "currency": "KRW",
            "locale": "ko-KR",
            "region": "동아시아",
            "is_ready": True,
        }


@dataclass
class MarketStatusItem:
    """개별 상품의 마켓 상태 레코드."""

    marketplace: str
    product_id: str
    state: str
    sku: Optional[str] = None
    title: Optional[str] = None
    price: Optional[float] = None
    currency: str = "KRW"
    price_krw: Optional[int] = None
    last_synced_at: Optional[datetime] = None
    error_message: Optional[str] = None

    def __post_init__(self) -> None:
        self.currency = (self.currency or "KRW").upper()
        if self.price is None and self.price_krw is not None:
            self.price = float(self.price_krw)
            self.currency = "KRW"
        elif self.price is not None and self.price_krw is None:
            converted, ok = convert_amount(float(self.price), self.currency, "KRW")
            if ok and converted is not None:
                self.price_krw = int(round(converted))

    @property
    def price_display(self) -> str:
        return format_currency_amount(self.price, self.currency)


@dataclass
class MarketStatusSummary:
    """마켓별 상품 상태 집계 요약."""

    marketplace: str
    active: int = 0
    out_of_stock: int = 0
    error: int = 0
    price_anomaly: int = 0
    suspended: int = 0
    total: int = 0
    last_synced_at: Optional[datetime] = None
    source: str = "mock"  # "sheets" / "live" / "mock"

    # 프론트엔드용 레이블 (마켓 코드 → 한글명)
    _LABELS: dict = field(default_factory=dict, init=False, repr=False, compare=False)

    def label(self) -> str:
        """마켓 한글 레이블 반환."""
        _map = {
            "coupang": "쿠팡",
            "smartstore": "스마트스토어",
            "11st": "11번가",
            "kohganemultishop": "코가네멀티샵",
            "woocommerce": "WooCommerce",
            "shopify": "Shopify",
            "amazon": "Amazon",
            "ebay": "eBay",
            "shopee": "Shopee",
        }
        return _map.get(self.marketplace, self.marketplace)

    def to_dict(self) -> dict:
        """JSON 직렬화 가능한 dict 반환."""
        return {
            "marketplace": self.marketplace,
            "label": self.label(),
            "country": marketplace_meta(self.marketplace).get("country"),
            "currency": marketplace_meta(self.marketplace).get("currency"),
            "locale": marketplace_meta(self.marketplace).get("locale"),
            "region": marketplace_meta(self.marketplace).get("region"),
            "active": self.active,
            "out_of_stock": self.out_of_stock,
            "error": self.error,
            "price_anomaly": self.price_anomaly,
            "suspended": self.suspended,
            "total": self.total,
            "last_synced_at": self.last_synced_at.isoformat() if self.last_synced_at else None,
            "source": self.source,
        }


@dataclass
class AllMarketStatus:
    """모든 마켓 상태 집계 결과."""

    summaries: List[MarketStatusSummary]
    items: List[MarketStatusItem] = field(default_factory=list)
    fetched_at: datetime = field(default_factory=datetime.utcnow)
    source: str = "mock"  # "sheets" / "live" / "mock"

    def is_mock(self) -> bool:
        return self.source == "mock"

    def to_legacy_dict(self) -> dict:
        """기존 data_aggregator.get_market_product_status() 형태와 호환되는 dict 반환.

        widgets.py 및 market_status.html 기존 템플릿과 호환성 유지.
        """
        markets = [s.to_dict() for s in self.summaries]
        return {
            "markets": markets,
            "is_mock": self.is_mock(),
            "source": self.source,
            "fetched_at": self.fetched_at.isoformat(),
        }
