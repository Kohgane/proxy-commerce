"""src/virtual_inventory/source_allocator.py — 소싱처 할당 엔진 (Phase 113)."""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class AllocationStrategy(str, Enum):
    cheapest_first = 'cheapest_first'
    fastest_first = 'fastest_first'
    single_source = 'single_source'
    balanced = 'balanced'
    reliability_first = 'reliability_first'


@dataclass
class SourceAllocation:
    source_id: str
    allocated_qty: int
    unit_cost: float
    currency: str
    estimated_delivery_days: int


@dataclass
class AllocationResult:
    allocation_id: str
    product_id: str
    quantity: int
    allocated_sources: List[SourceAllocation] = field(default_factory=list)
    total_cost: float = 0.0
    estimated_delivery_days: int = 0
    strategy_used: str = ''
    status: str = 'pending'
    allocated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class SourceAllocator:
    """소싱처 할당 엔진."""

    def __init__(self) -> None:
        self._allocations: Dict[str, AllocationResult] = {}
        self._stock_pool = None

    def set_stock_pool(self, pool) -> None:
        self._stock_pool = pool

    # ── 할당 ──────────────────────────────────────────────────────────────────

    def allocate(
        self,
        product_id: str,
        quantity: int,
        strategy: AllocationStrategy = AllocationStrategy.cheapest_first,
    ) -> AllocationResult:
        """소싱처 할당 수행."""
        sources = []
        if self._stock_pool is not None:
            sources = self._stock_pool.get_source_stocks(product_id)

        active = [s for s in sources if s.is_active and s.available_qty > 0]

        sorted_sources = self._sort_sources(active, strategy)

        allocated: List[SourceAllocation] = []
        remaining = quantity
        for src in sorted_sources:
            if remaining <= 0:
                break
            qty = min(src.available_qty, remaining)
            allocated.append(
                SourceAllocation(
                    source_id=src.source_id,
                    allocated_qty=qty,
                    unit_cost=src.price,
                    currency=src.currency,
                    estimated_delivery_days=src.lead_time_days,
                )
            )
            remaining -= qty

        total_cost = sum(a.allocated_qty * a.unit_cost for a in allocated)
        est_days = max((a.estimated_delivery_days for a in allocated), default=0)

        result = AllocationResult(
            allocation_id=str(uuid.uuid4()),
            product_id=product_id,
            quantity=quantity,
            allocated_sources=allocated,
            total_cost=total_cost,
            estimated_delivery_days=est_days,
            strategy_used=strategy.value,
            status='pending',
            allocated_at=datetime.now(timezone.utc),
        )
        self._allocations[result.allocation_id] = result
        return result

    def _sort_sources(self, sources: list, strategy: AllocationStrategy) -> list:
        if strategy == AllocationStrategy.cheapest_first:
            return sorted(sources, key=lambda s: s.price)

        if strategy == AllocationStrategy.fastest_first:
            return sorted(sources, key=lambda s: s.lead_time_days)

        if strategy == AllocationStrategy.reliability_first:
            return sorted(sources, key=lambda s: s.reliability_score, reverse=True)

        if strategy == AllocationStrategy.single_source:
            # Pick the single source with the most stock
            return sorted(sources, key=lambda s: s.available_qty, reverse=True)[:1]

        if strategy == AllocationStrategy.balanced:
            # score = (1/price_norm * 0.4) + (1/lead_time_norm * 0.3) + (reliability * 0.3)
            if not sources:
                return sources
            max_price = max(s.price for s in sources) or 1
            max_lead = max(s.lead_time_days for s in sources) or 1

            def _score(s):
                price_norm = s.price / max_price
                lead_norm = s.lead_time_days / max_lead
                return (1 / price_norm * 0.4) + (1 / lead_norm * 0.3) + (s.reliability_score * 0.3)

            return sorted(sources, key=_score, reverse=True)

        return sources

    # ── 조회 ──────────────────────────────────────────────────────────────────

    def get_allocation(self, allocation_id: str) -> Optional[AllocationResult]:
        return self._allocations.get(allocation_id)

    def get_allocation_history(
        self, product_id: Optional[str] = None, limit: int = 50
    ) -> List[AllocationResult]:
        history = list(self._allocations.values())
        if product_id is not None:
            history = [a for a in history if a.product_id == product_id]
        return history[-limit:]

    def cancel_allocation(self, allocation_id: str) -> bool:
        result = self._allocations.get(allocation_id)
        if result is None:
            return False
        result.status = 'cancelled'
        return True
