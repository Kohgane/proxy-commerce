"""src/competitor_pricing/position_analyzer.py — 가격 포지션 분석기 (Phase 111)."""
from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

from .tracker import CompetitorTracker

logger = logging.getLogger(__name__)


class PositionLabel(str, Enum):
    cheapest = 'cheapest'
    below_average = 'below_average'
    average = 'average'
    above_average = 'above_average'
    most_expensive = 'most_expensive'


@dataclass
class PricePosition:
    my_product_id: str
    my_price: float
    competitor_prices: List[float]
    min_price: float
    max_price: float
    avg_price: float
    median_price: float
    my_rank: int
    total_competitors: int
    percentile: float
    position_label: PositionLabel
    analyzed_at: str = field(
        default_factory=lambda: datetime.now(tz=timezone.utc).isoformat()
    )


class PricePositionAnalyzer:
    """경쟁사 대비 가격 포지션 분석기."""

    # 퍼센타일 임계값
    _CHEAPEST_PCT = 10.0
    _BELOW_AVG_PCT = 40.0
    _ABOVE_AVG_PCT = 60.0
    _MOST_EXP_PCT = 90.0

    def __init__(self, tracker: Optional[CompetitorTracker] = None) -> None:
        self._tracker = tracker or CompetitorTracker()
        # my_product_id → my_price (등록된 상품)
        self._my_products: Dict[str, float] = {}

    # ── 상품 등록 ─────────────────────────────────────────────────────────────

    def register_my_product(self, my_product_id: str, my_price: float) -> None:
        """분석 대상 상품 등록."""
        self._my_products[my_product_id] = my_price

    # ── 포지션 분석 ───────────────────────────────────────────────────────────

    def analyze_position(
        self, my_product_id: str, channel: Optional[str] = None
    ) -> PricePosition:
        """특정 상품의 가격 포지션 분석."""
        my_price = self._my_products.get(my_product_id, 10000.0)

        competitors = self._tracker.get_competitors(my_product_id=my_product_id)
        competitor_prices = [c.price for c in competitors if c.is_available and c.price > 0]

        # 경쟁사 없으면 mock 데이터 사용
        if not competitor_prices:
            competitor_prices = [
                round(my_price * 0.9, 0),
                round(my_price * 1.1, 0),
                round(my_price * 1.2, 0),
            ]

        all_prices = sorted(competitor_prices + [my_price])
        min_price = min(all_prices)
        max_price = max(all_prices)
        avg_price = round(sum(all_prices) / len(all_prices), 2)
        median_price = statistics.median(all_prices)

        my_rank = sum(1 for p in all_prices if p < my_price) + 1
        total = len(all_prices)
        percentile = round((my_rank - 1) / total * 100, 2) if total > 1 else 50.0

        position_label = self._label_from_percentile(percentile)

        return PricePosition(
            my_product_id=my_product_id,
            my_price=my_price,
            competitor_prices=competitor_prices,
            min_price=min_price,
            max_price=max_price,
            avg_price=avg_price,
            median_price=median_price,
            my_rank=my_rank,
            total_competitors=len(competitor_prices),
            percentile=percentile,
            position_label=position_label,
        )

    def analyze_all_positions(
        self, channel: Optional[str] = None
    ) -> Dict[str, PricePosition]:
        """등록된 모든 상품의 포지션 분석."""
        # 트래커에서 유니크 product_id 수집
        all_product_ids = set(self._my_products.keys())
        for cp in self._tracker.get_competitors():
            if cp.product_id:
                all_product_ids.add(cp.product_id)
                if cp.product_id not in self._my_products:
                    self._my_products[cp.product_id] = cp.price

        return {pid: self.analyze_position(pid, channel) for pid in all_product_ids}

    # ── 분포 / 요약 ───────────────────────────────────────────────────────────

    def get_price_distribution(self, my_product_id: str) -> List[dict]:
        """가격 분포 히스토그램 (5개 구간)."""
        position = self.analyze_position(my_product_id)
        all_prices = position.competitor_prices + [position.my_price]
        if not all_prices:
            return []

        min_p = min(all_prices)
        max_p = max(all_prices)
        if min_p == max_p:
            return [{'range_start': min_p, 'range_end': max_p, 'count': len(all_prices)}]

        bucket_size = (max_p - min_p) / 5
        buckets = []
        for i in range(5):
            start = min_p + i * bucket_size
            end = min_p + (i + 1) * bucket_size
            count = sum(1 for p in all_prices if start <= p < end)
            if i == 4:
                count = sum(1 for p in all_prices if start <= p <= end)
            buckets.append(
                {'range_start': round(start, 0), 'range_end': round(end, 0), 'count': count}
            )
        return buckets

    def get_position_summary(self) -> Dict[str, int]:
        """포지션 레이블별 상품 수 요약."""
        positions = self.analyze_all_positions()
        summary: Dict[str, int] = {label.value: 0 for label in PositionLabel}
        for pos in positions.values():
            summary[pos.position_label.value] += 1
        return summary

    # ── 가격 전쟁 감지 ────────────────────────────────────────────────────────

    def detect_price_war(self, my_product_id: Optional[str] = None) -> List[str]:
        """가격 전쟁 중인 상품 목록 반환 (이력에서 3회 이상 가격 하락)."""
        MIN_DROPS = 3
        war_products: List[str] = []

        product_ids = [my_product_id] if my_product_id else list(
            {cp.product_id for cp in self._tracker.get_competitors()}
        )

        for pid in product_ids:
            competitors = self._tracker.get_competitors(my_product_id=pid)
            for cp in competitors:
                history = self._tracker.get_price_history(cp.competitor_id)
                if len(history) < MIN_DROPS + 1:
                    continue
                drops = sum(
                    1
                    for i in range(1, len(history))
                    if history[i]['price'] < history[i - 1]['price']
                )
                if drops >= MIN_DROPS:
                    war_products.append(pid)
                    break

        return list(set(war_products))

    # ── 내부 헬퍼 ────────────────────────────────────────────────────────────

    def _label_from_percentile(self, percentile: float) -> PositionLabel:
        if percentile <= self._CHEAPEST_PCT:
            return PositionLabel.cheapest
        if percentile <= self._BELOW_AVG_PCT:
            return PositionLabel.below_average
        if percentile <= self._ABOVE_AVG_PCT:
            return PositionLabel.average
        if percentile <= self._MOST_EXP_PCT:
            return PositionLabel.above_average
        return PositionLabel.most_expensive
