"""src/finance_automation/revenue_recognizer.py — Phase 119: 매출 인식 엔진."""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import List

from .ledger import Ledger
from .models import AccountCode, LedgerEntry, RevenueRecord

logger = logging.getLogger(__name__)


class RevenueRecognizer:
    """주문 이벤트 기반 매출 인식 및 분개 생성.

    DEBIT AR / CREDIT REVENUE 분개를 자동 생성한다.
    환불 시 역분개를 생성한다.
    """

    def __init__(self, ledger: Ledger) -> None:
        self._ledger = ledger

    def recognize(self, order: dict) -> RevenueRecord:
        """주문 확정 시 매출 인식.

        Args:
            order: {order_id, channel, gross_amount, net_amount, currency}

        Returns:
            생성된 RevenueRecord
        """
        order_id = order.get('order_id', '')
        channel = order.get('channel', '')
        gross = Decimal(str(order.get('gross_amount', 0)))
        net = Decimal(str(order.get('net_amount', gross)))
        currency = order.get('currency', 'KRW')

        record = RevenueRecord(
            order_id=order_id,
            channel=channel,
            gross_amount=gross,
            net_amount=net,
            currency=currency,
        )
        entries = self._make_revenue_entries(record)
        self._ledger.post(entries)
        logger.info("[매출인식] 주문 %s 매출 인식: %s %s", order_id, net, currency)
        return record

    def reverse(self, refund: dict) -> RevenueRecord:
        """환불 시 매출 역인식.

        Args:
            refund: {order_id, channel, refund_amount, currency}

        Returns:
            역인식 RevenueRecord
        """
        order_id = refund.get('order_id', '')
        channel = refund.get('channel', '')
        amount = Decimal(str(refund.get('refund_amount', 0)))
        currency = refund.get('currency', 'KRW')

        record = RevenueRecord(
            order_id=order_id,
            channel=channel,
            gross_amount=-amount,
            net_amount=-amount,
            currency=currency,
            refunded_amount=amount,
        )
        entries = self._make_refund_entries(record, amount)
        self._ledger.post(entries)
        logger.info("[매출역인식] 주문 %s 환불: %s %s", order_id, amount, currency)
        return record

    def _make_revenue_entries(self, record: RevenueRecord) -> List[LedgerEntry]:
        """매출 분개 생성: DEBIT AR / CREDIT REVENUE."""
        amount = record.net_amount
        debit_entry = LedgerEntry(
            account=AccountCode.AR.value,
            debit=amount,
            credit=Decimal('0'),
            currency=record.currency,
            reference_type='order',
            reference_id=record.order_id,
            memo=f'매출인식 AR: {record.order_id}',
        )
        credit_entry = LedgerEntry(
            account=AccountCode.REVENUE.value,
            debit=Decimal('0'),
            credit=amount,
            currency=record.currency,
            reference_type='order',
            reference_id=record.order_id,
            memo=f'매출인식 REVENUE: {record.order_id}',
        )
        return [debit_entry, credit_entry]

    def _make_refund_entries(self, record: RevenueRecord, amount: Decimal) -> List[LedgerEntry]:
        """환불 분개 생성: DEBIT REFUND / CREDIT AR."""
        debit_entry = LedgerEntry(
            account=AccountCode.REFUND.value,
            debit=amount,
            credit=Decimal('0'),
            currency=record.currency,
            reference_type='refund',
            reference_id=record.order_id,
            memo=f'환불 REFUND: {record.order_id}',
        )
        credit_entry = LedgerEntry(
            account=AccountCode.AR.value,
            debit=Decimal('0'),
            credit=amount,
            currency=record.currency,
            reference_type='refund',
            reference_id=record.order_id,
            memo=f'환불 AR 감소: {record.order_id}',
        )
        return [debit_entry, credit_entry]
