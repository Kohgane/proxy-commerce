"""src/multicurrency/settlement.py — Phase 45: 통화별 정산 계산."""
import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# 기본 수수료 설정 (통화별)
DEFAULT_FEE_RATES: Dict[str, dict] = {
    'KRW': {'fee_pct': 0.0, 'min_fee': 0, 'settlement_currency': 'KRW'},
    'USD': {'fee_pct': 1.5, 'min_fee': 500, 'settlement_currency': 'KRW'},
    'JPY': {'fee_pct': 1.0, 'min_fee': 300, 'settlement_currency': 'KRW'},
    'CNY': {'fee_pct': 2.0, 'min_fee': 400, 'settlement_currency': 'KRW'},
    'EUR': {'fee_pct': 1.5, 'min_fee': 600, 'settlement_currency': 'KRW'},
}


class SettlementCalculator:
    """통화별 정산 계산 (환전 수수료%, 최소 수수료, 정산 통화)."""

    def __init__(self, fee_rates: Optional[Dict[str, dict]] = None):
        self._fee_rates = dict(DEFAULT_FEE_RATES)
        if fee_rates:
            self._fee_rates.update(fee_rates)

    def calculate(
        self,
        amount_krw: float,
        source_currency: str,
        converter=None,
    ) -> dict:
        """정산 금액 계산.

        Args:
            amount_krw:       KRW 기준 금액
            source_currency:  원래 통화
            converter:        CurrencyConverter (선택)
        """
        source_currency = source_currency.upper()
        fee_config = self._fee_rates.get(source_currency, {'fee_pct': 1.0, 'min_fee': 0})
        fee_pct = Decimal(str(fee_config.get('fee_pct', 0)))
        min_fee = Decimal(str(fee_config.get('min_fee', 0)))
        amount = Decimal(str(amount_krw))
        fee = (amount * fee_pct / 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
        fee = max(fee, min_fee)
        net = amount - fee
        return {
            'gross_amount_krw': float(amount),
            'fee_pct': float(fee_pct),
            'fee_amount_krw': float(fee),
            'net_amount_krw': float(net),
            'source_currency': source_currency,
        }
