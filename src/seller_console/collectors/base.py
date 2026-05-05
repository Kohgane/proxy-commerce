"""src/seller_console/collectors/base.py — 수집기 기반 클래스 (Phase 128).

CollectorResult: 수집 결과 데이터 클래스
BaseCollector: 수집기 추상 기반 클래스
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional


@dataclass
class CollectorResult:
    """URL 수집 결과."""

    success: bool
    url: str
    source: str                       # "amazon_paapi", "amazon_og", "rakuten_api", "alo_scrape", ...
    title: Optional[str] = None
    description: Optional[str] = None
    images: list = field(default_factory=list)
    price: Optional[Decimal] = None
    currency: Optional[str] = None
    sku: Optional[str] = None
    asin: Optional[str] = None
    brand: Optional[str] = None
    category: Optional[str] = None
    attributes: dict = field(default_factory=dict)
    raw: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> dict:
        """JSON 직렬화용 딕셔너리 반환."""
        return {
            "success": self.success,
            "url": self.url,
            "source": self.source,
            "title": self.title,
            "description": self.description,
            "images": self.images,
            "price": str(self.price) if self.price is not None else None,
            "currency": self.currency,
            "sku": self.sku,
            "asin": self.asin,
            "brand": self.brand,
            "category": self.category,
            "attributes": self.attributes,
            "warnings": self.warnings,
            "error": self.error,
        }


class BaseCollector(ABC):
    """수집기 추상 기반 클래스."""

    name: str = "base"
    timeout: float = 10.0

    @abstractmethod
    def collect(self, url: str) -> CollectorResult:
        """URL에서 상품 정보 수집."""
        ...
