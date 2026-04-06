"""src/seller_report/sourcing_performance.py — SourcingPerformanceAnalyzer (Phase 114)."""
from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class SourcingPerformance:
    source_id: str
    source_name: str
    platform: str
    total_orders: int
    success_rate: float
    avg_delivery_days: float
    avg_cost_variance: float
    quality_score: float
    issue_count: int
    reliability_trend: str  # 'improving' / 'stable' / 'declining'


class SourcingPerformanceAnalyzer:
    """소싱처별 성과 분석."""

    def __init__(self) -> None:
        self._sources = self._generate_sample_sources()

    def _generate_sample_sources(self) -> List[Dict[str, Any]]:
        platforms = ['amazon', 'taobao', '1688', 'aliexpress', 'rakuten']
        sources = []
        for i in range(1, 16):
            sources.append({
                'source_id': f'SRC_{i:03d}',
                'source_name': f'소싱처 {i}',
                'platform': random.choice(platforms),
                'total_orders': random.randint(20, 500),
                'success_rate': round(random.uniform(60, 99), 2),
                'avg_delivery_days': round(random.uniform(3, 20), 1),
                'avg_cost_variance': round(random.uniform(-5, 15), 2),
                'quality_score': round(random.uniform(2.5, 5.0), 2),
                'issue_count': random.randint(0, 30),
                'reliability_trend': random.choice(['improving', 'stable', 'declining']),
            })
        return sources

    def _to_perf(self, s: Dict[str, Any]) -> SourcingPerformance:
        return SourcingPerformance(
            source_id=s['source_id'],
            source_name=s['source_name'],
            platform=s['platform'],
            total_orders=s['total_orders'],
            success_rate=s['success_rate'],
            avg_delivery_days=s['avg_delivery_days'],
            avg_cost_variance=s['avg_cost_variance'],
            quality_score=s['quality_score'],
            issue_count=s['issue_count'],
            reliability_trend=s['reliability_trend'],
        )

    def analyze_source(self, source_id: str, period: str = 'monthly') -> Optional[SourcingPerformance]:
        """소싱처 성과 분석."""
        for s in self._sources:
            if s['source_id'] == source_id:
                return self._to_perf(s)
        return None

    def compare_sources(self, period: str = 'monthly') -> List[SourcingPerformance]:
        """소싱처 간 비교."""
        return [self._to_perf(s) for s in self._sources]

    def get_source_ranking(self) -> List[SourcingPerformance]:
        """소싱처 순위 (성공률 + 품질 기준)."""
        scored = sorted(
            self._sources,
            key=lambda s: (s['success_rate'] * 0.5 + s['quality_score'] * 10 * 0.5),
            reverse=True,
        )
        return [self._to_perf(s) for s in scored]

    def get_problematic_sources(self) -> List[SourcingPerformance]:
        """문제 소싱처 (실패율 높음 또는 배송 지연)."""
        problematic = [
            s for s in self._sources
            if s['success_rate'] < 80 or s['avg_delivery_days'] > 14 or s['issue_count'] > 15
        ]
        return [self._to_perf(s) for s in problematic]

    def get_source_recommendations(self) -> List[Dict[str, str]]:
        """소싱처별 개선/교체 제안."""
        recs = []
        for s in self._sources:
            if s['success_rate'] < 80:
                recs.append({
                    'source_id': s['source_id'],
                    'type': 'low_success_rate',
                    'message': (
                        f"{s['source_name']} 성공률 {s['success_rate']:.1f}% — "
                        f"소싱처 교체 검토 필요"
                    ),
                })
            if s['avg_delivery_days'] > 14:
                recs.append({
                    'source_id': s['source_id'],
                    'type': 'slow_delivery',
                    'message': (
                        f"{s['source_name']} 평균 배송 {s['avg_delivery_days']:.1f}일 — "
                        f"빠른 소싱처로 대체 검토"
                    ),
                })
            if s['avg_cost_variance'] > 10:
                recs.append({
                    'source_id': s['source_id'],
                    'type': 'cost_variance',
                    'message': (
                        f"{s['source_name']} 비용 편차 {s['avg_cost_variance']:.1f}% — "
                        f"가격 협상 또는 대체 소싱처 발굴"
                    ),
                })
        return recs
