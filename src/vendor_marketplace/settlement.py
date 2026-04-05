"""src/vendor_marketplace/settlement.py — 정산 관리 시스템 (Phase 98)."""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Dict, List, Optional

from .commission import CommissionCalculator

logger = logging.getLogger(__name__)


class SettlementStatus(Enum):
    pending = 'pending'
    processing = 'processing'
    completed = 'completed'
    failed = 'failed'


class SettlementCycle(Enum):
    weekly = 'weekly'        # 주간
    biweekly = 'biweekly'   # 격주
    monthly = 'monthly'      # 월간


@dataclass
class Settlement:
    """정산 내역."""
    settlement_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    vendor_id: str = ''
    period_start: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    period_end: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    gross_sales: float = 0.0          # 총 매출
    commission: float = 0.0           # 수수료
    returns_deduction: float = 0.0    # 반품 차감
    net_amount: float = 0.0           # 정산액 (총매출 - 수수료 - 반품)
    status: SettlementStatus = SettlementStatus.pending
    cycle: str = SettlementCycle.weekly.value
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    error_message: str = ''
    order_count: int = 0
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            'settlement_id': self.settlement_id,
            'vendor_id': self.vendor_id,
            'period_start': self.period_start.isoformat(),
            'period_end': self.period_end.isoformat(),
            'gross_sales': self.gross_sales,
            'commission': self.commission,
            'returns_deduction': self.returns_deduction,
            'net_amount': self.net_amount,
            'status': self.status.value,
            'cycle': self.cycle,
            'order_count': self.order_count,
            'created_at': self.created_at.isoformat(),
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'error_message': self.error_message,
            'metadata': self.metadata,
        }


@dataclass
class PayoutRecord:
    """지급 기록."""
    payout_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    settlement_id: str = ''
    vendor_id: str = ''
    amount: float = 0.0
    bank_name: str = ''
    bank_account: str = ''
    bank_holder: str = ''
    status: str = 'pending'   # pending, processing, completed, failed
    requested_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    tx_id: str = ''

    def to_dict(self) -> dict:
        return {
            'payout_id': self.payout_id,
            'settlement_id': self.settlement_id,
            'vendor_id': self.vendor_id,
            'amount': self.amount,
            'bank_name': self.bank_name,
            'bank_account': self.bank_account,
            'bank_holder': self.bank_holder,
            'status': self.status,
            'requested_at': self.requested_at.isoformat(),
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'tx_id': self.tx_id,
        }


class SettlementReport:
    """판매자별 정산 리포트 생성."""

    def generate(
        self,
        vendor_id: str,
        settlements: List[Settlement],
        period_label: str = '',
    ) -> dict:
        """정산 리포트 생성."""
        total_gross = sum(s.gross_sales for s in settlements)
        total_commission = sum(s.commission for s in settlements)
        total_returns = sum(s.returns_deduction for s in settlements)
        total_net = sum(s.net_amount for s in settlements)
        total_orders = sum(s.order_count for s in settlements)

        return {
            'vendor_id': vendor_id,
            'period_label': period_label,
            'settlement_count': len(settlements),
            'total_gross_sales': round(total_gross, 2),
            'total_commission': round(total_commission, 2),
            'total_returns_deduction': round(total_returns, 2),
            'total_net_amount': round(total_net, 2),
            'total_order_count': total_orders,
            'effective_commission_rate': round(
                (total_commission / total_gross * 100) if total_gross else 0.0, 2
            ),
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'settlements': [s.to_dict() for s in settlements],
        }


