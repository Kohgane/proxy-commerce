"""src/finance_automation/refund_reconciler.py — Phase 119: 환불 대사 처리."""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Optional

from .fee_calculator import ChannelFeeCalculator
from .ledger import Ledger
from .models import AccountCode, LedgerEntry
from .revenue_recognizer import RevenueRecognizer

logger = logging.getLogger(__name__)


class RefundReconciler:
    """환불 이벤트 기반 매출 역인식 및 수수료 역환급 대사.

    환불 시 매출 역인식 + 채널 수수료 역환급 분개를 생성한다.
    """

    def __init__(
        self,
        recognizer: RevenueRecognizer,
        fee_calc: ChannelFeeCalculator,
        ledger: Ledger,
    ) -> None:
        self._recognizer = recognizer
        self._fee_calc = fee_calc
        self._ledger = ledger

    def process_refund_event(self, event: dict) -> dict:
        """환불 이벤트 처리.

        Args:
            event: {order_id, channel, refund_amount, currency, pg, reason}

        Returns:
            처리 결과 요약 dict
        """
        order_id = event.get('order_id', '')
        channel = event.get('channel', '')
        refund_amount = Decimal(str(event.get('refund_amount', 0)))
        currency = event.get('currency', 'KRW')
        pg = event.get('pg', '')
        reason = event.get('reason', '')

        # 1. 매출 역인식
        rev_record = self._recognizer.reverse({
            'order_id': order_id,
            'channel': channel,
            'refund_amount': refund_amount,
            'currency': currency,
        })

        # 2. 채널 수수료 역환급 분개
        fee_amount = self._fee_calc.calculate_channel_fee(channel, refund_amount)
        if fee_amount > Decimal('0'):
            self._post_fee_reversal(order_id, channel, fee_amount, currency)

        # 3. PG 수수료 역환급 분개
        pg_fee = self._fee_calc.calculate_pg_fee(pg, refund_amount) if pg else Decimal('0')
        if pg_fee > Decimal('0'):
            self._post_pg_fee_reversal(order_id, pg, pg_fee, currency)

        logger.info("[환불대사] 주문 %s 환불 대사 완료: %s %s", order_id, refund_amount, currency)
        return {
            'order_id': order_id,
            'channel': channel,
            'refund_amount': str(refund_amount),
            'fee_reversal': str(fee_amount),
            'pg_fee_reversal': str(pg_fee),
            'currency': currency,
            'reason': reason,
            'status': 'reconciled',
        }

    def reconcile_partial_refund(
        self,
        order_id: str,
        refund_amount: Decimal,
        channel: str,
    ) -> dict:
        """부분 환불 대사.

        Args:
            order_id: 주문 ID
            refund_amount: 부분 환불 금액
            channel: 채널명
        """
        return self.process_refund_event({
            'order_id': order_id,
            'channel': channel,
            'refund_amount': str(refund_amount),
            'currency': 'KRW',
            'reason': 'partial_refund',
        })

    def _post_fee_reversal(
        self, order_id: str, channel: str, fee: Decimal, currency: str
    ) -> None:
        """채널 수수료 역환급 분개: DEBIT CHANNEL_FEE / CREDIT AP."""
        entries = [
            LedgerEntry(
                account=AccountCode.AP.value,
                debit=fee,
                credit=Decimal('0'),
                currency=currency,
                reference_type='fee_reversal',
                reference_id=order_id,
                memo=f'채널 수수료 역환급 ({channel}): {order_id}',
            ),
            LedgerEntry(
                account=AccountCode.CHANNEL_FEE.value,
                debit=Decimal('0'),
                credit=fee,
                currency=currency,
                reference_type='fee_reversal',
                reference_id=order_id,
                memo=f'채널 수수료 역환급 CHANNEL_FEE ({channel}): {order_id}',
            ),
        ]
        self._ledger.post(entries)

    def _post_pg_fee_reversal(
        self, order_id: str, pg: str, pg_fee: Decimal, currency: str
    ) -> None:
        """PG 수수료 역환급 분개: DEBIT AP / CREDIT CHANNEL_FEE."""
        entries = [
            LedgerEntry(
                account=AccountCode.AP.value,
                debit=pg_fee,
                credit=Decimal('0'),
                currency=currency,
                reference_type='pg_fee_reversal',
                reference_id=order_id,
                memo=f'PG 수수료 역환급 ({pg}): {order_id}',
            ),
            LedgerEntry(
                account=AccountCode.CHANNEL_FEE.value,
                debit=Decimal('0'),
                credit=pg_fee,
                currency=currency,
                reference_type='pg_fee_reversal',
                reference_id=order_id,
                memo=f'PG 수수료 역환급 CHANNEL_FEE ({pg}): {order_id}',
            ),
        ]
        self._ledger.post(entries)
