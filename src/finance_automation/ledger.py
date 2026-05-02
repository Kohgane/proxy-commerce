"""src/finance_automation/ledger.py — Phase 119: 복식부기 원장."""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Dict, List

from .models import LedgerEntry

logger = logging.getLogger(__name__)


class Ledger:
    """인메모리 복식부기 원장.

    모든 재무 거래는 대변/차변 균형을 맞춰야 한다.
    """

    def __init__(self) -> None:
        self._entries: Dict[str, LedgerEntry] = {}

    def post(self, entries: List[LedgerEntry]) -> None:
        """복식부기 분개 전기.

        대변 합계와 차변 합계가 일치해야 한다. 불일치 시 ValueError.

        Args:
            entries: 분개 항목 목록 (대차 균형 필수)
        """
        total_debit = sum(e.debit for e in entries)
        total_credit = sum(e.credit for e in entries)
        if total_debit != total_credit:
            raise ValueError(
                f'대차 불균형: 차변 {total_debit} ≠ 대변 {total_credit}'
            )
        for entry in entries:
            self._entries[entry.entry_id] = entry
        logger.debug("[원장] %d개 항목 전기 완료", len(entries))

    def query(
        self,
        account: str,
        period_start: str = '',
        period_end: str = '',
    ) -> List[LedgerEntry]:
        """계정별 원장 조회.

        Args:
            account: 계정 코드
            period_start: 시작일 (YYYY-MM-DD, 포함)
            period_end: 종료일 (YYYY-MM-DD, 포함)
        """
        result = []
        for entry in self._entries.values():
            if account and entry.account != account:
                continue
            if period_start and entry.date < period_start:
                continue
            if period_end and entry.date > period_end:
                continue
            result.append(entry)
        return result

    def trial_balance(self, period: str = '') -> dict:
        """시산표 계산.

        Args:
            period: 기간 접두어 (YYYY-MM 또는 YYYY). 빈 문자열이면 전체.

        Returns:
            {account: {debit, credit, net}} 형태의 dict
        """
        balance: Dict[str, Dict[str, Decimal]] = {}
        for entry in self._entries.values():
            if period and not entry.date.startswith(period):
                continue
            acc = entry.account
            if acc not in balance:
                balance[acc] = {'debit': Decimal('0'), 'credit': Decimal('0'), 'net': Decimal('0')}
            balance[acc]['debit'] += entry.debit
            balance[acc]['credit'] += entry.credit
            balance[acc]['net'] = balance[acc]['debit'] - balance[acc]['credit']
        return balance

    def lock_period(self, date_str: str) -> int:
        """지정 일자까지의 원장 항목을 잠금.

        Args:
            date_str: 잠금 기준일 (YYYY-MM-DD, 포함)

        Returns:
            잠금 처리된 항목 수
        """
        count = 0
        for entry in self._entries.values():
            if entry.date <= date_str and not entry.locked:
                entry.locked = True
                count += 1
        logger.info("[원장] %s까지 %d개 항목 잠금", date_str, count)
        return count

    def all_entries(self) -> List[LedgerEntry]:
        """전체 원장 항목 반환."""
        return list(self._entries.values())
