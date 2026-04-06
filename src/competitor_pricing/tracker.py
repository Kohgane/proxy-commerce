"""src/competitor_pricing/tracker.py — 경쟁사 상품 가격 추적기 (Phase 111)."""
from __future__ import annotations

import logging
import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

MAX_RETRIES = 3


@dataclass
class CompetitorProduct:
    competitor_id: str
    product_id: str
    competitor_name: str
    platform: str
    title: str
    price: float
    currency: str = 'KRW'
    url: str = ''
    seller_name: str = ''
    seller_rating: float = 0.0
    shipping_cost: float = 0.0
    is_available: bool = True
    last_checked_at: str = field(
        default_factory=lambda: datetime.now(tz=timezone.utc).isoformat()
    )
    check_interval_minutes: int = 240
    metadata: Dict[str, Any] = field(default_factory=dict)


class CompetitorTracker:
    """경쟁사 상품 가격 추적기."""

    def __init__(self) -> None:
        self._competitors: Dict[str, CompetitorProduct] = {}
        self._price_history: Dict[str, List[dict]] = {}

    # ── 등록 / 삭제 ──────────────────────────────────────────────────────────

    def add_competitor(self, product_data: dict) -> CompetitorProduct:
        """경쟁사 상품을 등록한다."""
        competitor_id = product_data.get('competitor_id') or str(uuid.uuid4())
        product = CompetitorProduct(
            competitor_id=competitor_id,
            product_id=product_data.get('product_id', ''),
            competitor_name=product_data.get('competitor_name', ''),
            platform=product_data.get('platform', 'unknown'),
            title=product_data.get('title', ''),
            price=float(product_data.get('price', 0.0)),
            currency=product_data.get('currency', 'KRW'),
            url=product_data.get('url', ''),
            seller_name=product_data.get('seller_name', ''),
            seller_rating=float(product_data.get('seller_rating', 0.0)),
            shipping_cost=float(product_data.get('shipping_cost', 0.0)),
            is_available=bool(product_data.get('is_available', True)),
            check_interval_minutes=int(product_data.get('check_interval_minutes', 240)),
            metadata=product_data.get('metadata', {}),
        )
        self._competitors[competitor_id] = product
        self._price_history.setdefault(competitor_id, [])
        self._record_price(competitor_id, product.price)
        logger.info("경쟁사 등록: %s (%s)", competitor_id, product.competitor_name)
        return product

    def remove_competitor(self, competitor_id: str) -> bool:
        """경쟁사를 제거한다."""
        if competitor_id not in self._competitors:
            return False
        del self._competitors[competitor_id]
        self._price_history.pop(competitor_id, None)
        logger.info("경쟁사 삭제: %s", competitor_id)
        return True

    # ── 가격 체크 ─────────────────────────────────────────────────────────────

    def check_competitor(self, competitor_id: str) -> Optional[CompetitorProduct]:
        """단일 경쟁사 가격 체크 (mock: ±5% 변동 시뮬레이션)."""
        product = self._competitors.get(competitor_id)
        if product is None:
            logger.warning("경쟁사 없음: %s", competitor_id)
            return None

        # 실제 환경에서는 네트워크 오류 등 일시적 장애를 재시도하지만,
        # mock 구현에서는 성공을 보장한다.
        for attempt in range(MAX_RETRIES):
            try:
                variation = random.uniform(-0.05, 0.05)
                new_price = max(0.0, round(product.price * (1 + variation), 0))
                product.price = new_price
                product.last_checked_at = datetime.now(tz=timezone.utc).isoformat()
                self._record_price(competitor_id, new_price)
                logger.debug("경쟁사 가격 체크 완료: %s → %.0f", competitor_id, new_price)
                return product
            except Exception as exc:  # noqa: BLE001
                logger.warning("가격 체크 시도 %d/%d 실패: %s", attempt + 1, MAX_RETRIES, exc)

        logger.error("경쟁사 가격 체크 실패 (최대 재시도 초과): %s", competitor_id)
        return None

    def check_all(self) -> List[CompetitorProduct]:
        """전체 경쟁사 가격 체크."""
        results: List[CompetitorProduct] = []
        for competitor_id in list(self._competitors):
            result = self.check_competitor(competitor_id)
            if result is not None:
                results.append(result)
        return results

    # ── 조회 ─────────────────────────────────────────────────────────────────

    def get_competitors(self, my_product_id: Optional[str] = None) -> List[CompetitorProduct]:
        """경쟁사 목록 반환 (my_product_id 로 필터링 가능)."""
        competitors = list(self._competitors.values())
        if my_product_id:
            competitors = [c for c in competitors if c.product_id == my_product_id]
        return competitors

    def get_competitor(self, competitor_id: str) -> Optional[CompetitorProduct]:
        """단일 경쟁사 반환."""
        return self._competitors.get(competitor_id)

    def get_price_history(
        self, competitor_id: str, period: Optional[str] = None
    ) -> List[dict]:
        """가격 이력 반환.

        period 는 현재 무시하고 전체 이력을 반환한다 (mock).
        """
        history = self._price_history.get(competitor_id, [])
        return list(history)

    # ── 내부 헬퍼 ────────────────────────────────────────────────────────────

    def _record_price(self, competitor_id: str, price: float) -> None:
        self._price_history.setdefault(competitor_id, []).append(
            {
                'price': price,
                'checked_at': datetime.now(tz=timezone.utc).isoformat(),
            }
        )
