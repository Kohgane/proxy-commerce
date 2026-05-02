"""src/finance_automation/anomaly_detector.py — Phase 119: 재무 이상 감지."""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import List, Optional

from .fee_calculator import ChannelFeeCalculator
from .ledger import Ledger
from .models import (
    CostRecord,
    FinanceAnomaly,
    FxPnL,
    LedgerEntry,
    RevenueRecord,
    SettlementBatch,
)

logger = logging.getLogger(__name__)


class FinanceAnomalyDetector:
    """재무 이상 거래 자동 감지.

    마이너스 마진, FX 손실 한도 초과, 미정산, 중복 분개, 매출 불일치 등을 탐지한다.
    """

    def __init__(self, ledger: Ledger, fee_calc: ChannelFeeCalculator) -> None:
        self._ledger = ledger
        self._fee_calc = fee_calc

    def detect_negative_margin(
        self,
        record: RevenueRecord,
        cost: CostRecord,
    ) -> Optional[FinanceAnomaly]:
        """마이너스 마진 감지.

        Args:
            record: 매출 레코드
            cost: 원가 레코드

        Returns:
            이상 감지 시 FinanceAnomaly, 정상이면 None
        """
        total_cost = cost.cogs + cost.shipping + cost.customs
        margin = record.net_amount - total_cost
        if margin < Decimal('0'):
            return FinanceAnomaly(
                type='negative_margin',
                severity='high',
                reference=record.order_id,
                detail=f'마진 {margin} KRW (매출={record.net_amount}, 원가={total_cost})',
            )
        return None

    def detect_fx_loss(
        self,
        pnl: FxPnL,
        threshold_krw: Decimal = Decimal('50000'),
    ) -> Optional[FinanceAnomaly]:
        """FX 손실 한도 초과 감지.

        Args:
            pnl: FxPnL 레코드
            threshold_krw: 손실 임계값 (KRW)

        Returns:
            임계값 초과 손실 시 FinanceAnomaly, 정상이면 None
        """
        if pnl.realized_pnl_krw < -threshold_krw:
            return FinanceAnomaly(
                type='fx_loss_exceeded',
                severity='medium',
                reference=pnl.purchase_id,
                detail=f'FX 실현 손실 {pnl.realized_pnl_krw} KRW (임계값 -{threshold_krw})',
            )
        return None

    def detect_missing_settlement(
        self,
        batches: List[SettlementBatch],
        expected_channels: List[str],
    ) -> List[FinanceAnomaly]:
        """미정산 채널 감지.

        Args:
            batches: 정산 배치 목록
            expected_channels: 정산 예상 채널 목록

        Returns:
            미정산 채널별 FinanceAnomaly 목록
        """
        finalized_channels = {b.channel for b in batches if b.status == 'finalized'}
        anomalies = []
        for channel in expected_channels:
            if channel not in finalized_channels:
                anomalies.append(FinanceAnomaly(
                    type='missing_settlement',
                    severity='high',
                    reference=channel,
                    detail=f'채널 {channel} 정산 누락',
                ))
        return anomalies

    def detect_duplicate_entries(
        self,
        entries: List[LedgerEntry],
    ) -> List[FinanceAnomaly]:
        """원장 중복 분개 감지.

        동일 reference_id + account + amount 조합이 중복되면 이상으로 처리한다.

        Args:
            entries: 원장 항목 목록

        Returns:
            중복 항목별 FinanceAnomaly 목록
        """
        seen: dict = {}
        anomalies = []
        for entry in entries:
            key = (entry.reference_id, entry.account, entry.debit, entry.credit)
            if key in seen and entry.reference_id:
                anomalies.append(FinanceAnomaly(
                    type='duplicate_entry',
                    severity='critical',
                    reference=entry.entry_id,
                    detail=f'중복 분개 감지: ref={entry.reference_id} acc={entry.account}',
                ))
            seen[key] = True
        return anomalies

    def detect_revenue_mismatch(
        self,
        revenue_records: List[RevenueRecord],
        batches: List[SettlementBatch],
    ) -> List[FinanceAnomaly]:
        """매출 레코드와 정산 배치 금액 불일치 감지.

        Args:
            revenue_records: 매출 레코드 목록
            batches: 정산 배치 목록

        Returns:
            불일치 채널별 FinanceAnomaly 목록
        """
        anomalies = []
        channels = {b.channel for b in batches}
        for channel in channels:
            total_rev = sum(r.gross_amount for r in revenue_records if r.channel == channel)
            batch_gross = sum(b.gross for b in batches if b.channel == channel)
            if total_rev != batch_gross:
                anomalies.append(FinanceAnomaly(
                    type='revenue_mismatch',
                    severity='high',
                    reference=channel,
                    detail=f'매출 불일치 ({channel}): 레코드={total_rev}, 정산={batch_gross}',
                ))
        return anomalies

    def run_all(self, context: dict) -> List[FinanceAnomaly]:
        """전체 이상 감지 실행.

        Args:
            context: {revenue_records, cost_records, fx_pnls, batches, expected_channels, ...}

        Returns:
            감지된 모든 FinanceAnomaly 목록
        """
        anomalies: List[FinanceAnomaly] = []

        revenue_records = context.get('revenue_records', [])
        cost_records = context.get('cost_records', [])
        fx_pnls = context.get('fx_pnls', [])
        batches = context.get('batches', [])
        expected_channels = context.get('expected_channels', [])

        # 마이너스 마진 감지
        for rev in revenue_records:
            for cost in cost_records:
                if cost.purchase_id.startswith(rev.order_id) or not cost_records:
                    anomaly = self.detect_negative_margin(rev, cost)
                    if anomaly:
                        anomalies.append(anomaly)
                    break

        # FX 손실 감지
        for pnl in fx_pnls:
            anomaly = self.detect_fx_loss(pnl)
            if anomaly:
                anomalies.append(anomaly)

        # 미정산 감지
        if expected_channels:
            anomalies.extend(self.detect_missing_settlement(batches, expected_channels))

        # 중복 분개 감지
        all_entries = self._ledger.all_entries()
        anomalies.extend(self.detect_duplicate_entries(all_entries))

        # 매출 불일치 감지
        if revenue_records and batches:
            anomalies.extend(self.detect_revenue_mismatch(revenue_records, batches))

        logger.info("[이상감지] 총 %d건 이상 감지", len(anomalies))
        return anomalies
