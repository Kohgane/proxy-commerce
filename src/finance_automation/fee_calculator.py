"""src/finance_automation/fee_calculator.py — Phase 119: 채널/PG 수수료 계산기."""
from __future__ import annotations

import logging
from decimal import Decimal

logger = logging.getLogger(__name__)

try:
    from ..vendor_marketplace.settlement import SettlementManager as _VMSettlement  # type: ignore
    _HAS_VM = True
except ImportError:
    _HAS_VM = False

# 채널별 수수료율
_CHANNEL_RATES: dict = {
    'coupang': Decimal('0.11'),
    'naver': Decimal('0.0585'),
    'own': Decimal('0'),
    'vendor': Decimal('0.08'),
}

# PG 수수료율
_PG_RATES: dict = {
    'toss': Decimal('0.014'),
    'stripe': Decimal('2.9') / Decimal('100'),
    'paypal': Decimal('0.034'),
}


class ChannelFeeCalculator:
    """채널별 수수료 및 PG 수수료 계산.

    채널 수수료율: coupang 11%, naver 5.85%, own 0%, vendor 8% (기본값).
    PG 수수료율: toss 1.4%, stripe 2.9%, paypal 3.4%.
    """

    def get_fee_rate(self, channel: str) -> Decimal:
        """채널 수수료율 반환.

        Args:
            channel: 채널명 (coupang|naver|own|vendor)
        """
        if _HAS_VM:
            try:
                vm = _VMSettlement()
                rate = vm.get_fee_rate(channel)
                if rate is not None:
                    return Decimal(str(rate))
            except Exception:
                pass
        return _CHANNEL_RATES.get(channel.lower(), Decimal('0.08'))

    def calculate_channel_fee(self, channel: str, amount: Decimal) -> Decimal:
        """채널 수수료 금액 계산.

        Args:
            channel: 채널명
            amount: 거래 금액

        Returns:
            수수료 금액 (Decimal)
        """
        rate = self.get_fee_rate(channel)
        return (amount * rate).quantize(Decimal('1'))

    def calculate_pg_fee(self, pg: str, amount: Decimal) -> Decimal:
        """PG 수수료 금액 계산.

        Args:
            pg: PG 명 (toss|stripe|paypal)
            amount: 결제 금액

        Returns:
            수수료 금액 (Decimal)
        """
        rate = _PG_RATES.get(pg.lower(), Decimal('0'))
        return (amount * rate).quantize(Decimal('1'))
