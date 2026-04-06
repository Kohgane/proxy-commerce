"""src/sourcing_discovery/opportunity_finder.py — 소싱 기회 발굴 (Phase 115)."""
from __future__ import annotations

import logging
import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class OpportunityStatus(str, Enum):
    discovered = 'discovered'
    evaluating = 'evaluating'
    approved = 'approved'
    rejected = 'rejected'
    listed = 'listed'


class DiscoveryMethod(str, Enum):
    trend_based = 'trend_based'
    competitor_gap = 'competitor_gap'
    margin_opportunity = 'margin_opportunity'
    seasonal = 'seasonal'
    supplier_recommendation = 'supplier_recommendation'
    cross_platform = 'cross_platform'


@dataclass
class SourcingOpportunity:
    opportunity_id: str
    product_name: str
    category: str
    source_platform: str
    source_url: str
    source_price: float
    source_currency: str
    estimated_selling_price: float
    estimated_margin_rate: float
    estimated_monthly_demand: int
    competition_level: str
    opportunity_score: float
    trend_data: Dict[str, Any]
    risk_factors: List[str]
    discovery_method: DiscoveryMethod
    status: OpportunityStatus
    discovered_at: datetime
    metadata: Dict[str, Any]


_SAMPLE_PRODUCTS = [
    ('무선이어폰 프리미엄', '전자기기', 'taobao', 15.0, 'CNY'),
    ('스마트워치 밴드', '전자기기', '1688', 5.0, 'CNY'),
    ('레티놀앰플 30ml', '뷰티', 'taobao', 8.0, 'CNY'),
    ('요가매트 6mm', '스포츠', 'alibaba', 6.0, 'CNY'),
    ('세라믹프라이팬 28cm', '주방용품', '1688', 12.0, 'CNY'),
    ('고양이자동화장실', '반려동물', 'taobao', 45.0, 'CNY'),
    ('콜라겐파우더 500g', '건강식품', 'alibaba', 10.0, 'CNY'),
    ('오피스체어 메쉬', '가구/인테리어', '1688', 80.0, 'CNY'),
    ('카고바지 남성', '패션', 'taobao', 20.0, 'CNY'),
    ('포터블모니터 15인치', '전자기기', 'alibaba', 55.0, 'CNY'),
    ('두피에센스 100ml', '뷰티', 'taobao', 12.0, 'CNY'),
    ('필라테스링 세트', '스포츠', '1688', 4.0, 'CNY'),
    ('에스프레소머신', '주방용품', 'alibaba', 35.0, 'CNY'),
    ('자동급식기 스마트', '반려동물', 'taobao', 25.0, 'CNY'),
    ('글루타치온 60캡슐', '건강식품', 'alibaba', 8.0, 'CNY'),
    ('아크릴선반 세트', '가구/인테리어', '1688', 7.0, 'CNY'),
    ('크롭자켓 여성', '패션', 'taobao', 18.0, 'CNY'),
    ('노이즈캔슬링헤드폰', '전자기기', 'alibaba', 22.0, 'CNY'),
    ('젤네일키트 10색', '뷰티', 'taobao', 15.0, 'CNY'),
    ('테니스라켓 카본', '스포츠', '1688', 18.0, 'CNY'),
]


def _generate_opportunity(product: tuple, method: DiscoveryMethod) -> SourcingOpportunity:
    name, category, platform, price, currency = product
    krw_price = price * 185
    selling_price = krw_price * 2.5
    total_cost = krw_price * (1 + 0.08 + 0.10 + 0.10) + 5000
    margin = (selling_price - total_cost) / selling_price * 100

    score = min(100.0, max(0.0, margin * 1.5 + random.uniform(-10, 10)))
    demand = random.randint(20, 300)
    risk_factors = []
    if price > 30:
        risk_factors.append('높은 소싱가격')
    if margin < 20:
        risk_factors.append('낮은 마진율')
    if random.random() > 0.6:
        risk_factors.append('경쟁 심화 가능성')

    return SourcingOpportunity(
        opportunity_id=str(uuid.uuid4())[:12],
        product_name=name,
        category=category,
        source_platform=platform,
        source_url=f'https://{platform}.com/item/{random.randint(10000, 99999)}',
        source_price=price,
        source_currency=currency,
        estimated_selling_price=round(selling_price, 0),
        estimated_margin_rate=round(margin, 1),
        estimated_monthly_demand=demand,
        competition_level=random.choice(['low', 'medium', 'high']),
        opportunity_score=round(score, 1),
        trend_data={'growth_rate': random.uniform(10, 80), 'direction': 'rising'},
        risk_factors=risk_factors,
        discovery_method=method,
        status=OpportunityStatus.discovered,
        discovered_at=datetime.now(),
        metadata={'auto_generated': True},
    )


