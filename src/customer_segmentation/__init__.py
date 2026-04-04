"""src/customer_segmentation/ — Phase 86: 고객 세그멘테이션."""
from __future__ import annotations

from .models import Segment
from .segment_manager import SegmentManager
from .segment_rules import SegmentRule, PurchaseFrequencyRule, SpendingRule, RecencyRule, GeographicRule
from .segment_analyzer import SegmentAnalyzer
from .segment_exporter import SegmentExporter
from .auto_segmenter import AutoSegmenter

__all__ = [
    "Segment",
    "SegmentManager",
    "SegmentRule",
    "PurchaseFrequencyRule",
    "SpendingRule",
    "RecencyRule",
    "GeographicRule",
    "SegmentAnalyzer",
    "SegmentExporter",
    "AutoSegmenter",
]
