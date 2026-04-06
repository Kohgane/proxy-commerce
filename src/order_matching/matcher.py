"""src/order_matching/matcher.py — 주문 소싱처 자동 매칭 엔진 (Phase 112).

OrderSourceMatcher: 고객 주문 접수 → 소싱처 자동 매칭 → 이행 가능 여부 판정
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class FulfillmentStatus(str, Enum):
    fulfillable = 'fulfillable'
    partially_fulfillable = 'partially_fulfillable'
    unfulfillable = 'unfulfillable'
    risky = 'risky'
    pending_check = 'pending_check'


@dataclass
class MatchResult:
    match_id: str
    order_id: str
    product_id: str
    matched_sources: List[str]
    best_source: Optional[str]
    fulfillment_status: FulfillmentStatus
    estimated_cost: float
    estimated_delivery_days: int
    risk_score: float
    matched_at: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class OrderSourceMatcher:
    """고객 주문 → 소싱처 자동 매칭 엔진."""

    def __init__(self) -> None:
        # product_id → list of source dicts {source_id, name, price, stock, active, shipping_days, score}
        self._source_registry: Dict[str, List[dict]] = {}
        # match_id → MatchResult
        self._results: Dict[str, MatchResult] = {}
        # order_id → list of MatchResult
        self._order_results: Dict[str, List[MatchResult]] = {}
        # order_id → list of product_ids (simulated order data)
        self._orders: Dict[str, List[dict]] = {}

    # ── 주문/상품 등록 (테스트/시뮬레이션용) ──────────────────────────────────

    def register_order(self, order_id: str, items: List[dict]) -> None:
        """주문 등록 (items: [{product_id, quantity}, ...])."""
        self._orders[order_id] = items

    def register_source(self, product_id: str, source: dict) -> None:
        """소싱처 등록."""
        self._source_registry.setdefault(product_id, [])
        self._source_registry[product_id].append(source)

    # ── 매칭 로직 ─────────────────────────────────────────────────────────────

    def match_order(self, order_id: str) -> List[MatchResult]:
        """주문의 모든 상품에 대해 소싱처 매칭."""
        items = self._orders.get(order_id)
        if items is None:
            # 주문이 없으면 단일 미등록 상품으로 처리
            items = [{'product_id': order_id, 'quantity': 1}]

        results: List[MatchResult] = []
        for item in items:
            product_id = item.get('product_id', '')
            quantity = item.get('quantity', 1)
            result = self.match_product(product_id, quantity, order_id=order_id)
            results.append(result)

        self._order_results[order_id] = results
        logger.info("주문 매칭 완료: order_id=%s, 상품수=%d", order_id, len(results))
        return results

    def match_product(
        self,
        product_id: str,
        quantity: int = 1,
        order_id: Optional[str] = None,
    ) -> MatchResult:
        """단일 상품 소싱처 매칭."""
        sources = self._source_registry.get(product_id, [])

        if not sources:
            result = MatchResult(
                match_id=str(uuid.uuid4()),
                order_id=order_id or '',
                product_id=product_id,
                matched_sources=[],
                best_source=None,
                fulfillment_status=FulfillmentStatus.unfulfillable,
                estimated_cost=0.0,
                estimated_delivery_days=0,
                risk_score=100.0,
                matched_at=datetime.now(tz=timezone.utc).isoformat(),
                metadata={'reason': 'no_sources_registered'},
            )
            self._results[result.match_id] = result
            return result

        # 활성 소싱처만 필터
        active_sources = [s for s in sources if s.get('active', True)]
        # 충분한 재고 소싱처
        available_sources = [
            s for s in active_sources
            if s.get('stock', 999) >= quantity
        ]

        matched_source_ids = [s['source_id'] for s in available_sources]

        if not available_sources:
            fulfillment_status = FulfillmentStatus.unfulfillable
            best_source = None
            estimated_cost = 0.0
            estimated_delivery_days = 0
            risk_score = 90.0
        else:
            # 우선순위 + 점수 기반 최적 소싱처 선택
            best = self._select_best_source(available_sources)
            best_source = best['source_id']
            estimated_cost = float(best.get('price', 0)) * quantity
            estimated_delivery_days = int(best.get('shipping_days', 3))
            risk_score = self._compute_risk_score(best, available_sources)

            if risk_score >= 61:
                fulfillment_status = FulfillmentStatus.risky
            elif len(available_sources) < len(sources):
                fulfillment_status = FulfillmentStatus.partially_fulfillable
            else:
                fulfillment_status = FulfillmentStatus.fulfillable

        result = MatchResult(
            match_id=str(uuid.uuid4()),
            order_id=order_id or '',
            product_id=product_id,
            matched_sources=matched_source_ids,
            best_source=best_source,
            fulfillment_status=fulfillment_status,
            estimated_cost=estimated_cost,
            estimated_delivery_days=estimated_delivery_days,
            risk_score=risk_score,
            matched_at=datetime.now(tz=timezone.utc).isoformat(),
        )
        self._results[result.match_id] = result
        logger.info(
            "상품 매칭: product_id=%s, status=%s, best=%s",
            product_id, fulfillment_status.value, best_source,
        )
        return result

    def match_bulk_orders(self, order_ids: List[str]) -> Dict[str, List[MatchResult]]:
        """일괄 주문 매칭."""
        bulk_results: Dict[str, List[MatchResult]] = {}
        for order_id in order_ids:
            bulk_results[order_id] = self.match_order(order_id)
        logger.info("일괄 매칭 완료: %d 주문", len(order_ids))
        return bulk_results

    # ── 조회 ──────────────────────────────────────────────────────────────────

    def get_match_result(self, order_id: str) -> Optional[List[MatchResult]]:
        """매칭 결과 조회."""
        return self._order_results.get(order_id)

    def get_match_history(
        self,
        order_id: Optional[str] = None,
        product_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[MatchResult]:
        """매칭 이력 조회."""
        results = list(self._results.values())
        if order_id:
            results = [r for r in results if r.order_id == order_id]
        if product_id:
            results = [r for r in results if r.product_id == product_id]
        results.sort(key=lambda r: r.matched_at, reverse=True)
        return results[:limit]

    def get_match_stats(self) -> dict:
        """매칭 통계."""
        all_results = list(self._results.values())
        total = len(all_results)
        if total == 0:
            return {
                'total': 0,
                'fulfillable': 0,
                'unfulfillable': 0,
                'risky': 0,
                'partially_fulfillable': 0,
                'success_rate': 0.0,
                'avg_sources_per_match': 0.0,
            }
        by_status: Dict[str, int] = {}
        source_counts = []
        for r in all_results:
            status = r.fulfillment_status.value
            by_status[status] = by_status.get(status, 0) + 1
            source_counts.append(len(r.matched_sources))

        success = by_status.get('fulfillable', 0) + by_status.get('partially_fulfillable', 0)
        return {
            'total': total,
            'fulfillable': by_status.get('fulfillable', 0),
            'unfulfillable': by_status.get('unfulfillable', 0),
            'risky': by_status.get('risky', 0),
            'partially_fulfillable': by_status.get('partially_fulfillable', 0),
            'success_rate': round(success / total * 100, 1),
            'avg_sources_per_match': round(sum(source_counts) / total, 1),
        }

    # ── 내부 헬퍼 ─────────────────────────────────────────────────────────────

    def _select_best_source(self, sources: List[dict]) -> dict:
        """우선순위 rank → 점수 순으로 최적 소싱처 선택."""
        def sort_key(s: dict):
            rank = s.get('priority_rank', 999)
            score = -s.get('score', 0)  # 점수 높을수록 우선
            return (rank, score)

        return sorted(sources, key=sort_key)[0]

    def _compute_risk_score(self, best: dict, all_available: List[dict]) -> float:
        """리스크 점수 계산 (0~100)."""
        score = 0.0
        # 가용 소싱처 수가 적을수록 리스크 ↑
        if len(all_available) == 1:
            score += 30
        elif len(all_available) == 2:
            score += 15
        # 소싱처 신뢰도 낮으면 리스크 ↑
        reliability = best.get('reliability', 1.0)
        score += (1.0 - reliability) * 40
        # 재고 여유 없으면 리스크 ↑
        stock = best.get('stock', 999)
        if stock < 10:
            score += 20
        elif stock < 50:
            score += 10
        return min(round(score, 1), 100.0)