class SourcingOpportunityFinder:
    """소싱 기회 발굴기."""

    def __init__(self) -> None:
        self._opportunities: Dict[str, SourcingOpportunity] = {}

    def discover_opportunities(
        self,
        method: str = None,
        category: str = None,
        limit: int = 20,
    ) -> List[SourcingOpportunity]:
        """기회 발굴."""
        methods = [
            DiscoveryMethod.trend_based,
            DiscoveryMethod.competitor_gap,
            DiscoveryMethod.margin_opportunity,
            DiscoveryMethod.seasonal,
            DiscoveryMethod.supplier_recommendation,
            DiscoveryMethod.cross_platform,
        ]
        target_method = DiscoveryMethod(method) if method else random.choice(methods)

        products = _SAMPLE_PRODUCTS[:]
        if category:
            products = [p for p in products if p[1] == category]
        if not products:
            products = _SAMPLE_PRODUCTS[:]

        max_count = min(10, len(products))
        min_count = min(5, max_count)
        count = min(limit, random.randint(min_count, max_count))
        selected = random.sample(products, min(count, len(products)))

        new_opps = []
        for product in selected:
            opp = _generate_opportunity(product, target_method)
            self._opportunities[opp.opportunity_id] = opp
            new_opps.append(opp)

        return new_opps

    def evaluate_opportunity(self, opportunity_id: str) -> Dict[str, Any]:
        """기회 평가."""
        opp = self._opportunities.get(opportunity_id)
        if opp is None:
            raise ValueError(f'기회를 찾을 수 없습니다: {opportunity_id}')
        opp.status = OpportunityStatus.evaluating
        return {
            'opportunity_id': opportunity_id,
            'status': opp.status.value,
            'evaluation': {
                'market_size_score': random.uniform(60, 100),
                'competition_score': random.uniform(40, 90),
                'margin_score': opp.estimated_margin_rate,
                'demand_score': min(100, opp.estimated_monthly_demand / 3),
                'overall_score': opp.opportunity_score,
            },
            'recommendation': '승인 권장' if opp.opportunity_score >= 70 else '추가 검토 필요',
            'evaluated_at': datetime.now().isoformat(),
        }

    def approve_opportunity(self, opportunity_id: str) -> SourcingOpportunity:
        """기회 승인."""
        opp = self._opportunities.get(opportunity_id)
        if opp is None:
            raise ValueError(f'기회를 찾을 수 없습니다: {opportunity_id}')
        opp.status = OpportunityStatus.approved
        return opp

    def reject_opportunity(self, opportunity_id: str, reason: str = '') -> SourcingOpportunity:
        """기회 거절."""
        opp = self._opportunities.get(opportunity_id)
        if opp is None:
            raise ValueError(f'기회를 찾을 수 없습니다: {opportunity_id}')
        opp.status = OpportunityStatus.rejected
        opp.metadata['reject_reason'] = reason
        return opp

    def get_opportunities(
        self,
        status: str = None,
        method: str = None,
        sort_by: str = 'opportunity_score',
    ) -> List[SourcingOpportunity]:
        """기회 목록 조회."""
        opps = list(self._opportunities.values())
        if status:
            opps = [o for o in opps if o.status.value == status]
        if method:
            opps = [o for o in opps if o.discovery_method.value == method]
        reverse = True
        if sort_by == 'opportunity_score':
            opps.sort(key=lambda x: x.opportunity_score, reverse=reverse)
        elif sort_by == 'estimated_margin_rate':
            opps.sort(key=lambda x: x.estimated_margin_rate, reverse=reverse)
        elif sort_by == 'estimated_monthly_demand':
            opps.sort(key=lambda x: x.estimated_monthly_demand, reverse=reverse)
        return opps

    def get_opportunity(self, opportunity_id: str) -> Optional[SourcingOpportunity]:
        """단일 기회 조회."""
        return self._opportunities.get(opportunity_id)
