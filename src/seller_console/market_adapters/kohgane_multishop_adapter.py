"""src/seller_console/market_adapters/kohgane_multishop_adapter.py — 코가네멀티샵 어댑터 stub (Phase 127).

자체몰 어댑터 — 향후 내부 DB/API 연동 예정.
현재는 빈 리스트 반환 + 경고 로그.
"""
from __future__ import annotations

import logging
from typing import List

from src.seller_console.market_status import MarketStatusItem
from .base import MarketAdapter

logger = logging.getLogger(__name__)


class KohganeMultishopAdapter(MarketAdapter):
    """코가네 자체몰 어댑터 (향후 내부 API 연동 예정)."""

    marketplace = "kohganemultishop"

    def fetch_inventory(self) -> List[MarketStatusItem]:
        """자체몰 API에서 재고 조회 — 향후 실연동 예정."""
        logger.warning("코가네멀티샵 어댑터 미구현 — Sheets 캐시 사용")
        return []

    def fetch_orders_unified(self, since=None, until=None) -> list:
        """자체몰 주문 조회 — 향후 실연동 예정 (현재 stub)."""
        logger.warning("코가네멀티샵 fetch_orders_unified 미구현 — 빈 목록 반환")
        return []

    def update_tracking(self, order_id: str, courier: str = "", tracking_no: str = "") -> bool:
        """자체몰 운송장 등록 — stub."""
        logger.warning("코가네멀티샵 update_tracking 미구현")
        return False

    def health_check(self) -> dict:
        """자체몰 API 상태 확인 — stub."""
        return {"status": "stub", "detail": "코가네멀티샵 어댑터 미구현"}
