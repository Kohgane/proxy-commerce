"""src/finance_automation/automation_manager.py — Phase 119: 정산/회계 자동화 통합 오케스트레이터."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional

from .anomaly_detector import FinanceAnomalyDetector
from .cost_aggregator import CostAggregator
from .fee_calculator import ChannelFeeCalculator
from .financial_statement_builder import FinancialStatementBuilder
from .fx_pnl_calculator import FxPnLCalculator
from .ledger import Ledger
from .models import (
    CostRecord,
    FinanceAnomaly,
    FinancialStatement,
    FxPnL,
    LedgerEntry,
    PeriodClose,
    RevenueRecord,
    SettlementBatch,
    TaxReport,
)
from .period_closer import PeriodCloser
from .refund_reconciler import RefundReconciler
from .revenue_recognizer import RevenueRecognizer
from .settlement_orchestrator import SettlementOrchestrator
from .tax_reporter import TaxReporter

logger = logging.getLogger(__name__)


class FinanceAutomationManager:
    """정산/회계 자동화 전체 사이클 통합 오케스트레이터.

    매출 인식 → 매입 집계 → 채널 수수료 → FX 손익 →
    일/주/월 마감 → 재무제표 → 세무 리포트 → 이상 감지.
    """

    def __init__(self) -> None:
        self._ledger = Ledger()
        self._recognizer = RevenueRecognizer(self._ledger)
        self._cost_agg = CostAggregator(self._ledger)
        self._fee_calc = ChannelFeeCalculator()
        self._fx_calc = FxPnLCalculator()
        self._settlement = SettlementOrchestrator(self._fee_calc)
        self._refund_rec = RefundReconciler(self._recognizer, self._fee_calc, self._ledger)
        self._anomaly_det = FinanceAnomalyDetector(self._ledger, self._fee_calc)
        self._period_closer = PeriodCloser(self._ledger, self._anomaly_det, self._recognizer)
        self._stmt_builder = FinancialStatementBuilder(self._ledger)
        self._tax_reporter = TaxReporter(self._ledger, self._cost_agg)

        self._revenue_records: List[RevenueRecord] = []
        self._cost_records: List[CostRecord] = []
        self._fx_pnls: List[FxPnL] = []
        self._anomalies: List[FinanceAnomaly] = []

    # ── 이벤트 라우팅 ─────────────────────────────────────────────────────────

    def on_order_event(self, event: dict) -> dict:
        """주문 이벤트 처리.

        지원 이벤트 타입:
          - order_confirmed: 주문 확정 → 매출 인식
          - delivered: 배송 완료 → 채널 수수료 분개
          - cancelled: 주문 취소 → 매출 역인식
          - refunded: 환불 → 환불 대사

        Args:
            event: {type, order_id, channel, gross_amount, net_amount, ...}

        Returns:
            처리 결과 dict
        """
        event_type = event.get('type', '')

        if event_type == 'order_confirmed':
            record = self._recognizer.recognize(event)
            self._revenue_records.append(record)
            return {'status': 'revenue_recognized', 'order_id': event.get('order_id')}

        if event_type == 'delivered':
            channel = event.get('channel', '')
            amount = Decimal(str(event.get('gross_amount', 0)))
            fee = self._fee_calc.calculate_channel_fee(channel, amount)
            return {'status': 'fee_calculated', 'channel_fee': str(fee)}

        if event_type == 'cancelled':
            amount = Decimal(str(event.get('gross_amount', event.get('net_amount', 0))))
            record = self._recognizer.reverse({
                'order_id': event.get('order_id', ''),
                'channel': event.get('channel', ''),
                'refund_amount': str(amount),
                'currency': event.get('currency', 'KRW'),
            })
            return {'status': 'revenue_reversed', 'order_id': event.get('order_id')}

        if event_type == 'refunded':
            result = self._refund_rec.process_refund_event({
                'order_id': event.get('order_id', ''),
                'channel': event.get('channel', ''),
                'refund_amount': event.get('refund_amount', event.get('gross_amount', 0)),
                'currency': event.get('currency', 'KRW'),
                'pg': event.get('pg', ''),
                'reason': event.get('reason', ''),
            })
            return result

        logger.warning("[매니저] 알 수 없는 이벤트 타입: %s", event_type)
        return {'status': 'unknown_event', 'type': event_type}

    # ── 기간 마감 ─────────────────────────────────────────────────────────────

    def run_daily_close(self, date_str: str = '') -> PeriodClose:
        """일 마감 실행.

        Args:
            date_str: 마감 일자 (기본값: 오늘)
        """
        if not date_str:
            date_str = datetime.now(timezone.utc).date().isoformat()
        return self._period_closer.close_daily(date_str)

    def run_weekly_close(self, week_str: str = '') -> PeriodClose:
        """주 마감 실행.

        Args:
            week_str: ISO 주 문자열 (예: '2026-W18', 기본값: 현재 주)
        """
        if not week_str:
            now = datetime.now(timezone.utc)
            week_str = now.strftime('%Y-W%W')
        return self._period_closer.close_weekly(week_str)

    def run_monthly_close(self, month_str: str = '') -> PeriodClose:
        """월 마감 실행.

        Args:
            month_str: YYYY-MM (기본값: 이번 달)
        """
        if not month_str:
            month_str = datetime.now(timezone.utc).strftime('%Y-%m')
        return self._period_closer.close_monthly(month_str)

    # ── 재무제표 ──────────────────────────────────────────────────────────────

    def generate_statement(self, stmt_type: str, period: str) -> FinancialStatement:
        """재무제표 생성.

        Args:
            stmt_type: pnl|bs|cf
            period: YYYY-MM 또는 YYYY
        """
        return self._stmt_builder.build(stmt_type, period)

    # ── 세무 리포트 ───────────────────────────────────────────────────────────

    def generate_tax_report(self, period: str) -> TaxReport:
        """세무 리포트 생성.

        Args:
            period: YYYY-MM
        """
        return self._tax_reporter.generate_report(period)

    # ── 원장 조회 ─────────────────────────────────────────────────────────────

    def get_ledger_entries(
        self,
        account: str = '',
        period_start: str = '',
        period_end: str = '',
    ) -> List[LedgerEntry]:
        """원장 항목 조회.

        Args:
            account: 계정 코드 필터
            period_start: 시작일
            period_end: 종료일
        """
        return self._ledger.query(account, period_start, period_end)

    # ── 정산 조회 ─────────────────────────────────────────────────────────────

    def get_settlements(self, channel: str = '') -> List[SettlementBatch]:
        """정산 배치 목록 조회.

        Args:
            channel: 채널 필터
        """
        return self._settlement.list_batches(channel)

    # ── 이상 감지 조회 ────────────────────────────────────────────────────────

    def get_anomalies(self) -> List[FinanceAnomaly]:
        """감지된 재무 이상 목록 반환."""
        return self._anomalies

    def detect_anomalies(self) -> List[FinanceAnomaly]:
        """이상 감지 실행 및 결과 저장."""
        context = {
            'revenue_records': self._revenue_records,
            'cost_records': self._cost_records,
            'fx_pnls': self._fx_pnls,
            'batches': self._settlement.list_batches(),
        }
        new_anomalies = self._anomaly_det.run_all(context)
        self._anomalies.extend(new_anomalies)
        return new_anomalies

    # ── FX 손익 조회 ──────────────────────────────────────────────────────────

    def get_fx_pnls(self, period: str = '') -> List[FxPnL]:
        """FX 손익 목록 반환.

        Args:
            period: 기간 필터 (미구현 시 전체 반환)
        """
        return self._fx_pnls

    # ── 매입 기록 ─────────────────────────────────────────────────────────────

    def record_cost(self, data: dict) -> CostRecord:
        """매입 원가 기록.

        Args:
            data: 매입 데이터 dict
        """
        record = self._cost_agg.record_purchase(data)
        self._cost_records.append(record)
        return record

    # ── 메트릭 ────────────────────────────────────────────────────────────────

    def metrics(self) -> dict:
        """자동화 현황 메트릭 반환.

        Returns:
            dict with revenue_count, cost_count, settlement_count, anomaly_count 등
        """
        tb = self._ledger.trial_balance()
        revenue_net = tb.get('revenue', {}).get('credit', Decimal('0')) - \
                      tb.get('revenue', {}).get('debit', Decimal('0'))
        cogs_net = tb.get('cogs', {}).get('debit', Decimal('0')) - \
                   tb.get('cogs', {}).get('credit', Decimal('0'))

        return {
            'revenue_records': len(self._revenue_records),
            'cost_records': len(self._cost_records),
            'settlement_batches': len(self._settlement.list_batches()),
            'anomalies': len(self._anomalies),
            'fx_pnls': len(self._fx_pnls),
            'total_revenue_krw': str(revenue_net),
            'total_cogs_krw': str(cogs_net),
            'ledger_entries': len(self._ledger.all_entries()),
        }
