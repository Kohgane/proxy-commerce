"""src/channel_sync/publishers/naver.py — 네이버 스마트스토어 퍼블리셔 mock 구현 (Phase 109)."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .base import ChannelPublisher, ListingState, ListingStatus, PublishResult

logger = logging.getLogger(__name__)

# 네이버 카테고리 매핑
NAVER_CATEGORY_MAP: Dict[str, str] = {
    'electronics': '50000803',
    'fashion': '50000167',
    'beauty': '50000025',
    'home': '50002170',
    'food': '50000006',
    'sports': '50000075',
    'toys': '50003658',
    'books': '50005542',
    'default': '50000803',
}

# 네이버 수수료율
NAVER_FEE_RATES: Dict[str, float] = {
    '50000803': 0.08,  # 전자제품
    '50000167': 0.09,  # 패션
    '50000025': 0.10,  # 뷰티
    '50002170': 0.07,  # 홈
    '50000006': 0.06,  # 식품
    'default': 0.08,
}


class NaverPublisher(ChannelPublisher):
    """네이버 스마트스토어 상품 관리 mock 퍼블리셔."""

    channel_name = 'naver'

    def __init__(self):
        self._listings: Dict[str, ListingStatus] = {}
        self._is_healthy: bool = True

    # ── 핵심 메서드 ──────────────────────────────────────────────────────────

    def publish(self, product_data: dict) -> PublishResult:
        """네이버에 상품 등록."""
        try:
            listing_id = str(uuid.uuid4())
            channel_listing_id = f'naver-{uuid.uuid4().hex[:8]}'

            category = product_data.get('category', 'default')
            naver_category = NAVER_CATEGORY_MAP.get(category, NAVER_CATEGORY_MAP['default'])
            fee_rate = NAVER_FEE_RATES.get(naver_category, NAVER_FEE_RATES['default'])
            sale_price = self._apply_fee(product_data.get('price', 0), fee_rate)
            tags = self._build_tags(product_data)

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
                    'naver_category': naver_category,
                    'fee_rate': fee_rate,
                    'tags': tags,
                },
            )
            self._listings[listing_id] = listing

            logger.info("네이버 상품 등록: %s → %s", product_data.get('product_id'), listing_id)
            return PublishResult(
                success=True,
                listing_id=listing_id,
                channel=self.channel_name,
                message='네이버 상품 등록 완료',
                raw_response={'channel_listing_id': channel_listing_id, 'category': naver_category, 'tags': tags},
            )
        except Exception as exc:
            logger.error("네이버 publish 오류: %s", exc)
            return PublishResult(success=False, channel=self.channel_name, error=str(exc))

    def update(self, listing_id: str, updates: dict) -> PublishResult:
        """네이버 상품 수정."""
        listing = self._listings.get(listing_id)
        if not listing:
            return PublishResult(success=False, channel=self.channel_name, error='listing not found')

        if 'price' in updates:
            fee_rate = listing.metadata.get('fee_rate', 0.08)
            listing.price = self._apply_fee(updates['price'], fee_rate)
        if 'title' in updates:
            listing.title = updates['title']
        if 'stock' in updates:
            listing.stock = int(updates['stock'])
        if 'tags' in updates:
            listing.metadata['tags'] = updates['tags']

        listing.last_synced_at = datetime.now(tz=timezone.utc).isoformat()
        logger.info("네이버 상품 수정: %s", listing_id)
        return PublishResult(success=True, listing_id=listing_id, channel=self.channel_name, message='네이버 상품 수정 완료')

    def deactivate(self, listing_id: str, reason: str) -> PublishResult:
        """네이버 상품 비활성화."""
        listing = self._listings.get(listing_id)
        if not listing:
            return PublishResult(success=False, channel=self.channel_name, error='listing not found')

        listing.state = ListingState.paused
        listing.error_message = reason
        listing.last_synced_at = datetime.now(tz=timezone.utc).isoformat()
        logger.info("네이버 상품 비활성화: %s (사유: %s)", listing_id, reason)
        return PublishResult(success=True, listing_id=listing_id, channel=self.channel_name, message='네이버 상품 비활성화 완료')

    def activate(self, listing_id: str) -> PublishResult:
        """네이버 상품 재활성화."""
        listing = self._listings.get(listing_id)
        if not listing:
            return PublishResult(success=False, channel=self.channel_name, error='listing not found')

        listing.state = ListingState.active
        listing.error_message = None
        listing.last_synced_at = datetime.now(tz=timezone.utc).isoformat()
        logger.info("네이버 상품 재활성화: %s", listing_id)
        return PublishResult(success=True, listing_id=listing_id, channel=self.channel_name, message='네이버 상품 재활성화 완료')

    def delete(self, listing_id: str) -> PublishResult:
        """네이버 상품 삭제."""
        listing = self._listings.get(listing_id)
        if not listing:
            return PublishResult(success=False, channel=self.channel_name, error='listing not found')

        listing.state = ListingState.deleted
        listing.last_synced_at = datetime.now(tz=timezone.utc).isoformat()
        logger.info("네이버 상품 삭제: %s", listing_id)
        return PublishResult(success=True, listing_id=listing_id, channel=self.channel_name, message='네이버 상품 삭제 완료')

    def get_status(self, listing_id: str) -> Optional[ListingStatus]:
        """네이버 상품 상태 조회."""
        return self._listings.get(listing_id)

    def health_check(self) -> bool:
        """네이버 연결 상태 확인."""
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
        effective_rate = min(fee_rate, 0.99)
        return round(price / (1 - effective_rate))

    @staticmethod
    def _build_tags(product_data: dict) -> List[str]:
        """네이버 태그 생성."""
        tags = product_data.get('tags', [])
        if not tags:
            title = product_data.get('title', '')
            tags = [w for w in title.split() if len(w) >= 2][:5]
        return tags
