"""src/finance_automation/settlement_orchestrator.py — Phase 119: 채널 정산 오케스트레이터."""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Dict, List, Optional

from .fee_calculator import ChannelFeeCalculator
from .models import RevenueRecord, SettlementBatch

logger = logging.getLogger(__name__)

# 채널별 정산 주기
_SETTLEMENT_CYCLES: dict = {
    'coupang': 'weekly',
    'naver': 'daily',
    'vendor': 'monthly',
    'own': 'monthly',
}


class SettlementOrchestrator:
    """채널별 정산 배치 생성 및 관리.

    채널 수수료 차감 후 순 정산 금액을 산출한다.
    """

    def __init__(self, fee_calc: ChannelFeeCalculator) -> None:
        self._fee_calc = fee_calc
        self._batches: Dict[str, SettlementBatch] = {}

    def create_batch(
        self,
        channel: str,
        period_start: str,
        period_end: str,
        revenue_records: List[RevenueRecord],
    ) -> SettlementBatch:
        """정산 배치 생성.

        Args:
            channel: 채널명
            period_start: 정산 시작일 (YYYY-MM-DD)
            period_end: 정산 종료일 (YYYY-MM-DD)
            revenue_records: 해당 기간 매출 레코드 목록

        Returns:
            생성된 SettlementBatch
        """
        gross = sum(r.gross_amount for r in revenue_records if r.channel == channel)
        fees = self._fee_calc.calculate_channel_fee(channel, gross)
        net = gross - fees

        batch = SettlementBatch(
            channel=channel,
            period_start=period_start,
            period_end=period_end,
            gross=gross,
            fees=fees,
            net=net,
            status='draft',
        )
        self._batches[batch.batch_id] = batch
        logger.info("[정산] 배치 생성: %s 채널=%s gross=%s net=%s", batch.batch_id, channel, gross, net)
        return batch

    def finalize_batch(self, batch_id: str) -> SettlementBatch:
        """정산 배치 확정.

        Args:
            batch_id: 정산 배치 ID

        Returns:
            확정된 SettlementBatch
        """
        batch = self._batches.get(batch_id)
        if batch is None:
            raise KeyError(f'정산 배치를 찾을 수 없습니다: {batch_id}')
        batch.status = 'finalized'
        logger.info("[정산] 배치 확정: %s", batch_id)
        return batch

    def get_batch(self, batch_id: str) -> Optional[SettlementBatch]:
        """정산 배치 조회.

        Args:
            batch_id: 정산 배치 ID
        """
        return self._batches.get(batch_id)

    def list_batches(self, channel: str = '') -> List[SettlementBatch]:
        """정산 배치 목록 조회.

        Args:
            channel: 채널 필터 (빈 문자열이면 전체)
        """
        batches = list(self._batches.values())
        if channel:
            batches = [b for b in batches if b.channel == channel]
        return batches

    def get_cycle(self, channel: str) -> str:
        """채널 정산 주기 반환."""
        return _SETTLEMENT_CYCLES.get(channel.lower(), 'monthly')
