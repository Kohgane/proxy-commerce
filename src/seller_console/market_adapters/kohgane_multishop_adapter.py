"""src/seller_console/market_adapters/kohgane_multishop_adapter.py — 코가네멀티샵 어댑터 (Phase 131).

DEPRECATED in Phase 132
kohganemultishop.org는 WooCommerce 기반 외부 워드프레스이므로
WooCommerceAdapter로 통합. 본 어댑터는 호환성을 위해 stub만 유지.
"""
from __future__ import annotations

import logging
import warnings
from typing import List

from src.seller_console.market_status import MarketStatusItem
from .base import MarketAdapter

logger = logging.getLogger(__name__)


class KohganeMultishopAdapter(MarketAdapter):
    """코가네 자체몰 어댑터 — Phase 132에서 deprecated.

    WooCommerceAdapter를 사용하세요.
    """

    marketplace = "kohganemultishop"
    DEPRECATED = True

    def __init__(self):
        warnings.warn(
            "KohganeMultishopAdapter는 Phase 132에서 deprecated되었습니다. "
            "WooCommerceAdapter를 사용하세요.",
            DeprecationWarning,
            stacklevel=2,
        )

    def fetch_inventory(self) -> List[MarketStatusItem]:
        return []

    def upload_product(self, product: dict) -> dict:
        return {"ok": False, "error": "deprecated"}

    def fetch_orders_unified(self, since=None, until=None) -> list:
        return []

    def update_tracking(self, order_id: str, courier: str = "", tracking_no: str = "") -> bool:
        return False

    def health_check(self) -> dict:
        return {"status": "deprecated", "detail": "WooCommerceAdapter를 사용하세요."}

