"""src/finance_automation/cost_aggregator.py — Phase 119: 매입 원가 집계."""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Dict, List

from .ledger import Ledger
from .models import AccountCode, CostRecord, LedgerEntry

logger = logging.getLogger(__name__)


class CostAggregator:
    """매입 원가 기록 및 집계.

    COGS, 배송비, 관세를 분개하고 AP(매입채무)를 기록한다.
    """

    def __init__(self, ledger: Ledger) -> None:
        self._ledger = ledger
        self._records: Dict[str, CostRecord] = {}

    def record_purchase(self, data: dict) -> CostRecord:
        """매입 기록 및 분개 전기.

        Args:
            data: {purchase_id, source, cogs, shipping, customs, fx_rate_at_purchase, currency}

        Returns:
            생성된 CostRecord
        """
        purchase_id = data.get('purchase_id', '')
        source = data.get('source', '')
        cogs = Decimal(str(data.get('cogs', 0)))
        shipping = Decimal(str(data.get('shipping', 0)))
        customs = Decimal(str(data.get('customs', 0)))
        fx_rate = Decimal(str(data.get('fx_rate_at_purchase', 1)))
        currency = data.get('currency', 'KRW')

        record = CostRecord(
            purchase_id=purchase_id,
            source=source,
            cogs=cogs,
            shipping=shipping,
            customs=customs,
            fx_rate_at_purchase=fx_rate,
            currency=currency,
        )
        self._records[purchase_id] = record

        entries = self._make_cost_entries(record)
        self._ledger.post(entries)
        logger.info("[매입집계] 매입 기록: %s COGS=%s", purchase_id, cogs)
        return record

    def get_costs_by_period(self, start: str, end: str) -> List[CostRecord]:
        """기간별 원가 레코드 조회.

        원장 COGS 계정 조회를 통해 해당 기간의 purchase_id를 추출한다.

        Args:
            start: 시작일 (YYYY-MM-DD)
            end: 종료일 (YYYY-MM-DD)
        """
        entries = self._ledger.query(AccountCode.COGS.value, start, end)
        purchase_ids = {e.reference_id for e in entries}
        return [r for pid, r in self._records.items() if pid in purchase_ids]

    def get_all_records(self) -> List[CostRecord]:
        """전체 원가 레코드 반환."""
        return list(self._records.values())

    def _make_cost_entries(self, record: CostRecord) -> List[LedgerEntry]:
        """원가 분개 생성: DEBIT COGS/SHIPPING/CUSTOMS / CREDIT AP."""
        entries: List[LedgerEntry] = []
        total = Decimal('0')

        for account, amount in [
            (AccountCode.COGS.value, record.cogs),
            (AccountCode.SHIPPING_OUT.value, record.shipping),
            (AccountCode.CUSTOMS_DUTY.value, record.customs),
        ]:
            if amount > Decimal('0'):
                entries.append(LedgerEntry(
                    account=account,
                    debit=amount,
                    credit=Decimal('0'),
                    currency=record.currency,
                    fx_rate=record.fx_rate_at_purchase,
                    reference_type='purchase',
                    reference_id=record.purchase_id,
                    memo=f'매입 {account}: {record.purchase_id}',
                ))
                total += amount

        if total > Decimal('0'):
            entries.append(LedgerEntry(
                account=AccountCode.AP.value,
                debit=Decimal('0'),
                credit=total,
                currency=record.currency,
                fx_rate=record.fx_rate_at_purchase,
                reference_type='purchase',
                reference_id=record.purchase_id,
                memo=f'매입채무 AP: {record.purchase_id}',
            ))
        return entries
