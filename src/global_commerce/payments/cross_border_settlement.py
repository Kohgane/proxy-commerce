"""src/global_commerce/payments/cross_border_settlement.py — 해외 결제 정산 (Phase 93)."""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# 통화별 환전 수수료율
_FX_FEE_RATES: Dict[str, float] = {
    'KRW': 0.0,
    'USD': 0.015,   # 1.5%
    'EUR': 0.015,
    'GBP': 0.018,
    'JPY': 0.012,
    'CNY': 0.020,
    'AUD': 0.015,
    'CAD': 0.015,
}

# 통화별 정산 주기 (일)
_SETTLEMENT_CYCLES: Dict[str, int] = {
    'KRW': 1,
    'USD': 2,
    'EUR': 2,
    'GBP': 3,
    'JPY': 2,
    'CNY': 5,
    'AUD': 2,
    'CAD': 2,
}

# 해외 송금 최소 수수료 (KRW)
_REMITTANCE_MIN_FEE_KRW = 5000
# 해외 송금 수수료율
_REMITTANCE_FEE_RATE = 0.005


@dataclass
class SettlementRecord:
    """정산 기록."""
    settlement_id: str
    order_id: str
    original_amount: float
    original_currency: str
    settled_amount_krw: float
    fx_rate: float
    fx_fee: float
    remittance_fee: float
    net_amount_krw: float
    settlement_days: int
    status: str = 'pending'
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return {
            'settlement_id': self.settlement_id,
            'order_id': self.order_id,
            'original_amount': self.original_amount,
            'original_currency': self.original_currency,
            'settled_amount_krw': self.settled_amount_krw,
            'fx_rate': self.fx_rate,
            'fx_fee': self.fx_fee,
            'remittance_fee': self.remittance_fee,
            'net_amount_krw': self.net_amount_krw,
            'settlement_days': self.settlement_days,
            'status': self.status,
            'created_at': self.created_at,
        }


class CrossBorderSettlement:
    """해외 결제 정산 로직 — 환전 수수료 계산, 해외 송금 시뮬레이션."""

    # 기본 환율 (KRW 기준, mock)
    _FX_RATES: Dict[str, float] = {
        'KRW': 1.0,
        'USD': 1350.0,
        'EUR': 1470.0,
        'GBP': 1710.0,
        'JPY': 9.0,
        'CNY': 185.0,
        'AUD': 880.0,
        'CAD': 990.0,
    }

    def __init__(self):
        self._records: Dict[str, SettlementRecord] = {}

    def calculate_fx_fee(self, amount: float, currency: str) -> float:
        """환전 수수료 계산.

        Args:
            amount: 원화 금액
            currency: 결제 통화

        Returns:
            환전 수수료 (KRW)
        """
        rate = _FX_FEE_RATES.get(currency.upper(), 0.015)
        return round(amount * rate, 2)

    def calculate_remittance_fee(self, amount_krw: float) -> float:
        """해외 송금 수수료 계산.

        Args:
            amount_krw: 송금 금액 (KRW)

        Returns:
            송금 수수료 (KRW)
        """
        fee = max(_REMITTANCE_MIN_FEE_KRW, amount_krw * _REMITTANCE_FEE_RATE)
        return round(fee, 2)

    def to_krw(self, amount: float, currency: str) -> float:
        """외화를 원화로 환산 (mock 환율 사용).

        Args:
            amount: 외화 금액
            currency: 외화 통화 코드

        Returns:
            원화 환산 금액
        """
        rate = self._FX_RATES.get(currency.upper(), 1350.0)
        return round(amount * rate, 2)

    def settle(self, order_id: str, amount: float, currency: str) -> SettlementRecord:
        """결제 정산 처리.

        Args:
            order_id: 주문 ID
            amount: 결제 금액 (외화)
            currency: 결제 통화

        Returns:
            SettlementRecord
        """
        currency = currency.upper()
        fx_rate = self._FX_RATES.get(currency, 1350.0)
        settled_krw = self.to_krw(amount, currency)
        fx_fee = self.calculate_fx_fee(settled_krw, currency)
        remittance_fee = self.calculate_remittance_fee(settled_krw) if currency != 'KRW' else 0.0
        net_krw = settled_krw - fx_fee - remittance_fee
        days = _SETTLEMENT_CYCLES.get(currency, 2)

        record = SettlementRecord(
            settlement_id=str(uuid.uuid4()),
            order_id=order_id,
            original_amount=amount,
            original_currency=currency,
            settled_amount_krw=settled_krw,
            fx_rate=fx_rate,
            fx_fee=fx_fee,
            remittance_fee=remittance_fee,
            net_amount_krw=net_krw,
            settlement_days=days,
            status='pending',
        )
        self._records[record.settlement_id] = record
        logger.info("정산 생성: %s order=%s currency=%s amount=%s", record.settlement_id, order_id, currency, amount)
        return record

    def get_settlement_cycle(self, currency: str) -> int:
        """통화별 정산 주기(일) 반환."""
        return _SETTLEMENT_CYCLES.get(currency.upper(), 2)

    def list_records(self, order_id: Optional[str] = None) -> List[SettlementRecord]:
        if order_id:
            return [r for r in self._records.values() if r.order_id == order_id]
        return list(self._records.values())
