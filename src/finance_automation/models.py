"""src/finance_automation/models.py — Phase 119: 정산/회계 자동화 데이터 모델."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional
from uuid import uuid4


class AccountCode(str, Enum):
    """복식부기 계정 코드."""
    REVENUE = 'revenue'
    COGS = 'cogs'
    CHANNEL_FEE = 'channel_fee'
    SHIPPING_OUT = 'shipping_out'
    CUSTOMS_DUTY = 'customs_duty'
    FX_GAIN = 'fx_gain'
    FX_LOSS = 'fx_loss'
    REFUND = 'refund'
    POINT_LIABILITY = 'point_liability'
    CASH = 'cash'
    AR = 'ar'
    AP = 'ap'


@dataclass
class LedgerEntry:
    """복식부기 원장 항목."""
    entry_id: str = field(default_factory=lambda: str(uuid4()))
    date: str = field(default_factory=lambda: datetime.now(timezone.utc).date().isoformat())
    account: str = ''
    debit: Decimal = Decimal('0')
    credit: Decimal = Decimal('0')
    currency: str = 'KRW'
    fx_rate: Decimal = Decimal('1')
    reference_type: str = ''
    reference_id: str = ''
    memo: str = ''
    locked: bool = False


@dataclass
class RevenueRecord:
    """매출 인식 레코드."""
    order_id: str
    channel: str
    gross_amount: Decimal
    net_amount: Decimal
    currency: str = 'KRW'
    recognized_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    refunded_amount: Decimal = Decimal('0')


@dataclass
class CostRecord:
    """매입 원가 레코드."""
    purchase_id: str
    source: str
    cogs: Decimal
    shipping: Decimal = Decimal('0')
    customs: Decimal = Decimal('0')
    fx_rate_at_purchase: Decimal = Decimal('1')
    currency: str = 'KRW'


@dataclass
class SettlementBatch:
    """채널 정산 배치."""
    batch_id: str = field(default_factory=lambda: str(uuid4()))
    channel: str = ''
    period_start: str = ''
    period_end: str = ''
    gross: Decimal = Decimal('0')
    fees: Decimal = Decimal('0')
    net: Decimal = Decimal('0')
    status: str = 'draft'  # draft|finalized|paid


@dataclass
class FxPnL:
    """외환 손익 레코드."""
    purchase_id: str
    fx_at_purchase: Decimal
    fx_at_settlement: Decimal
    realized_pnl_krw: Decimal = Decimal('0')


@dataclass
class PeriodClose:
    """기간 마감 레코드."""
    period: str
    type: str  # daily|weekly|monthly
    status: str = 'open'  # open|closed
    closed_at: Optional[str] = None
    totals: dict = field(default_factory=dict)


@dataclass
class FinancialStatement:
    """재무제표."""
    type: str  # pnl|bs|cf
    period: str
    line_items: List[dict] = field(default_factory=list)
    totals: dict = field(default_factory=dict)


@dataclass
class TaxReport:
    """세무 리포트."""
    period: str
    vat_payable: Decimal = Decimal('0')
    vat_receivable: Decimal = Decimal('0')
    customs_paid: Decimal = Decimal('0')
    total_taxable: Decimal = Decimal('0')


@dataclass
class FinanceAnomaly:
    """재무 이상 감지 레코드."""
    type: str
    severity: str  # low|medium|high|critical
    reference: str
    detected_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    detail: str = ''
