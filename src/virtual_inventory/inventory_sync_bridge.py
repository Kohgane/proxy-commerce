"""src/virtual_inventory/inventory_sync_bridge.py — 채널 동기화 브리지 (Phase 113)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, Optional

logger = logging.getLogger(__name__)

_CHANNEL_FACTORS: Dict[str, float] = {
    'coupang': 0.9,
    'naver': 0.95,
    'internal': 1.0,
}


class InventorySyncBridge:
    """가상 재고 → 채널별 재고 동기화 브리지."""

    def __init__(self) -> None:
        # product_id → {channel: qty}
        self._channel_stocks: Dict[str, Dict[str, int]] = {}
        self._last_sync_at: Optional[datetime] = None
        self._stock_pool = None

    def set_stock_pool(self, pool) -> None:
        self._stock_pool = pool

    # ── 동기화 ────────────────────────────────────────────────────────────────

    def sync_to_channels(self, product_id: Optional[str] = None) -> dict:
        """채널 재고 동기화 (mock). 반환: {synced, timestamp}."""
        if self._stock_pool is None:
            return {'synced': 0, 'timestamp': datetime.now(timezone.utc).isoformat()}

        if product_id is not None:
            product_ids = [product_id]
        else:
            product_ids = [vs.product_id for vs in self._stock_pool.get_all_virtual_stocks()]

        for pid in product_ids:
            self._channel_stocks[pid] = {
                channel: self.calculate_channel_stock(pid, channel)
                for channel in ('coupang', 'naver', 'internal')
            }

        self._last_sync_at = datetime.now(timezone.utc)
        return {'synced': len(product_ids), 'timestamp': self._last_sync_at.isoformat()}

    def get_channel_stock_map(self, product_id: str) -> Dict[str, int]:
        """상품의 채널별 재고 맵 반환."""
        return dict(self._channel_stocks.get(product_id, {}))

    def calculate_channel_stock(self, product_id: str, channel: str) -> int:
        """채널별 재고 계산 (채널 안전 버퍼 적용)."""
        if self._stock_pool is None:
            return 0
        vs = self._stock_pool.get_virtual_stock(product_id)
        if vs is None:
            return 0
        sellable = vs.sellable
        factor = _CHANNEL_FACTORS.get(channel, 0.85)
        return max(0, int(sellable * factor))

    # ── 상태 조회 ─────────────────────────────────────────────────────────────

    def get_sync_status(self) -> dict:
        """동기화 상태 반환."""
        total = 0
        if self._stock_pool is not None:
            total = len(self._stock_pool.get_all_virtual_stocks())
        synced = len(self._channel_stocks)
        discrepancies = self.get_stock_discrepancies()
        return {
            'last_synced_at': self._last_sync_at.isoformat() if self._last_sync_at else None,
            'total_products': total,
            'synced_products': synced,
            'discrepancy_count': len(discrepancies),
        }

    def get_stock_discrepancies(self) -> list:
        """채널 재고와 가상 재고 사이의 차이 목록."""
        result = []
        if self._stock_pool is None:
            return result
        for pid, channels in self._channel_stocks.items():
            vs = self._stock_pool.get_virtual_stock(pid)
            virtual_qty = vs.sellable if vs else 0
            for channel, channel_qty in channels.items():
                diff = virtual_qty - channel_qty
                if diff != 0:
                    result.append({
                        'product_id': pid,
                        'virtual_stock': virtual_qty,
                        'channel_stock': channel_qty,
                        'channel': channel,
                        'difference': diff,
                    })
        return result
