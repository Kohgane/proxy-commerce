"""src/source_monitor/alternative_finder.py — 대체 소싱처 검색 (Phase 108).

AlternativeSourceFinder: 문제 발생 상품의 대체 소싱처 자동 검색
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .engine import SourceProduct, SourceType

logger = logging.getLogger(__name__)


@dataclass
class AlternativeSource:
    alternative_id: str
    original_product_id: str
    source_type: SourceType
    url: str
    price: float
    seller_rating: float
    estimated_delivery_days: int
    match_score: float
    found_at: str = ''
    approved: bool = False
    metadata: Dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.found_at:
            self.found_at = datetime.now(tz=timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            'alternative_id': self.alternative_id,
            'original_product_id': self.original_product_id,
            'source_type': self.source_type.value if hasattr(self.source_type, 'value') else self.source_type,
            'url': self.url,
            'price': self.price,
            'seller_rating': self.seller_rating,
            'estimated_delivery_days': self.estimated_delivery_days,
            'match_score': self.match_score,
            'found_at': self.found_at,
            'approved': self.approved,
            'metadata': self.metadata,
        }


class AlternativeSourceFinder:
    """대체 소싱처 자동 검색기."""

    def __init__(self):
        self._alternatives: Dict[str, List[AlternativeSource]] = {}

    def find_alternatives(self, product: SourceProduct) -> List[AlternativeSource]:
        """대체 소싱처 검색 (mock)."""
        alternatives: List[AlternativeSource] = []

        # 다양한 마켓플레이스에서 대체 소싱처 mock 검색
        candidates = [
            {
                'source_type': SourceType.coupang,
                'price_factor': 1.05,
                'seller_rating': 4.5,
                'delivery_days': 2,
            },
            {
                'source_type': SourceType.naver,
                'price_factor': 1.03,
                'seller_rating': 4.3,
                'delivery_days': 3,
            },
            {
                'source_type': SourceType.taobao,
                'price_factor': 0.75,
                'seller_rating': 4.1,
                'delivery_days': 14,
            },
            {
                'source_type': SourceType.alibaba_1688,
                'price_factor': 0.65,
                'seller_rating': 4.0,
                'delivery_days': 20,
            },
        ]

        # 원래 소싱처와 동일한 마켓은 제외
        candidates = [c for c in candidates if c['source_type'] != product.source_type]

        for c in candidates[:3]:
            alt_price = round(product.current_price * c['price_factor'], 2)
            score = self._calculate_match_score(
                original_price=product.current_price,
                alt_price=alt_price,
                seller_rating=c['seller_rating'],
                delivery_days=c['delivery_days'],
                stock_stable=True,
            )
            alt = AlternativeSource(
                alternative_id=str(uuid.uuid4()),
                original_product_id=product.source_product_id,
                source_type=c['source_type'],
                url=f"https://mock-{c['source_type'].value}.example.com/product/{product.my_product_id}",
                price=alt_price,
                seller_rating=c['seller_rating'],
                estimated_delivery_days=c['delivery_days'],
                match_score=score,
            )
            alternatives.append(alt)

        # 점수 내림차순 정렬
        alternatives.sort(key=lambda a: a.match_score, reverse=True)

        self._alternatives[product.source_product_id] = alternatives
        return alternatives

    def _calculate_match_score(
        self,
        original_price: float,
        alt_price: float,
        seller_rating: float,
        delivery_days: int,
        stock_stable: bool,
    ) -> float:
        """매칭 점수 계산: 가격 유사도 40% + 셀러 평점 30% + 배송 속도 20% + 재고 안정성 10%."""
        # 가격 유사도 (가격이 비슷할수록 높은 점수, 0~1)
        if original_price > 0:
            price_diff_pct = abs(alt_price - original_price) / original_price
            price_score = max(0.0, 1.0 - price_diff_pct)
        else:
            price_score = 0.5

        # 셀러 평점 (5.0 기준 정규화)
        rating_score = min(seller_rating / 5.0, 1.0)

        # 배송 속도 (2일=1.0, 30일+=0.0)
        delivery_score = max(0.0, 1.0 - (delivery_days - 2) / 28)

        # 재고 안정성
        stock_score = 1.0 if stock_stable else 0.0

        score = (
            price_score * 0.4
            + rating_score * 0.3
            + delivery_score * 0.2
            + stock_score * 0.1
        )
        return round(score * 100, 1)

    def get_alternatives(self, source_product_id: str) -> List[AlternativeSource]:
        return self._alternatives.get(source_product_id, [])

    def approve_alternative(self, alternative_id: str, source_product_id: str) -> bool:
        alts = self._alternatives.get(source_product_id, [])
        for alt in alts:
            if alt.alternative_id == alternative_id:
                alt.approved = True
                return True
        return False

    def switch_source(self, product: SourceProduct, alternative_id: str) -> Optional[dict]:
        """소싱처 전환 (mock)."""
        alts = self._alternatives.get(product.source_product_id, [])
        for alt in alts:
            if alt.alternative_id == alternative_id and alt.approved:
                logger.info(
                    "소싱처 전환: %s → %s (%s)",
                    product.source_product_id,
                    alternative_id,
                    alt.source_type.value,
                )
                return {
                    'switched': True,
                    'new_source': alt.to_dict(),
                    'original_product_id': product.source_product_id,
                }
        return None
