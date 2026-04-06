"""src/channel_sync/publishers/coupang.py — 쿠팡 퍼블리셔 mock 구현 (Phase 109)."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Optional

from .base import ChannelPublisher, ListingState, ListingStatus, PublishResult

logger = logging.getLogger(__name__)

# 쿠팡 카테고리 매핑 (소싱처 카테고리 → 쿠팡 카테고리 ID)
COUPANG_CATEGORY_MAP: Dict[str, str] = {
    'electronics': '56137',
    'fashion': '15685',
    'beauty': '56136',
    'home': '56145',
    'food': '56152',
    'sports': '56148',
    'toys': '56153',
    'books': '56149',
    'default': '56137',
}

# 쿠팡 수수료율 (카테고리별)
COUPANG_FEE_RATES: Dict[str, float] = {
    '56137': 0.10,  # 전자제품
    '15685': 0.12,  # 패션
    '56136': 0.11,  # 뷰티
    '56145': 0.08,  # 홈
    '56152': 0.07,  # 식품
    'default': 0.10,
}


class CoupangPublisher(ChannelPublisher):
    """쿠팡 상품 관리 mock 퍼블리셔."""

    channel_name = 'coupang'

    def __init__(self):
        self._listings: Dict[str, ListingStatus] = {}
        self._is_healthy: bool = True

    # ── 핵심 메서드 ──────────────────────────────────────────────────────────

    def publish(self, product_data: dict) -> PublishResult:
        """쿠팡에 상품 등록."""
        try:
            listing_id = str(uuid.uuid4())
            channel_listing_id = f'coupang-{uuid.uuid4().hex[:8]}'

            category = product_data.get('category', 'default')
            coupang_category = COUPANG_CATEGORY_MAP.get(category, COUPANG_CATEGORY_MAP['default'])
            fee_rate = COUPANG_FEE_RATES.get(coupang_category, COUPANG_FEE_RATES['default'])
            sale_price = self._apply_fee(product_data.get('price', 0), fee_rate)

            listing = ListingStatus(
                listing_id=listing_id,
                channel=self.channel_name,
                product_id=product_data.get('product_id', ''),
                state=ListingState.active,
                channel_listing_id=channel_listing_id,
                title=product_data.get('title', ''),
                price=sale_price,
                stock=product_data.get('stock', 0),
                last_synced_at=datetime.now(tz=timezone.utc).isoformat(),
                metadata={
                    'coupang_category': coupang_category,
                    'fee_rate': fee_rate,
                    'rocket_delivery': product_data.get('rocket_delivery', False),
                },
            )
            self._listings[listing_id] = listing

            logger.info("쿠팡 상품 등록: %s → %s", product_data.get('product_id'), listing_id)
            return PublishResult(
                success=True,
                listing_id=listing_id,
                channel=self.channel_name,
                message='쿠팡 상품 등록 완료',
                raw_response={'channel_listing_id': channel_listing_id, 'category': coupang_category},
            )
        except Exception as exc:
            logger.error("쿠팡 publish 오류: %s", exc)
            return PublishResult(success=False, channel=self.channel_name, error=str(exc))

    def update(self, listing_id: str, updates: dict) -> PublishResult:
        """쿠팡 상품 수정."""
        listing = self._listings.get(listing_id)
        if not listing:
            return PublishResult(success=False, channel=self.channel_name, error='listing not found')

        if 'price' in updates:
            fee_rate = listing.metadata.get('fee_rate', 0.10)
            listing.price = self._apply_fee(updates['price'], fee_rate)
        if 'title' in updates:
            listing.title = updates['title']
        if 'stock' in updates:
            listing.stock = int(updates['stock'])

        listing.last_synced_at = datetime.now(tz=timezone.utc).isoformat()
        logger.info("쿠팡 상품 수정: %s", listing_id)
        return PublishResult(success=True, listing_id=listing_id, channel=self.channel_name, message='쿠팡 상품 수정 완료')

    def deactivate(self, listing_id: str, reason: str) -> PublishResult:
        """쿠팡 상품 비활성화."""
        listing = self._listings.get(listing_id)
        if not listing:
            return PublishResult(success=False, channel=self.channel_name, error='listing not found')

        listing.state = ListingState.paused
        listing.error_message = reason
        listing.last_synced_at = datetime.now(tz=timezone.utc).isoformat()
        logger.info("쿠팡 상품 비활성화: %s (사유: %s)", listing_id, reason)
        return PublishResult(success=True, listing_id=listing_id, channel=self.channel_name, message='쿠팡 상품 비활성화 완료')

    def activate(self, listing_id: str) -> PublishResult:
        """쿠팡 상품 재활성화."""
        listing = self._listings.get(listing_id)
        if not listing:
            return PublishResult(success=False, channel=self.channel_name, error='listing not found')

        listing.state = ListingState.active
        listing.error_message = None
        listing.last_synced_at = datetime.now(tz=timezone.utc).isoformat()
        logger.info("쿠팡 상품 재활성화: %s", listing_id)
        return PublishResult(success=True, listing_id=listing_id, channel=self.channel_name, message='쿠팡 상품 재활성화 완료')

    def delete(self, listing_id: str) -> PublishResult:
        """쿠팡 상품 삭제."""
        listing = self._listings.get(listing_id)
        if not listing:
            return PublishResult(success=False, channel=self.channel_name, error='listing not found')

        listing.state = ListingState.deleted
        listing.last_synced_at = datetime.now(tz=timezone.utc).isoformat()
        logger.info("쿠팡 상품 삭제: %s", listing_id)
        return PublishResult(success=True, listing_id=listing_id, channel=self.channel_name, message='쿠팡 상품 삭제 완료')

    def get_status(self, listing_id: str) -> Optional[ListingStatus]:
        """쿠팡 상품 상태 조회."""
        return self._listings.get(listing_id)

    def health_check(self) -> bool:
        """쿠팡 연결 상태 확인."""
        return self._is_healthy

    def list_listings(self) -> list:
        """전체 리스팅 목록."""
        return list(self._listings.values())

    # ── 내부 헬퍼 ─────────────────────────────────────────────────────────────

    @staticmethod
    def _apply_fee(price: float, fee_rate: float) -> float:
        """수수료 포함 판매가 계산."""
        if price <= 0:
            return 0.0
        return round(price / (1 - fee_rate))
