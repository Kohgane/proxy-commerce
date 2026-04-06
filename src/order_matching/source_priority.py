"""src/order_matching/source_priority.py — 소싱처 우선순위 관리 (Phase 112).

SourcePriorityManager: 상품별 소싱처 우선순위 설정 + 자동 순위 산정
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# 가중치
WEIGHT_PRICE = 0.40
WEIGHT_RELIABILITY = 0.30
WEIGHT_SHIPPING_SPEED = 0.20
WEIGHT_QUALITY = 0.10


@dataclass
class ScoringFactors:
    price_score: float = 0.0
    reliability_score: float = 0.0
    shipping_speed_score: float = 0.0
    quality_score: float = 0.0
    weighted_total: float = 0.0


@dataclass
class SourcePriority:
    product_id: str
    source_id: str
    priority_rank: int
    is_primary: bool
    is_backup: bool
    score: float
    scoring_factors: ScoringFactors
    last_updated: str


class SourcePriorityManager:
    """소싱처 우선순위 관리자."""

    def __init__(self) -> None:
        # (product_id, source_id) → SourcePriority
        self._priorities: Dict[tuple, SourcePriority] = {}
        # source_id → source info dict {price, reliability, shipping_days, quality, active}
        self._source_info: Dict[str, dict] = {}
        # 강등 이력
        self._demotion_history: List[dict] = []

    # ── 소싱처 정보 등록 ──────────────────────────────────────────────────────

    def register_source_info(self, source_id: str, info: dict) -> None:
        """소싱처 정보 등록 (가격, 신뢰도, 배송일 등)."""
        self._source_info[source_id] = dict(info)

    # ── 우선순위 설정/조회 ─────────────────────────────────────────────────────

    def set_priority(
        self, product_id: str, source_id: str, priority_rank: int
    ) -> SourcePriority:
        """우선순위 설정."""
        key = (product_id, source_id)
        existing = self._priorities.get(key)
        factors = existing.scoring_factors if existing else ScoringFactors()
        score = existing.score if existing else 0.0

        priority = SourcePriority(
            product_id=product_id,
            source_id=source_id,
            priority_rank=priority_rank,
            is_primary=(priority_rank == 1),
            is_backup=(priority_rank > 1),
            score=score,
            scoring_factors=factors,
            last_updated=datetime.now(tz=timezone.utc).isoformat(),
        )
        self._priorities[key] = priority
        logger.info(
            "우선순위 설정: product=%s, source=%s, rank=%d",
            product_id, source_id, priority_rank,
        )
        return priority

    def get_priorities(self, product_id: str) -> List[SourcePriority]:
        """소싱처 우선순위 목록 반환 (순위 오름차순)."""
        priorities = [
            p for (pid, _), p in self._priorities.items() if pid == product_id
        ]
        return sorted(priorities, key=lambda p: p.priority_rank)

    def get_primary_source(self, product_id: str) -> Optional[SourcePriority]:
        """주 소싱처 반환 (priority_rank=1)."""
        priorities = self.get_priorities(product_id)
        for p in priorities:
            if p.is_primary:
                return p
        return priorities[0] if priorities else None

    def get_backup_sources(self, product_id: str) -> List[SourcePriority]:
        """백업 소싱처 목록 반환 (priority_rank>1)."""
        return [p for p in self.get_priorities(product_id) if p.is_backup]

    # ── 자동 순위 산정 ─────────────────────────────────────────────────────────

    def auto_rank_sources(self, product_id: str) -> List[SourcePriority]:
        """자동 순위 산정: 가격40% + 신뢰도30% + 배송속도20% + 품질10%."""
        # 이 상품에 연결된 소싱처 수집
        source_ids = list({
            sid for (pid, sid) in self._priorities if pid == product_id
        })
        if not source_ids:
            # 등록된 소싱처 정보에서 검색
            source_ids = list(self._source_info.keys())

        if not source_ids:
            return []

        scored: List[tuple] = []
        for source_id in source_ids:
            info = self._source_info.get(source_id, {})
            factors = self._compute_scoring_factors(source_id, source_ids, info)
            scored.append((source_id, factors))

        # weighted_total 내림차순 정렬
        scored.sort(key=lambda x: x[1].weighted_total, reverse=True)

        priorities = []
        for rank, (source_id, factors) in enumerate(scored, start=1):
            priority = SourcePriority(
                product_id=product_id,
                source_id=source_id,
                priority_rank=rank,
                is_primary=(rank == 1),
                is_backup=(rank > 1),
                score=factors.weighted_total,
                scoring_factors=factors,
                last_updated=datetime.now(tz=timezone.utc).isoformat(),
            )
            self._priorities[(product_id, source_id)] = priority
            priorities.append(priority)

        logger.info("자동 순위 산정: product=%s, sources=%d", product_id, len(priorities))
        return priorities

    # ── 승격 / 강등 ───────────────────────────────────────────────────────────

    def promote_backup(self, product_id: str, source_id: str) -> Optional[SourcePriority]:
        """백업 소싱처를 주 소싱처로 승격."""
        key = (product_id, source_id)
        if key not in self._priorities:
            return None
        # 기존 주 소싱처를 rank=2로 강등
        old_primary = self.get_primary_source(product_id)
        if old_primary and old_primary.source_id != source_id:
            old_key = (product_id, old_primary.source_id)
            self._priorities[old_key] = SourcePriority(
                product_id=old_primary.product_id,
                source_id=old_primary.source_id,
                priority_rank=2,
                is_primary=False,
                is_backup=True,
                score=old_primary.score,
                scoring_factors=old_primary.scoring_factors,
                last_updated=datetime.now(tz=timezone.utc).isoformat(),
            )
        # 대상 소싱처를 rank=1로 승격
        target = self._priorities[key]
        promoted = SourcePriority(
            product_id=target.product_id,
            source_id=target.source_id,
            priority_rank=1,
            is_primary=True,
            is_backup=False,
            score=target.score,
            scoring_factors=target.scoring_factors,
            last_updated=datetime.now(tz=timezone.utc).isoformat(),
        )
        self._priorities[key] = promoted
        logger.info("소싱처 승격: product=%s, source=%s", product_id, source_id)
        return promoted

    def demote_source(
        self, product_id: str, source_id: str, reason: str
    ) -> Optional[SourcePriority]:
        """소싱처 강등 (문제 발생 시 우선순위 낮춤)."""
        key = (product_id, source_id)
        if key not in self._priorities:
            return None
        existing = self._priorities[key]
        # 현재 최하위 rank 파악
        all_priorities = self.get_priorities(product_id)
        max_rank = max((p.priority_rank for p in all_priorities), default=1)

        demoted = SourcePriority(
            product_id=existing.product_id,
            source_id=existing.source_id,
            priority_rank=max_rank + 1,
            is_primary=False,
            is_backup=True,
            score=existing.score,
            scoring_factors=existing.scoring_factors,
            last_updated=datetime.now(tz=timezone.utc).isoformat(),
        )
        self._priorities[key] = demoted
        self._demotion_history.append({
            'product_id': product_id,
            'source_id': source_id,
            'reason': reason,
            'old_rank': existing.priority_rank,
            'new_rank': demoted.priority_rank,
            'at': demoted.last_updated,
        })
        logger.info(
            "소싱처 강등: product=%s, source=%s, reason=%s", product_id, source_id, reason
        )
        return demoted

    def get_demotion_history(self) -> List[dict]:
        """강등 이력 반환."""
        return list(self._demotion_history)

    # ── 내부 헬퍼 ─────────────────────────────────────────────────────────────

    def _compute_scoring_factors(
        self, source_id: str, all_source_ids: List[str], info: dict
    ) -> ScoringFactors:
        """가중 점수 계산."""
        # 가격 점수: 같은 상품 소싱처 중 최저가일수록 높음 (0~100)
        prices = []
        for sid in all_source_ids:
            p = self._source_info.get(sid, {}).get('price', 0)
            if p > 0:
                prices.append(p)
        my_price = float(info.get('price', 0))
        if prices and my_price > 0:
            min_price = min(prices)
            max_price = max(prices)
            if max_price > min_price:
                price_score = (1 - (my_price - min_price) / (max_price - min_price)) * 100
            else:
                price_score = 100.0
        else:
            price_score = 50.0

        reliability_score = float(info.get('reliability', 0.8)) * 100

        # 배송 속도 점수: 빠를수록 높음 (최소 1일, 최대 30일 기준)
        shipping_days = float(info.get('shipping_days', 7))
        shipping_speed_score = max(0.0, (30 - shipping_days) / 29 * 100)

        quality_score = float(info.get('quality_score', 0.8)) * 100

        weighted_total = (
            price_score * WEIGHT_PRICE
            + reliability_score * WEIGHT_RELIABILITY
            + shipping_speed_score * WEIGHT_SHIPPING_SPEED
            + quality_score * WEIGHT_QUALITY
        )
        return ScoringFactors(
            price_score=round(price_score, 1),
            reliability_score=round(reliability_score, 1),
            shipping_speed_score=round(shipping_speed_score, 1),
            quality_score=round(quality_score, 1),
            weighted_total=round(weighted_total, 1),
        )
