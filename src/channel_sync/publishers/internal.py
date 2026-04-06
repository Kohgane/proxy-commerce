"""src/channel_sync/publishers/internal.py — 자체몰 퍼블리셔 mock 구현 (Phase 109)."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Optional

from .base import ChannelPublisher, ListingState, ListingStatus, PublishResult

logger = logging.getLogger(__name__)


class InternalPublisher(ChannelPublisher):
    """자체몰 상품 관리 mock 퍼블리셔 (직접 DB 업데이트 시뮬레이션)."""

    channel_name = 'internal'

    def __init__(self):
        self._listings: Dict[str, ListingStatus] = {}
        self._is_healthy: bool = True

    # ── 핵심 메서드 ──────────────────────────────────────────────────────────

    def publish(self, product_data: dict) -> PublishResult:
        """자체몰에 상품 등록."""
        try:
            listing_id = str(uuid.uuid4())
            channel_listing_id = f'internal-{uuid.uuid4().hex[:8]}'

            listing = ListingStatus(
                listing_id=listing_id,
                channel=self.channel_name,
                product_id=product_data.get('product_id', ''),
                state=ListingState.active,
                channel_listing_id=channel_listing_id,
                title=product_data.get('title', ''),
                price=float(product_data.get('price', 0)),
                stock=int(product_data.get('stock', 0)),
                last_synced_at=datetime.now(tz=timezone.utc).isoformat(),
                metadata={
                    'category': product_data.get('category', ''),
                    'description': product_data.get('description', ''),
                    'images': product_data.get('images', []),
                    'options': product_data.get('options', []),
                },
            )
            self._listings[listing_id] = listing

            logger.info("자체몰 상품 등록: %s → %s", product_data.get('product_id'), listing_id)
            return PublishResult(
                success=True,
                listing_id=listing_id,
                channel=self.channel_name,
                message='자체몰 상품 등록 완료',
                raw_response={'channel_listing_id': channel_listing_id},
            )
        except Exception as exc:
            logger.error("자체몰 publish 오류: %s", exc)
            return PublishResult(success=False, channel=self.channel_name, error=str(exc))

    def update(self, listing_id: str, updates: dict) -> PublishResult:
        """자체몰 상품 수정."""
        listing = self._listings.get(listing_id)
        if not listing:
            return PublishResult(success=False, channel=self.channel_name, error='listing not found')

        if 'price' in updates:
            listing.price = float(updates['price'])
        if 'title' in updates:
            listing.title = updates['title']
        if 'stock' in updates:
            listing.stock = int(updates['stock'])
        if 'description' in updates:
            listing.metadata['description'] = updates['description']
        if 'images' in updates:
            listing.metadata['images'] = updates['images']
        if 'options' in updates:
            listing.metadata['options'] = updates['options']

        listing.last_synced_at = datetime.now(tz=timezone.utc).isoformat()
        logger.info("자체몰 상품 수정: %s", listing_id)
        return PublishResult(success=True, listing_id=listing_id, channel=self.channel_name, message='자체몰 상품 수정 완료')

    def deactivate(self, listing_id: str, reason: str) -> PublishResult:
        """자체몰 상품 비활성화."""
        listing = self._listings.get(listing_id)
        if not listing:
            return PublishResult(success=False, channel=self.channel_name, error='listing not found')

        listing.state = ListingState.paused
        listing.error_message = reason
        listing.last_synced_at = datetime.now(tz=timezone.utc).isoformat()
        logger.info("자체몰 상품 비활성화: %s (사유: %s)", listing_id, reason)
        return PublishResult(success=True, listing_id=listing_id, channel=self.channel_name, message='자체몰 상품 비활성화 완료')

    def activate(self, listing_id: str) -> PublishResult:
        """자체몰 상품 재활성화."""
        listing = self._listings.get(listing_id)
        if not listing:
            return PublishResult(success=False, channel=self.channel_name, error='listing not found')

        listing.state = ListingState.active
        listing.error_message = None
        listing.last_synced_at = datetime.now(tz=timezone.utc).isoformat()
        logger.info("자체몰 상품 재활성화: %s", listing_id)
        return PublishResult(success=True, listing_id=listing_id, channel=self.channel_name, message='자체몰 상품 재활성화 완료')

    def delete(self, listing_id: str) -> PublishResult:
        """자체몰 상품 삭제."""
        listing = self._listings.get(listing_id)
        if not listing:
            return PublishResult(success=False, channel=self.channel_name, error='listing not found')

        listing.state = ListingState.deleted
        listing.last_synced_at = datetime.now(tz=timezone.utc).isoformat()
        logger.info("자체몰 상품 삭제: %s", listing_id)
        return PublishResult(success=True, listing_id=listing_id, channel=self.channel_name, message='자체몰 상품 삭제 완료')

    def get_status(self, listing_id: str) -> Optional[ListingStatus]:
        """자체몰 상품 상태 조회."""
        return self._listings.get(listing_id)

    def health_check(self) -> bool:
        """자체몰 연결 상태 확인."""
        return self._is_healthy

    def list_listings(self) -> list:
        """전체 리스팅 목록."""
        return list(self._listings.values())
