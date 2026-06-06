"""Market adapter interface for listing workflows."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, Optional


def _to_krw_amount(amount: float, currency: str) -> Optional[int]:
    cur = (currency or "KRW").upper()
    if cur == "KRW":
        return int(round(float(amount)))
    try:
        from src.price import _build_fx_rates, _to_krw

        fx_rates = _build_fx_rates()
        converted = _to_krw(Decimal(str(amount)), cur, fx_rates)
        return int(round(float(converted)))
    except Exception:
        return None


_DEFAULT_META = {
    "market": "",
    "label": "",
    "country": "KR",
    "currency": "KRW",
    "locale": "ko-KR",
    "region": "동아시아",
    "is_ready": True,
}


MARKETPLACE_META: Dict[str, Dict[str, Any]] = {
    "mock": {"label": "Mock", "country": "KR", "currency": "KRW", "locale": "ko-KR", "region": "동아시아", "is_ready": True},
    "coupang": {"label": "쿠팡", "country": "KR", "currency": "KRW", "locale": "ko-KR", "region": "동아시아", "is_ready": True},
    "smartstore": {"label": "스마트스토어", "country": "KR", "currency": "KRW", "locale": "ko-KR", "region": "동아시아", "is_ready": True},
    "naver_commerce": {"label": "스마트스토어", "country": "KR", "currency": "KRW", "locale": "ko-KR", "region": "동아시아", "is_ready": True},
    "11st": {"label": "11번가", "country": "KR", "currency": "KRW", "locale": "ko-KR", "region": "동아시아", "is_ready": True},
    "elevenst": {"label": "11번가", "country": "KR", "currency": "KRW", "locale": "ko-KR", "region": "동아시아", "is_ready": True},
    "kohganemultishop": {"label": "코가네멀티샵", "country": "KR", "currency": "KRW", "locale": "ko-KR", "region": "동아시아", "is_ready": True},
    "woocommerce": {"label": "WooCommerce", "country": "KR", "currency": "KRW", "locale": "ko-KR", "region": "동아시아", "is_ready": True},
    "shopify": {"label": "Shopify", "country": "US", "currency": "USD", "locale": "en-US", "region": "북미", "is_ready": True},
    "amazon": {"label": "Amazon", "country": "US", "currency": "USD", "locale": "en-US", "region": "북미", "is_ready": False},
    "ebay": {"label": "eBay", "country": "GB", "currency": "GBP", "locale": "en-GB", "region": "유럽", "is_ready": False},
    "shopee": {"label": "Shopee", "country": "SG", "currency": "SGD", "locale": "en-SG", "region": "동남아", "is_ready": False},
}


def get_marketplace_meta(market: str) -> Dict[str, Any]:
    key = (market or "").strip().lower()
    found = MARKETPLACE_META.get(key, {})
    meta = {**_DEFAULT_META, **found}
    meta["market"] = key
    if not meta.get("label"):
        meta["label"] = market
    return meta


@dataclass
class ListingPayload:
    """상품 등록 payload.

    price/currency를 우선 값으로 간주하며, price_krw는 하위호환 필드다.
    둘 다 입력되고 값이 불일치하면 price/currency 기준으로 price_krw를 정규화한다.
    """

    title: str
    description: str
    price: Optional[float] = None
    currency: str = "KRW"
    price_krw: Optional[int] = None
    sku: str = ""
    qty: int = 0
    options: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.currency = (self.currency or "KRW").upper()
        if self.price is None and self.price_krw is not None:
            self.price = float(self.price_krw)
            self.currency = "KRW"
        elif self.price is not None and self.price_krw is None:
            self.price_krw = _to_krw_amount(float(self.price), self.currency)
        elif self.price is not None and self.price_krw is not None:
            normalized = _to_krw_amount(float(self.price), self.currency)
            if normalized is not None and normalized != self.price_krw:
                self.price_krw = normalized


@dataclass
class ListingResult:
    ok: bool
    market: str
    external_id: str = ""
    message: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OrderStatus:
    external_order_id: str
    status: str
    raw: Dict[str, Any] = field(default_factory=dict)


class MarketAdapter(ABC):
    market: str = ""
    country: str = "KR"
    currency: str = "KRW"
    locale: str = "ko-KR"
    region: str = "동아시아"

    @abstractmethod
    def create_listing(self, payload: ListingPayload) -> ListingResult:
        ...

    @abstractmethod
    def update_inventory(self, sku: str, qty: int) -> bool:
        ...

    @abstractmethod
    def get_order_status(self, external_order_id: str) -> OrderStatus:
        ...

    def marketplace_meta(self) -> Dict[str, Any]:
        meta = get_marketplace_meta(self.market)
        return {
            **meta,
            "market": self.market,
            "country": self.country or meta.get("country"),
            "currency": self.currency or meta.get("currency"),
            "locale": self.locale or meta.get("locale"),
            "region": self.region or meta.get("region"),
        }

    def is_configured(self) -> bool:
        return False

    def validate_listing(self, payload: ListingPayload) -> ListingResult:
        missing = []
        if not payload.title:
            missing.append("title")
        if not payload.description:
            missing.append("description")
        if payload.price is None and payload.price_krw is None:
            missing.append("price")
        if missing:
            return self._mock_result(
                f"required fields missing: {', '.join(missing)}",
                ok=False,
                raw={"status": "invalid_payload", "missing": missing},
            )
        return self._mock_result("listing payload validated", ok=True, raw={"status": "validated"})

    def upload_product(self, payload: ListingPayload) -> ListingResult:
        if not self.is_configured():
            return self._mock_result(
                "market credentials are missing; integration is not configured",
                ok=False,
                raw={"status": "not_configured"},
            )
        return self.create_listing(payload)

    def _mock_result(
        self,
        message: str,
        external_id: Optional[str] = None,
        *,
        ok: bool = True,
        raw: Optional[Dict[str, Any]] = None,
    ) -> ListingResult:
        return ListingResult(
            ok=ok,
            market=self.market,
            external_id=external_id or (f"MOCK-{self.market.upper()}" if ok else ""),
            message=message,
            raw=raw or {},
        )
