"""src/product_comparison/ — Phase 87: 상품 비교 도구."""
from __future__ import annotations

from .models import ComparisonSet
from .comparison_engine import ComparisonEngine
from .attribute_comparer import AttributeComparer
from .price_comparer import PriceComparer
from .feature_matrix import FeatureMatrix
from .comparison_score import ComparisonScore
from .comparison_history import ComparisonHistory

__all__ = [
    "ComparisonSet",
    "ComparisonEngine",
    "AttributeComparer",
    "PriceComparer",
    "FeatureMatrix",
    "ComparisonScore",
    "ComparisonHistory",
]
