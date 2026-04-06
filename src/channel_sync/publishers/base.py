"""src/channel_sync/publishers/base.py — 판매채널 퍼블리셔 추상 기반 클래스 (Phase 109).

ChannelPublisher ABC: 모든 채널 퍼블리셔가 구현해야 할 인터페이스
PublishResult: 퍼블리셔 작업 결과
ListingStatus: 채널별 리스팅 상태 데이터클래스
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class ListingState(str, Enum):
    draft = 'draft'
    pending_review = 'pending_review'
    active = 'active'
    paused = 'paused'
    inactive = 'inactive'
    deleted = 'deleted'
    error = 'error'


@dataclass
class PublishResult:
    success: bool
    listing_id: Optional[str] = None
    channel: str = ''
    message: str = ''
    error: Optional[str] = None
    raw_response: Dict = field(default_factory=dict)
    executed_at: str = ''

    def __post_init__(self):
        if not self.executed_at:
            self.executed_at = datetime.now(tz=timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            'success': self.success,
            'listing_id': self.listing_id,
            'channel': self.channel,
            'message': self.message,
            'error': self.error,
            'raw_response': self.raw_response,
            'executed_at': self.executed_at,
        }


@dataclass
class ListingStatus:
    listing_id: str
    channel: str
    product_id: str
    state: ListingState = ListingState.draft
    channel_listing_id: Optional[str] = None
    title: str = ''
    price: float = 0.0
    stock: int = 0
    last_synced_at: Optional[str] = None
    error_message: Optional[str] = None
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            'listing_id': self.listing_id,
            'channel': self.channel,
            'product_id': self.product_id,
            'state': self.state.value if hasattr(self.state, 'value') else self.state,
            'channel_listing_id': self.channel_listing_id,
            'title': self.title,
            'price': self.price,
            'stock': self.stock,
            'last_synced_at': self.last_synced_at,
            'error_message': self.error_message,
            'metadata': self.metadata,
        }


class ChannelPublisher(ABC):
    """판매채널 퍼블리셔 추상 기반 클래스."""

    channel_name: str = ''

    @abstractmethod
    def publish(self, product_data: dict) -> PublishResult:
        """상품 등록."""

    @abstractmethod
    def update(self, listing_id: str, updates: dict) -> PublishResult:
        """상품 수정."""

    @abstractmethod
    def deactivate(self, listing_id: str, reason: str) -> PublishResult:
        """상품 비활성화 (일시중지)."""

    @abstractmethod
    def activate(self, listing_id: str) -> PublishResult:
        """상품 재활성화."""

    @abstractmethod
    def delete(self, listing_id: str) -> PublishResult:
        """상품 삭제."""

    @abstractmethod
    def get_status(self, listing_id: str) -> Optional[ListingStatus]:
        """상품 상태 조회."""

    @abstractmethod
    def health_check(self) -> bool:
        """채널 연결 상태 확인."""
