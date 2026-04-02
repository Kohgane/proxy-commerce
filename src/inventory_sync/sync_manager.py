"""재고 동기화 매니저."""

import logging
from datetime import datetime

from .channel_adapter import CoupangAdapter, NaverAdapter, InternalAdapter
from .conflict_resolver import ConflictResolver

logger = logging.getLogger(__name__)


class InventorySyncManager:
    """재고 동기화 매니저 — 모든 채널 재고 동기화."""

    def __init__(self, conflict_strategy: str = 'conservative'):
        self._channels = {
            'coupang': CoupangAdapter(),
            'naver': NaverAdapter(),
            'internal': InternalAdapter(),
        }
        self._resolver = ConflictResolver(strategy=conflict_strategy)
        self._sync_log: list = []
        self._last_sync: dict = {}

    def sync_all_channels(self) -> dict:
        """모든 채널 재고 동기화.

        Returns:
            동기화 결과 딕셔너리
        """
        now = datetime.now().isoformat()
        synced_skus = set()
        results = {}

        for channel_name, adapter in self._channels.items():
            try:
                products = adapter.list_products()
                for sku in products:
                    synced_skus.add(sku)
            except Exception as exc:
                logger.error("채널 %s 동기화 오류: %s", channel_name, exc)

        for sku in synced_skus:
            result = self.sync_sku(sku)
            results[sku] = result

        self._sync_log.append({'timestamp': now, 'synced': len(synced_skus)})
        self._last_sync['all'] = now
        logger.info("전체 채널 동기화 완료: %d SKU", len(synced_skus))
        return {'synced_count': len(synced_skus), 'results': results, 'timestamp': now}

    def sync_sku(self, sku: str) -> dict:
        """단일 SKU 재고 동기화.

        Args:
            sku: 동기화할 SKU

        Returns:
            동기화 결과 딕셔너리
        """
        channel_stocks = {}
        for channel_name, adapter in self._channels.items():
            try:
                stock = adapter.get_stock(sku)
                channel_stocks[channel_name] = stock
            except Exception as exc:
                logger.error("SKU %s 채널 %s 조회 오류: %s", sku, channel_name, exc)

        resolved_stock = self._resolver.resolve(sku, channel_stocks)

        update_results = {}
        for channel_name, adapter in self._channels.items():
            try:
                success = adapter.update_stock(sku, resolved_stock)
                update_results[channel_name] = success
            except Exception as exc:
                logger.error("SKU %s 채널 %s 업데이트 오류: %s", sku, channel_name, exc)
                update_results[channel_name] = False

        self._last_sync[sku] = datetime.now().isoformat()
        return {
            'sku': sku,
            'channel_stocks': channel_stocks,
            'resolved_stock': resolved_stock,
            'update_results': update_results,
        }

    def get_sync_status(self) -> dict:
        """동기화 상태 조회."""
        return {
            'last_sync': self._last_sync,
            'sync_count': len(self._sync_log),
            'channels': list(self._channels.keys()),
        }
