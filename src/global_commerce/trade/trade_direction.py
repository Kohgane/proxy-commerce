"""src/global_commerce/trade/trade_direction.py — 수입/수출/구매대행 방향 Enum (Phase 93)."""
from __future__ import annotations

import enum


class TradeDirection(str, enum.Enum):
    """무역 방향."""
    IMPORT = 'import'          # 해외 → 국내 (수입)
    EXPORT = 'export'          # 국내 → 해외 (수출)
    PROXY_BUY = 'proxy_buy'    # 구매대행 (해외 대신 구매)
