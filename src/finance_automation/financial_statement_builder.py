"""src/finance_automation/financial_statement_builder.py — Phase 119: 재무제표 빌더."""
from __future__ import annotations

import logging
from decimal import Decimal

from .ledger import Ledger
from .models import AccountCode, FinancialStatement

logger = logging.getLogger(__name__)


class FinancialStatementBuilder:
    """손익계산서(P&L), 재무상태표(BS), 현금흐름표(CF) 자동 생성."""

    def __init__(self, ledger: Ledger) -> None:
        self._ledger = ledger

    def build(self, stmt_type: str, period: str) -> FinancialStatement:
        """재무제표 빌드.

        Args:
            stmt_type: pnl|bs|cf
            period: 기간 (YYYY-MM 또는 YYYY)
        """
        if stmt_type == 'pnl':
            return self.build_pnl(period)
        if stmt_type == 'bs':
            return self.build_bs(period)
        if stmt_type == 'cf':
            return self.build_cf(period)
        raise ValueError(f'지원하지 않는 재무제표 유형: {stmt_type}')

    def build_pnl(self, period: str) -> FinancialStatement:
        """손익계산서 생성.

        Args:
            period: 집계 기간

        Returns:
            FinancialStatement (pnl)
        """
        tb = self._ledger.trial_balance(period)

        revenue = self._net(tb, AccountCode.REVENUE.value, credit_positive=True)
        cogs = self._net(tb, AccountCode.COGS.value, credit_positive=False)
        gross_profit = revenue - cogs
        channel_fee = self._net(tb, AccountCode.CHANNEL_FEE.value, credit_positive=False)
        shipping = self._net(tb, AccountCode.SHIPPING_OUT.value, credit_positive=False)
        customs = self._net(tb, AccountCode.CUSTOMS_DUTY.value, credit_positive=False)
        fx_gain = self._net(tb, AccountCode.FX_GAIN.value, credit_positive=True)
        fx_loss = self._net(tb, AccountCode.FX_LOSS.value, credit_positive=False)
        fx_pnl = fx_gain - fx_loss
        refund = self._net(tb, AccountCode.REFUND.value, credit_positive=False)
        net_income = gross_profit - channel_fee - shipping - customs + fx_pnl - refund

        line_items = [
            {'name': '매출', 'amount': str(revenue)},
            {'name': '매출원가(COGS)', 'amount': str(cogs)},
            {'name': '매출총이익', 'amount': str(gross_profit)},
            {'name': '채널 수수료', 'amount': str(channel_fee)},
            {'name': '배송비', 'amount': str(shipping)},
            {'name': '관세', 'amount': str(customs)},
            {'name': '외환 손익', 'amount': str(fx_pnl)},
            {'name': '환불', 'amount': str(refund)},
            {'name': '순이익', 'amount': str(net_income)},
        ]
        return FinancialStatement(
            type='pnl',
            period=period,
            line_items=line_items,
            totals={'revenue': str(revenue), 'net_income': str(net_income)},
        )

    def build_bs(self, period: str) -> FinancialStatement:
        """재무상태표 생성.

        Args:
            period: 집계 기간

        Returns:
            FinancialStatement (bs)
        """
        tb = self._ledger.trial_balance(period)

        cash = self._net(tb, AccountCode.CASH.value, credit_positive=False)
        ar = self._net(tb, AccountCode.AR.value, credit_positive=False)
        ap = self._net(tb, AccountCode.AP.value, credit_positive=True)
        equity = cash + ar - ap

        line_items = [
            {'name': '현금(Cash)', 'amount': str(cash)},
            {'name': '매출채권(AR)', 'amount': str(ar)},
            {'name': '매입채무(AP)', 'amount': str(ap)},
            {'name': '자본(Equity)', 'amount': str(equity)},
        ]
        return FinancialStatement(
            type='bs',
            period=period,
            line_items=line_items,
            totals={'total_assets': str(cash + ar), 'total_liabilities': str(ap), 'equity': str(equity)},
        )

    def build_cf(self, period: str) -> FinancialStatement:
        """현금흐름표 생성.

        Args:
            period: 집계 기간

        Returns:
            FinancialStatement (cf)
        """
        tb = self._ledger.trial_balance(period)

        revenue = self._net(tb, AccountCode.REVENUE.value, credit_positive=True)
        cogs = self._net(tb, AccountCode.COGS.value, credit_positive=False)
        operating_cf = revenue - cogs
        investing_cf = Decimal('0')
        financing_cf = Decimal('0')

        line_items = [
            {'name': '영업 현금흐름', 'amount': str(operating_cf)},
            {'name': '투자 현금흐름', 'amount': str(investing_cf)},
            {'name': '재무 현금흐름', 'amount': str(financing_cf)},
        ]
        return FinancialStatement(
            type='cf',
            period=period,
            line_items=line_items,
            totals={
                'operating_cf': str(operating_cf),
                'investing_cf': str(investing_cf),
                'financing_cf': str(financing_cf),
                'net_cf': str(operating_cf + investing_cf + financing_cf),
            },
        )

    def _net(self, tb: dict, account: str, credit_positive: bool) -> Decimal:
        """시산표에서 계정 순액 추출."""
        if account not in tb:
            return Decimal('0')
        entry = tb[account]
        if credit_positive:
            return entry['credit'] - entry['debit']
        return entry['debit'] - entry['credit']
