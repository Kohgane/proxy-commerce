"""schemas/product.py — Unified Product schema using Pydantic.

Covers issues #85: unified product schema with validation.
"""
from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, HttpUrl, field_validator, model_validator


SUPPORTED_CURRENCIES = {"USD", "KRW", "JPY", "CNY", "EUR", "GBP", "AUD", "CAD", "HKD", "SGD"}

_CURRENCY_ALIASES: dict[str, str] = {
    "US": "USD",
    "KR": "KRW",
    "JP": "JPY",
    "CN": "CNY",
}


class StockStatus(str, Enum):
    IN_STOCK = "in_stock"
    OUT_OF_STOCK = "out_of_stock"
    LOW_STOCK = "low_stock"
    UNKNOWN = "unknown"


class ProductOption(BaseModel):
    name: str
    values: List[str]


class Product(BaseModel):
    source: str
    source_product_id: str
    source_url: str
    brand: Optional[str] = None
    title: str
    description: Optional[str] = None
    currency: str
    cost_price: float
    sell_price: Optional[float] = None
    images: List[str]
    thumbnail: Optional[str] = None
    options: List[ProductOption] = []
    stock_status: StockStatus = StockStatus.UNKNOWN

    @field_validator("title")
    @classmethod
    def title_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("title must not be empty")
        return v.strip()

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, v: str) -> str:
        normalized = _CURRENCY_ALIASES.get(v.upper(), v.upper())
        if normalized not in SUPPORTED_CURRENCIES:
            raise ValueError(f"unsupported currency: {v!r}")
        return normalized

    @field_validator("cost_price")
    @classmethod
    def cost_price_positive(cls, v: float) -> float:
        if v < 0:
            raise ValueError("cost_price must be non-negative")
        return v

    @field_validator("images")
    @classmethod
    def at_least_one_image(cls, v: List[str]) -> List[str]:
        if not v:
            raise ValueError("at least one image URL is required")
        return v

    @model_validator(mode="after")
    def set_thumbnail(self) -> "Product":
        if self.thumbnail is None and self.images:
            self.thumbnail = self.images[0]
        return self
