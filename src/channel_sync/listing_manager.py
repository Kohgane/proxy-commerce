"""src/channel_sync/listing_manager.py — 판매채널 리스팅 상태 관리 (Phase 109).

ListingStatusManager: 채널별 리스팅 상태 관리 + 이력 추적
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .publishers.base import ListingState, ListingStatus

logger = logging.getLogger(__name__)


@dataclass
class ListingHistoryEntry:
    entry_id: str
    listing_id: str
    old_state: str
    new_state: str
    reason: str
    changed_at: str = ''

    def __post_init__(self):
        if not self.changed_at:
            self.changed_at = datetime.now(tz=timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            'entry_id': self.entry_id,
            'listing_id': self.listing_id,
            'old_state': self.old_state,
            'new_state': self.new_state,
            'reason': self.reason,
            'changed_at': self.changed_at,
        }


class ListingStatusManager:
    """판매채널별 리스팅 상태 관리자."""

    def __init__(self):
        self._listings: Dict[str, ListingStatus] = {}
        self._history: List[ListingHistoryEntry] = []

    # ── 등록 / 조회 ───────────────────────────────────────────────────────────

    def register_listing(self, listing: ListingStatus) -> ListingStatus:
        """리스팅 등록."""
        self._listings[listing.listing_id] = listing
        self._record_history(listing.listing_id, 'new', listing.state.value if hasattr(listing.state, 'value') else str(listing.state), '리스팅 등록')
        logger.info("리스팅 등록: %s (%s)", listing.listing_id, listing.channel)
        return listing

    def get_listing(self, listing_id: str) -> Optional[ListingStatus]:
        """리스팅 조회."""
        return self._listings.get(listing_id)

    def get_listings(self, product_id: Optional[str] = None) -> List[ListingStatus]:
        """상품별(또는 전체) 리스팅 조회."""
        listings = list(self._listings.values())
        if product_id:
            listings = [l for l in listings if l.product_id == product_id]
        return listings

    def get_listings_by_channel(self, channel: str) -> List[ListingStatus]:
        """채널별 리스팅 조회."""
        return [l for l in self._listings.values() if l.channel == channel]

    # ── 상태 변경 ─────────────────────────────────────────────────────────────

    def pause_listing(self, listing_id: str, reason: str) -> Optional[ListingStatus]:
        """리스팅 일시중지."""
        listing = self._listings.get(listing_id)
        if not listing:
            return None
        old_state = listing.state.value if hasattr(listing.state, 'value') else str(listing.state)
        listing.state = ListingState.paused
        listing.error_message = reason
        listing.last_synced_at = datetime.now(tz=timezone.utc).isoformat()
        self._record_history(listing_id, old_state, ListingState.paused.value, reason)
        logger.info("리스팅 일시중지: %s (사유: %s)", listing_id, reason)
        return listing

    def resume_listing(self, listing_id: str) -> Optional[ListingStatus]:
        """리스팅 재활성화."""
        listing = self._listings.get(listing_id)
        if not listing:
            return None
        old_state = listing.state.value if hasattr(listing.state, 'value') else str(listing.state)
        listing.state = ListingState.active
        listing.error_message = None
        listing.last_synced_at = datetime.now(tz=timezone.utc).isoformat()
        self._record_history(listing_id, old_state, ListingState.active.value, '재활성화')
        logger.info("리스팅 재활성화: %s", listing_id)
        return listing

    def deactivate_listing(self, listing_id: str, reason: str) -> Optional[ListingStatus]:
        """리스팅 비활성화."""
        listing = self._listings.get(listing_id)
        if not listing:
            return None
        old_state = listing.state.value if hasattr(listing.state, 'value') else str(listing.state)
        listing.state = ListingState.inactive
        listing.error_message = reason
        listing.last_synced_at = datetime.now(tz=timezone.utc).isoformat()
        self._record_history(listing_id, old_state, ListingState.inactive.value, reason)
        return listing

    def delete_listing(self, listing_id: str) -> Optional[ListingStatus]:
        """리스팅 삭제 표시."""
        listing = self._listings.get(listing_id)
        if not listing:
            return None
        old_state = listing.state.value if hasattr(listing.state, 'value') else str(listing.state)
        listing.state = ListingState.deleted
        listing.last_synced_at = datetime.now(tz=timezone.utc).isoformat()
        self._record_history(listing_id, old_state, ListingState.deleted.value, '삭제')
        return listing

    # ── 일괄 작업 ─────────────────────────────────────────────────────────────

    def bulk_pause(self, product_ids: List[str], reason: str) -> List[str]:
        """일괄 중지 — 주어진 상품 ID에 해당하는 모든 리스팅 중지."""
        paused_ids = []
        for listing in self._listings.values():
            if listing.product_id in product_ids and listing.state not in (ListingState.deleted, ListingState.paused):
                old_state = listing.state.value if hasattr(listing.state, 'value') else str(listing.state)
                listing.state = ListingState.paused
                listing.error_message = reason
                listing.last_synced_at = datetime.now(tz=timezone.utc).isoformat()
                self._record_history(listing.listing_id, old_state, ListingState.paused.value, reason)
                paused_ids.append(listing.listing_id)
        return paused_ids

    def bulk_resume(self, product_ids: List[str]) -> List[str]:
        """일괄 재활성화."""
        resumed_ids = []
        for listing in self._listings.values():
            if listing.product_id in product_ids and listing.state == ListingState.paused:
                old_state = listing.state.value if hasattr(listing.state, 'value') else str(listing.state)
                listing.state = ListingState.active
                listing.error_message = None
                listing.last_synced_at = datetime.now(tz=timezone.utc).isoformat()
                self._record_history(listing.listing_id, old_state, ListingState.active.value, '일괄 재활성화')
                resumed_ids.append(listing.listing_id)
        return resumed_ids

    # ── 이력 ─────────────────────────────────────────────────────────────────

    def get_history(self, listing_id: Optional[str] = None, limit: int = 100) -> List[ListingHistoryEntry]:
        """이력 조회."""
        history = self._history
        if listing_id:
            history = [h for h in history if h.listing_id == listing_id]
        return history[-limit:]

    # ── 통계 ─────────────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """리스팅 현황 통계."""
        listings = list(self._listings.values())
        by_state: Dict[str, int] = {}
        by_channel: Dict[str, int] = {}
        for l in listings:
            state_val = l.state.value if hasattr(l.state, 'value') else str(l.state)
            by_state[state_val] = by_state.get(state_val, 0) + 1
            by_channel[l.channel] = by_channel.get(l.channel, 0) + 1
        return {
            'total': len(listings),
            'by_state': by_state,
            'by_channel': by_channel,
            'history_count': len(self._history),
        }

    # ── 내부 ─────────────────────────────────────────────────────────────────

    def _record_history(self, listing_id: str, old_state: str, new_state: str, reason: str) -> None:
        entry = ListingHistoryEntry(
            entry_id=str(uuid.uuid4()),
            listing_id=listing_id,
            old_state=old_state,
            new_state=new_state,
            reason=reason,
        )
        self._history.append(entry)
