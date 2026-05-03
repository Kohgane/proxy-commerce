"""src/seller_console/market_adapters/smartstore_adapter.py — 스마트스토어 어댑터 stub (Phase 127).

Phase 130에서 네이버 커머스 API 실연동 예정.
현재는 빈 리스트 반환 + 경고 로그.
"""
from __future__ import annotations

import logging
from typing import List

from src.seller_console.market_status import MarketStatusItem
from .base import MarketAdapter

logger = logging.getLogger(__name__)


class SmartStoreAdapter(MarketAdapter):
    """스마트스토어(네이버) 어댑터 (Phase 130 실연동 예정)."""

    marketplace = "smartstore"

    def fetch_inventory(self) -> List[MarketStatusItem]:
        """스마트스토어 API에서 재고 조회 — Phase 130 실연동 예정."""
        logger.warning("스마트스토어 어댑터 미구현 — Sheets 캐시 사용")
        return []

    def health_check(self) -> dict:
        """스마트스토어 API 상태 확인 — stub."""
        return {"status": "stub", "detail": "스마트스토어 어댑터 미구현 (Phase 130 예정)"}
