"""src/ai_recommendation/__init__.py — Phase 94: AI 기반 상품 추천 시스템."""
from __future__ import annotations

from .auto_recommender import AutoRecommender
from .collaborative_filter import AdvancedCollaborativeFilter
from .content_based_filter import AdvancedContentBasedFilter
from .cross_sell import CrossSellEngine
from .feedback_loop import FeedbackLoop
from .personalization import PersonalizationEngine
from .recommendation_engine import AIRecommendationEngine
from .recommendation_model import (
    EventType,
    PriceTier,
    ProductVector,
    RecommendationResult,
    UserEvent,
    UserProfile,
)
from .trending_analyzer import AITrendingAnalyzer

__all__ = [
    "AIRecommendationEngine",
    "AdvancedCollaborativeFilter",
    "AdvancedContentBasedFilter",
    "PersonalizationEngine",
    "AITrendingAnalyzer",
    "CrossSellEngine",
    "FeedbackLoop",
    "AutoRecommender",
    "UserEvent",
    "EventType",
    "RecommendationResult",
    "UserProfile",
    "ProductVector",
    "PriceTier",
]
