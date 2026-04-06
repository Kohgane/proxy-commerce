"""src/competitor_pricing/matcher.py — 경쟁사 상품 매칭 (Phase 111)."""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

from .tracker import CompetitorProduct, CompetitorTracker

logger = logging.getLogger(__name__)

_MOCK_PLATFORMS = ['coupang', 'naver', '11st', 'gmarket', 'auction']
_MOCK_SELLERS = ['판매자A', '판매자B', '판매자C', '공식스토어', '베스트셀러']


class MatchType(str, Enum):
    exact = 'exact'
    similar = 'similar'
    alternative = 'alternative'


@dataclass
class CompetitorMatch:
    match_id: str
    my_product_id: str
    competitor_product: CompetitorProduct
    match_score: float
    match_type: MatchType
    matched_at: str = field(
        default_factory=lambda: datetime.now(tz=timezone.utc).isoformat()
    )
    confirmed: bool = False
    rejected: bool = False


class CompetitorMatcher:
    """경쟁사 상품 자동 매칭."""

    def __init__(self, tracker: Optional[CompetitorTracker] = None) -> None:
        self._tracker = tracker or CompetitorTracker()
        self._matches: Dict[str, CompetitorMatch] = {}

    # ── 자동 검색 ─────────────────────────────────────────────────────────────

    def find_competitors(
        self,
        my_product_id: str,
        my_product: Optional[dict] = None,
        platforms: Optional[List[str]] = None,
    ) -> List[CompetitorMatch]:
        """경쟁사 자동 검색 (mock: 2–3개 생성)."""
        import random

        my_product = my_product or {}
        base_price = float(my_product.get('price', 10000))
        title = my_product.get('title', f'상품_{my_product_id}')
        target_platforms = platforms or _MOCK_PLATFORMS[:3]

        new_matches: List[CompetitorMatch] = []
        count = random.randint(2, 3)
        for i in range(count):
            platform = target_platforms[i % len(target_platforms)]
            price_variation = random.uniform(0.85, 1.15)
            cp = CompetitorProduct(
                competitor_id=str(uuid.uuid4()),
                product_id=my_product_id,
                competitor_name=f'{platform}_{_MOCK_SELLERS[i % len(_MOCK_SELLERS)]}',
                platform=platform,
                title=f'[{platform}] {title}',
                price=round(base_price * price_variation, 0),
                url=f'https://{platform}.example.com/products/{my_product_id}_{i}',
                seller_name=_MOCK_SELLERS[i % len(_MOCK_SELLERS)],
                seller_rating=round(random.uniform(3.5, 5.0), 1),
                shipping_cost=random.choice([0, 2500, 3000]),
                is_available=True,
            )
            self._tracker.add_competitor(
                {
                    'competitor_id': cp.competitor_id,
                    'product_id': cp.product_id,
                    'competitor_name': cp.competitor_name,
                    'platform': cp.platform,
                    'title': cp.title,
                    'price': cp.price,
                    'url': cp.url,
                    'seller_name': cp.seller_name,
                    'seller_rating': cp.seller_rating,
                    'shipping_cost': cp.shipping_cost,
                    'is_available': cp.is_available,
                }
            )
            score = self.calculate_match_score(my_product, cp)
            if score >= 80:
                match_type = MatchType.exact
            elif score >= 50:
                match_type = MatchType.similar
            else:
                match_type = MatchType.alternative

            match = CompetitorMatch(
                match_id=str(uuid.uuid4()),
                my_product_id=my_product_id,
                competitor_product=cp,
                match_score=score,
                match_type=match_type,
            )
            self._matches[match.match_id] = match
            new_matches.append(match)

        logger.info("경쟁사 검색 완료: %s → %d개", my_product_id, len(new_matches))
        return new_matches

    # ── 매칭 점수 계산 ────────────────────────────────────────────────────────

    def calculate_match_score(
        self, my_product: dict, competitor_product: CompetitorProduct
    ) -> float:
        """매칭 점수 계산 (0–100).

        - 제목 유사도: 40%
        - 가격 유사도: 25%
        - 카테고리 일치: 20%
        - 브랜드/모델 일치: 15%
        """
        my_title = str(my_product.get('title', '')).lower()
        comp_title = competitor_product.title.lower()
        my_price = float(my_product.get('price', 0))
        comp_price = competitor_product.price
        my_category = str(my_product.get('category', '')).lower()
        comp_category = str(competitor_product.metadata.get('category', '')).lower()

        # 제목 유사도 (keyword overlap)
        title_score = 0.0
        if my_title and comp_title:
            my_words = set(my_title.split())
            comp_words = set(comp_title.split())
            if my_words:
                overlap = len(my_words & comp_words) / len(my_words)
                title_score = min(100.0, overlap * 100)

        # 가격 유사도
        price_score = 0.0
        if my_price > 0 and comp_price > 0:
            max_price = max(my_price, comp_price)
            diff_ratio = abs(my_price - comp_price) / max_price
            price_score = max(0.0, (1 - diff_ratio) * 100)

        # 카테고리 일치
        category_score = 100.0 if (my_category and my_category == comp_category) else 0.0

        # 브랜드/모델 일치
        brand_score = 0.0
        my_brand = str(my_product.get('brand', '')).lower()
        comp_brand = str(competitor_product.metadata.get('brand', '')).lower()
        if my_brand and comp_brand and my_brand == comp_brand:
            brand_score = 100.0
        elif my_brand and my_brand in comp_title:
            brand_score = 60.0

        total = (
            title_score * 0.40
            + price_score * 0.25
            + category_score * 0.20
            + brand_score * 0.15
        )
        return round(total, 2)

    # ── 조회 / 상태 변경 ──────────────────────────────────────────────────────

    def get_matches(self, my_product_id: Optional[str] = None) -> List[CompetitorMatch]:
        """매칭 목록 반환."""
        matches = list(self._matches.values())
        if my_product_id:
            matches = [m for m in matches if m.my_product_id == my_product_id]
        return matches

    def confirm_match(self, match_id: str) -> bool:
        """매칭 확인."""
        match = self._matches.get(match_id)
        if not match:
            return False
        match.confirmed = True
        match.rejected = False
        return True

    def reject_match(self, match_id: str) -> bool:
        """매칭 거부."""
        match = self._matches.get(match_id)
        if not match:
            return False
        match.rejected = True
        match.confirmed = False
        return True
