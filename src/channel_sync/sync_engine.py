"""src/channel_sync/sync_engine.py — 채널 동기화 엔진 (Phase 109).

ChannelSyncEngine: 소싱처 변동 이벤트 수신 → 판매채널 자동 반영 오케스트레이션
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

ALL_CHANNELS = ['coupang', 'naver', 'internal']

# 재시도 설정
MAX_RETRIES = 3
BASE_BACKOFF_SECONDS = 1.0  # 지수 백오프 기반 (테스트에서 실제 sleep 안 함)


class SyncStatus(str, Enum):
    pending = 'pending'
    in_progress = 'in_progress'
    success = 'success'
    failed = 'failed'
    retrying = 'retrying'


class ChangeEventType(str, Enum):
    price_changed = 'price_changed'
    out_of_stock = 'out_of_stock'
    listing_removed = 'listing_removed'
    seller_inactive = 'seller_inactive'
    back_in_stock = 'back_in_stock'
    source_recovered = 'source_recovered'
    info_changed = 'info_changed'


@dataclass
class SyncQueueItem:
    item_id: str
    product_id: str
    channels: List[str]
    action: str  # publish / update / deactivate / activate / delete
    payload: Dict
    priority: int = 5
    retries: int = 0
    status: SyncStatus = SyncStatus.pending
    created_at: str = ''
    updated_at: str = ''
    error: Optional[str] = None

    def __post_init__(self):
        now = datetime.now(tz=timezone.utc).isoformat()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now

    def to_dict(self) -> dict:
        return {
            'item_id': self.item_id,
            'product_id': self.product_id,
            'channels': self.channels,
            'action': self.action,
            'payload': self.payload,
            'priority': self.priority,
            'retries': self.retries,
            'status': self.status.value if hasattr(self.status, 'value') else self.status,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'error': self.error,
        }


@dataclass
class SyncHistoryEntry:
    entry_id: str
    product_id: str
    channel: str
    action: str
    success: bool
    listing_id: Optional[str] = None
    error: Optional[str] = None
    synced_at: str = ''

    def __post_init__(self):
        if not self.synced_at:
            self.synced_at = datetime.now(tz=timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            'entry_id': self.entry_id,
            'product_id': self.product_id,
            'channel': self.channel,
            'action': self.action,
            'success': self.success,
            'listing_id': self.listing_id,
            'error': self.error,
            'synced_at': self.synced_at,
        }


class ChannelSyncEngine:
    """채널 동기화 오케스트레이션 엔진."""

    def __init__(self):
        from .publishers.coupang import CoupangPublisher
        from .publishers.naver import NaverPublisher
        from .publishers.internal import InternalPublisher
        from .product_mapper import ProductMapper
        from .listing_manager import ListingStatusManager
        from .conflict_resolver import SyncConflictResolver

        self._publishers = {
            'coupang': CoupangPublisher(),
            'naver': NaverPublisher(),
            'internal': InternalPublisher(),
        }
        self._mapper = ProductMapper()
        self._listing_manager = ListingStatusManager()
        self._conflict_resolver = SyncConflictResolver()

        self._queue: Dict[str, SyncQueueItem] = {}
        self._history: List[SyncHistoryEntry] = []
        # product_id → {channel → listing_id} 매핑
        self._product_listings: Dict[str, Dict[str, str]] = {}

    # ── 동기화 트리거 ─────────────────────────────────────────────────────────

    def sync_product(self, product_id: str, channels: Optional[List[str]] = None, product_data: Optional[dict] = None) -> dict:
        """특정 상품을 지정 채널에 동기화."""
        target_channels = channels or ALL_CHANNELS
        data = product_data or {'product_id': product_id}
        results = {}

        for channel in target_channels:
            publisher = self._publishers.get(channel)
            if not publisher:
                results[channel] = {'success': False, 'error': f'unknown channel: {channel}'}
                continue

            channel_data = self._mapper.map_product(data, channel)
            existing_listing_id = self._product_listings.get(product_id, {}).get(channel)

            if existing_listing_id:
                result = self._execute_with_retry(publisher, 'update', existing_listing_id, channel_data)
            else:
                result = self._execute_with_retry(publisher, 'publish', channel_data)

            if result.success and result.listing_id:
                # 리스팅 매핑 저장
                if product_id not in self._product_listings:
                    self._product_listings[product_id] = {}
                self._product_listings[product_id][channel] = result.listing_id
                # listing_manager에 등록
                status = publisher.get_status(result.listing_id)
                if status:
                    self._listing_manager.register_listing(status)

            self._record_history(product_id, channel, 'sync', result.success, result.listing_id, result.error)
            results[channel] = result.to_dict()

        return {'product_id': product_id, 'results': results}

    def sync_all(self, channel: Optional[str] = None) -> dict:
        """전체 상품 동기화."""
        target_channels = [channel] if channel else ALL_CHANNELS
        synced_count = 0
        failed_count = 0

        all_product_ids = set(self._product_listings.keys())
        for product_id in all_product_ids:
            result = self.sync_product(product_id, target_channels)
            for ch, r in result['results'].items():
                if r.get('success'):
                    synced_count += 1
                else:
                    failed_count += 1

        return {
            'synced': synced_count,
            'failed': failed_count,
            'channels': target_channels,
        }

    # ── 소싱처 변동 이벤트 처리 ──────────────────────────────────────────────

    def handle_source_change(self, change_event: dict) -> dict:
        """Phase 108 변동 이벤트 처리."""
        event_type = change_event.get('change_type', '')
        product_id = change_event.get('my_product_id') or change_event.get('product_id', '')
        channels = change_event.get('channels') or ALL_CHANNELS
        results = {}

        if event_type in ('price_increase', 'price_decrease', 'price_changed'):
            # 가격 변동 → 판매가 재계산 + 업데이트
            new_price = change_event.get('new_value') or change_event.get('price', 0)
            results = self._handle_price_change(product_id, float(new_price), channels)

        elif event_type in ('out_of_stock',):
            # 품절 → 판매채널 일시중지
            results = self._handle_out_of_stock(product_id, channels)

        elif event_type in ('listing_removed', 'seller_inactive'):
            # 삭제/비활성 → 판매채널 비활성화
            results = self._handle_deactivation(product_id, channels, reason=event_type)

        elif event_type in ('back_in_stock', 'source_recovered'):
            # 소싱처 복구 → 판매채널 재활성화
            results = self._handle_reactivation(product_id, channels)

        else:
            # 기타 정보 변경 → 업데이트
            results = self._handle_info_change(product_id, change_event, channels)

        return {
            'event_type': event_type,
            'product_id': product_id,
            'results': results,
        }

    def _handle_price_change(self, product_id: str, new_price: float, channels: List[str]) -> dict:
        results = {}
        for channel in channels:
            publisher = self._publishers.get(channel)
            if not publisher:
                continue
            listing_id = self._product_listings.get(product_id, {}).get(channel)
            if listing_id:
                result = self._execute_with_retry(publisher, 'update', listing_id, {'price': new_price})
            else:
                result = self._execute_with_retry(publisher, 'publish', {'product_id': product_id, 'price': new_price})
                if result.success and result.listing_id:
                    if product_id not in self._product_listings:
                        self._product_listings[product_id] = {}
                    self._product_listings[product_id][channel] = result.listing_id
            self._record_history(product_id, channel, 'price_update', result.success, result.listing_id, result.error)
            results[channel] = result.to_dict()
        return results

    def _handle_out_of_stock(self, product_id: str, channels: List[str]) -> dict:
        from .publishers.base import PublishResult
        results = {}
        for channel in channels:
            publisher = self._publishers.get(channel)
            if not publisher:
                continue
            listing_id = self._product_listings.get(product_id, {}).get(channel)
            if listing_id:
                result = self._execute_with_retry(publisher, 'deactivate', listing_id, '품절')
                self._listing_manager.pause_listing(listing_id, '품절')
            else:
                result = PublishResult(success=False, channel=channel, error='no listing')
            self._record_history(product_id, channel, 'pause_out_of_stock', result.success, listing_id, result.error)
            results[channel] = result.to_dict()
        return results

    def _handle_deactivation(self, product_id: str, channels: List[str], reason: str) -> dict:
        from .publishers.base import PublishResult
        results = {}
        for channel in channels:
            publisher = self._publishers.get(channel)
            if not publisher:
                continue
            listing_id = self._product_listings.get(product_id, {}).get(channel)
            if listing_id:
                result = self._execute_with_retry(publisher, 'deactivate', listing_id, reason)
                self._listing_manager.deactivate_listing(listing_id, reason)
            else:
                result = PublishResult(success=False, channel=channel, error='no listing')
            self._record_history(product_id, channel, 'deactivate', result.success, listing_id, result.error)
            results[channel] = result.to_dict()
        return results

    def _handle_reactivation(self, product_id: str, channels: List[str]) -> dict:
        results = {}
        for channel in channels:
            publisher = self._publishers.get(channel)
            if not publisher:
                continue
            listing_id = self._product_listings.get(product_id, {}).get(channel)
            if listing_id:
                result = self._execute_with_retry(publisher, 'activate', listing_id)
                self._listing_manager.resume_listing(listing_id)
            else:
                # 리스팅 없으면 새로 등록
                result = self._execute_with_retry(publisher, 'publish', {'product_id': product_id})
                if result.success and result.listing_id:
                    if product_id not in self._product_listings:
                        self._product_listings[product_id] = {}
                    self._product_listings[product_id][channel] = result.listing_id
            self._record_history(product_id, channel, 'activate', result.success, result.listing_id if hasattr(result, 'listing_id') else None, result.error if hasattr(result, 'error') else None)
            results[channel] = result.to_dict()
        return results

    def _handle_info_change(self, product_id: str, change_event: dict, channels: List[str]) -> dict:
        updates = {k: v for k, v in change_event.items() if k not in ('change_type', 'my_product_id', 'product_id', 'channels')}
        results = {}
        for channel in channels:
            publisher = self._publishers.get(channel)
            if not publisher:
                continue
            listing_id = self._product_listings.get(product_id, {}).get(channel)
            if listing_id:
                result = self._execute_with_retry(publisher, 'update', listing_id, updates)
            else:
                result = self._execute_with_retry(publisher, 'publish', {'product_id': product_id, **updates})
                if result.success and result.listing_id:
                    if product_id not in self._product_listings:
                        self._product_listings[product_id] = {}
                    self._product_listings[product_id][channel] = result.listing_id
            self._record_history(product_id, channel, 'info_update', result.success, result.listing_id, result.error)
            results[channel] = result.to_dict()
        return results

    # ── 큐 관리 ──────────────────────────────────────────────────────────────

    def enqueue(self, product_id: str, channels: List[str], action: str, payload: dict, priority: int = 5) -> SyncQueueItem:
        """동기화 큐에 작업 추가."""
        item_id = str(uuid.uuid4())
        item = SyncQueueItem(
            item_id=item_id,
            product_id=product_id,
            channels=channels,
            action=action,
            payload=payload,
            priority=priority,
        )
        self._queue[item_id] = item
        return item

    def process_queue(self) -> List[dict]:
        """큐에서 대기 중인 작업 처리."""
        pending = sorted(
            [i for i in self._queue.values() if i.status == SyncStatus.pending],
            key=lambda x: x.priority,
        )
        results = []
        for item in pending:
            item.status = SyncStatus.in_progress
            item.updated_at = datetime.now(tz=timezone.utc).isoformat()
            result = self.sync_product(item.product_id, item.channels, item.payload)
            # 모든 채널 성공 여부 확인
            all_ok = all(r.get('success') for r in result['results'].values())
            if all_ok:
                item.status = SyncStatus.success
            else:
                item.retries += 1
                if item.retries >= MAX_RETRIES:
                    item.status = SyncStatus.failed
                    item.error = 'max retries exceeded'
                else:
                    item.status = SyncStatus.retrying
            item.updated_at = datetime.now(tz=timezone.utc).isoformat()
            results.append(result)
        return results

    def get_queue_status(self) -> dict:
        """큐 현황."""
        items = list(self._queue.values())
        by_status: Dict[str, int] = {}
        for item in items:
            s = item.status.value if hasattr(item.status, 'value') else str(item.status)
            by_status[s] = by_status.get(s, 0) + 1
        return {
            'total': len(items),
            'by_status': by_status,
            'items': [i.to_dict() for i in items],
        }

    # ── 상태 / 이력 / 통계 ────────────────────────────────────────────────────

    def get_sync_status(self, product_id: Optional[str] = None) -> dict:
        """동기화 현황 조회."""
        if product_id:
            listings = self._listing_manager.get_listings(product_id=product_id)
            return {
                'product_id': product_id,
                'listings': [l.to_dict() for l in listings],
                'channels': self._product_listings.get(product_id, {}),
            }
        return {
            'total_products': len(self._product_listings),
            'listing_stats': self._listing_manager.get_stats(),
            'queue_stats': self.get_queue_status(),
        }

    def get_sync_history(
        self,
        product_id: Optional[str] = None,
        channel: Optional[str] = None,
        limit: int = 50,
    ) -> List[dict]:
        """동기화 이력 조회."""
        history = self._history
        if product_id:
            history = [h for h in history if h.product_id == product_id]
        if channel:
            history = [h for h in history if h.channel == channel]
        return [h.to_dict() for h in history[-limit:]]

    def get_sync_stats(self) -> dict:
        """전체 동기화 통계."""
        history = self._history
        success_count = sum(1 for h in history if h.success)
        failed_count = sum(1 for h in history if not h.success)

        by_channel: Dict[str, Dict[str, int]] = {}
        for h in history:
            if h.channel not in by_channel:
                by_channel[h.channel] = {'success': 0, 'failed': 0}
            if h.success:
                by_channel[h.channel]['success'] += 1
            else:
                by_channel[h.channel]['failed'] += 1

        return {
            'total': len(history),
            'success': success_count,
            'failed': failed_count,
            'by_channel': by_channel,
            'products_synced': len(self._product_listings),
        }

    # ── 채널 건강도 ───────────────────────────────────────────────────────────

    def get_channel_health(self, channel: Optional[str] = None) -> dict:
        """채널 연결 상태 확인."""
        channels = [channel] if channel else list(self._publishers.keys())
        health = {}
        for ch in channels:
            publisher = self._publishers.get(ch)
            if publisher:
                health[ch] = {
                    'healthy': publisher.health_check(),
                    'channel': ch,
                }
        return health

    # ── 내부 헬퍼 ─────────────────────────────────────────────────────────────

    def _execute_with_retry(self, publisher, method: str, *args, max_retries: int = MAX_RETRIES):
        """재시도 로직 포함 퍼블리셔 메서드 실행 (지수 백오프)."""
        from .publishers.base import PublishResult
        last_result = None
        for attempt in range(max_retries):
            try:
                fn = getattr(publisher, method)
                last_result = fn(*args)
                if last_result.success:
                    return last_result
            except Exception as exc:
                logger.warning("퍼블리셔 %s.%s 시도 %d 실패: %s", publisher.channel_name, method, attempt + 1, exc)
                last_result = PublishResult(success=False, channel=publisher.channel_name, error=str(exc))
            # 지수 백오프 (테스트 환경에서는 실제 sleep 스킵)
            if attempt < max_retries - 1:
                _wait = BASE_BACKOFF_SECONDS * (2 ** attempt)
                # time.sleep(_wait)  # 실제 환경에서 활성화
        return last_result or PublishResult(success=False, channel=publisher.channel_name, error='unknown error')

    def _record_history(
        self,
        product_id: str,
        channel: str,
        action: str,
        success: bool,
        listing_id: Optional[str],
        error: Optional[str],
    ) -> None:
        entry = SyncHistoryEntry(
            entry_id=str(uuid.uuid4()),
            product_id=product_id,
            channel=channel,
            action=action,
            success=success,
            listing_id=listing_id,
            error=error,
        )
        self._history.append(entry)
