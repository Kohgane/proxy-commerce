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

    def health_check(self) -> dict:
        """자체몰 API 상태 확인 — stub."""
        return {"status": "stub", "detail": "코가네멀티샵 어댑터 미구현"}
