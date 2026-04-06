"""src/virtual_inventory/aggregation.py — 재고 집계 엔진 (Phase 113)."""
from __future__ import annotations

import logging
from enum import Enum
from typing import List

logger = logging.getLogger(__name__)


class AggregationStrategy(str, Enum):
    sum_all = 'sum_all'
    sum_active = 'sum_active'
    max_single = 'max_single'
    weighted = 'weighted'
    conservative = 'conservative'


class StockAggregationEngine:
    """소싱처 재고 집계 엔진."""

    def aggregate(self, sources: list, strategy: AggregationStrategy) -> int:
        """전략에 따라 소싱처 재고 집계."""
        if not sources:
            return 0

        if strategy == AggregationStrategy.sum_all:
            return sum(s.available_qty for s in sources)

        if strategy == AggregationStrategy.sum_active:
            return sum(s.available_qty for s in sources if s.is_active)

        if strategy == AggregationStrategy.max_single:
            return max(s.available_qty for s in sources)

        if strategy == AggregationStrategy.weighted:
            return int(
                sum(
                    s.available_qty * s.reliability_score
                    for s in sources
                    if s.is_active
                )
            )

        if strategy == AggregationStrategy.conservative:
            sum_active = sum(s.available_qty for s in sources if s.is_active)
            safety = max(3, int(sum_active * 0.1))
            return max(0, sum_active - safety)

        return 0

    def calculate_safety_stock(self, product_id: str, sources: list) -> int:  # noqa: ARG002
        """기본 안전 재고: avg_lead_time_days * 1.5, 최소 3."""
        if not sources:
            return 3
        avg_lead = sum(s.lead_time_days for s in sources) / len(sources)
        return max(3, int(avg_lead * 1.5))

    def get_sellable_quantity(self, product_id: str, virtual_stock_pool) -> int:
        """풀에서 판매 가능 수량 반환."""
        vs = virtual_stock_pool.get_virtual_stock(product_id)
        if vs is None:
            return 0
        return vs.sellable
