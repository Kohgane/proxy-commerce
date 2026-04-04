"""src/ai_recommendation/recommendation_model.py — Phase 94: AI 추천 데이터 모델."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class EventType(str, Enum):
    VIEW = "view"
    PURCHASE = "purchase"
    CART = "cart"
    WISHLIST = "wishlist"
    SEARCH = "search"


class PriceTier(str, Enum):
    LOW = "low"        # < 10,000원
    MID = "mid"        # 10,000 ~ 50,000원
    HIGH = "high"      # 50,000 ~ 200,000원
    PREMIUM = "premium"  # > 200,000원


@dataclass
class UserEvent:
    """사용자 이벤트 데이터."""
    user_id: str
    event_type: EventType
    product_id: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "event_type": self.event_type.value,
            "product_id": self.product_id,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class RecommendationResult:
    """추천 결과 데이터."""
    product_id: str
    score: float
    strategy: str
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "product_id": self.product_id,
            "score": round(self.score, 4),
            "strategy": self.strategy,
            "reason": self.reason,
        }


@dataclass
class UserProfile:
    """사용자 프로필 데이터."""
    user_id: str
    category_preferences: dict[str, float] = field(default_factory=dict)
    brand_preferences: dict[str, float] = field(default_factory=dict)
    price_range: dict[str, float] = field(default_factory=dict)
    purchase_history: list[str] = field(default_factory=list)
    view_history: list[str] = field(default_factory=list)
    search_history: list[str] = field(default_factory=list)
    wishlist: list[str] = field(default_factory=list)
    segment: str = "general"

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "category_preferences": self.category_preferences,
            "brand_preferences": self.brand_preferences,
            "price_range": self.price_range,
            "purchase_history": self.purchase_history,
            "segment": self.segment,
        }


@dataclass
class ProductVector:
    """상품 벡터 데이터."""
    product_id: str
    category: str
    brand: str = ""
    price_tier: PriceTier = PriceTier.MID
    tags: list[str] = field(default_factory=list)
    description: str = ""
    origin_country: str = ""
    popularity_score: float = 0.0

    def to_dict(self) -> dict:
        return {
            "product_id": self.product_id,
            "category": self.category,
            "brand": self.brand,
            "price_tier": self.price_tier.value,
            "tags": self.tags,
            "origin_country": self.origin_country,
            "popularity_score": self.popularity_score,
        }