class SettlementManager:
    """정산 관리 — 정산 생성, 조회, 상태 관리."""

    def __init__(
        self, calculator: Optional[CommissionCalculator] = None
    ) -> None:
        self._settlements: Dict[str, Settlement] = {}    # settlement_id → Settlement
        self._vendor_settlements: Dict[str, List[str]] = {}  # vendor_id → [settlement_id]
        self._calculator = calculator or CommissionCalculator()
        self._report = SettlementReport()

    def generate_settlement(
        self,
        vendor_id: str,
        orders: List[dict],
        vendor_tier: str = 'basic',
        cycle: str = SettlementCycle.weekly.value,
        period_start: Optional[datetime] = None,
        period_end: Optional[datetime] = None,
    ) -> Settlement:
        """정산 생성.

        orders: [{'order_id', 'amount', 'category', 'is_return': bool}]
        """
        now = datetime.now(timezone.utc)
        if period_start is None:
            period_start = now - timedelta(days=7)
        if period_end is None:
            period_end = now

        gross_sales = 0.0
        commission = 0.0
        returns_deduction = 0.0
        order_count = 0

        for order in orders:
            amount = float(order.get('amount', 0))
            is_return = order.get('is_return', False)
            category = order.get('category', '')

            if is_return:
                returns_deduction += amount
                continue

            calc = self._calculator.calculate(
                amount=amount,
                vendor_tier=vendor_tier,
                category=category,
            )
            gross_sales += amount
            commission += calc['commission']
            order_count += 1

        net_amount = round(gross_sales - commission - returns_deduction, 2)

        settlement = Settlement(
            vendor_id=vendor_id,
            period_start=period_start,
            period_end=period_end,
            gross_sales=round(gross_sales, 2),
            commission=round(commission, 2),
            returns_deduction=round(returns_deduction, 2),
            net_amount=net_amount,
            cycle=cycle,
            order_count=order_count,
        )
        self._settlements[settlement.settlement_id] = settlement
        self._vendor_settlements.setdefault(vendor_id, []).append(settlement.settlement_id)
        logger.info('정산 생성: %s (판매자: %s, 순수익: %s)', settlement.settlement_id, vendor_id, net_amount)
        return settlement

    def process_settlement(self, settlement_id: str) -> Settlement:
        """정산 처리 시작 (pending → processing)."""
        s = self._get_or_raise(settlement_id)
        if s.status != SettlementStatus.pending:
            raise ValueError(f'처리 불가 상태: {s.status.value}')
        s.status = SettlementStatus.processing
        return s

    def complete_settlement(self, settlement_id: str) -> Settlement:
        """정산 완료 (processing → completed)."""
        s = self._get_or_raise(settlement_id)
        if s.status != SettlementStatus.processing:
            raise ValueError(f'완료 불가 상태: {s.status.value}')
        s.status = SettlementStatus.completed
        s.completed_at = datetime.now(timezone.utc)
        return s

    def fail_settlement(self, settlement_id: str, error: str = '') -> Settlement:
        """정산 실패."""
        s = self._get_or_raise(settlement_id)
        s.status = SettlementStatus.failed
        s.error_message = error
        return s

    def get_settlement(self, settlement_id: str) -> Optional[Settlement]:
        return self._settlements.get(settlement_id)

    def list_vendor_settlements(
        self, vendor_id: str, status: Optional[str] = None
    ) -> List[Settlement]:
        ids = self._vendor_settlements.get(vendor_id, [])
        settlements = [self._settlements[sid] for sid in ids if sid in self._settlements]
        if status:
            settlements = [s for s in settlements if s.status.value == status]
        return settlements

    def generate_report(self, vendor_id: str, period_label: str = '') -> dict:
        settlements = self.list_vendor_settlements(vendor_id)
        return self._report.generate(vendor_id, settlements, period_label)

    def _get_or_raise(self, settlement_id: str) -> Settlement:
        s = self._settlements.get(settlement_id)
        if s is None:
            raise KeyError(f'정산 없음: {settlement_id}')
        return s


class PayoutService:
    """정산금 지급 처리 (mock)."""

    def __init__(self) -> None:
        self._accounts: Dict[str, dict] = {}   # vendor_id → bank info
        self._payouts: Dict[str, PayoutRecord] = {}

    def register_bank_account(
        self, vendor_id: str, bank_name: str, account: str, holder: str
    ) -> dict:
        """은행 계좌 등록."""
        info = {
            'vendor_id': vendor_id,
            'bank_name': bank_name,
            'bank_account': account,
            'bank_holder': holder,
            'registered_at': datetime.now(timezone.utc).isoformat(),
        }
        self._accounts[vendor_id] = info
        return info

    def get_bank_account(self, vendor_id: str) -> Optional[dict]:
        return self._accounts.get(vendor_id)

    def request_payout(self, settlement: Settlement) -> PayoutRecord:
        """지급 요청 (mock)."""
        account = self._accounts.get(settlement.vendor_id)
        if account is None:
            raise ValueError(f'등록된 계좌 없음: {settlement.vendor_id}')
        if settlement.status != SettlementStatus.completed:
            raise ValueError(f'완료되지 않은 정산: {settlement.settlement_id}')

        payout = PayoutRecord(
            settlement_id=settlement.settlement_id,
            vendor_id=settlement.vendor_id,
            amount=settlement.net_amount,
            bank_name=account['bank_name'],
            bank_account=account['bank_account'],
            bank_holder=account['bank_holder'],
            status='processing',
            tx_id=f'TX-{uuid.uuid4().hex[:8].upper()}',
        )
        payout.completed_at = datetime.now(timezone.utc)
        payout.status = 'completed'
        self._payouts[payout.payout_id] = payout
        logger.info('지급 완료: %s (금액: %s)', payout.payout_id, payout.amount)
        return payout

    def get_payout_history(self, vendor_id: str) -> List[PayoutRecord]:
        return [p for p in self._payouts.values() if p.vendor_id == vendor_id]
