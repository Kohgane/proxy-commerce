"""tests/test_finance_automation.py — Phase 119: 정산/회계 자동화 종합 테스트."""
from __future__ import annotations

import json
import os
import sys
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# FX 네트워크 비활성화
os.environ['FX_DISABLE_NETWORK'] = '1'

from src.finance_automation.models import (
    AccountCode,
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
from src.finance_automation.ledger import Ledger
from src.finance_automation.revenue_recognizer import RevenueRecognizer
from src.finance_automation.cost_aggregator import CostAggregator
from src.finance_automation.fee_calculator import ChannelFeeCalculator
from src.finance_automation.fx_pnl_calculator import FxPnLCalculator
from src.finance_automation.settlement_orchestrator import SettlementOrchestrator
from src.finance_automation.refund_reconciler import RefundReconciler
from src.finance_automation.anomaly_detector import FinanceAnomalyDetector
from src.finance_automation.period_closer import PeriodCloser
from src.finance_automation.financial_statement_builder import FinancialStatementBuilder
from src.finance_automation.tax_reporter import TaxReporter
from src.finance_automation.automation_manager import FinanceAutomationManager
from src.api.finance_automation_api import finance_automation_bp


# ── 공통 픽스처 ──────────────────────────────────────────────────────────────

@pytest.fixture
def ledger():
    return Ledger()


@pytest.fixture
def recognizer(ledger):
    return RevenueRecognizer(ledger)


@pytest.fixture
def cost_agg(ledger):
    return CostAggregator(ledger)


@pytest.fixture
def fee_calc():
    return ChannelFeeCalculator()


@pytest.fixture
def fx_calc():
    return FxPnLCalculator()


@pytest.fixture
def settlement(fee_calc):
    return SettlementOrchestrator(fee_calc)


@pytest.fixture
def refund_rec(recognizer, fee_calc, ledger):
    return RefundReconciler(recognizer, fee_calc, ledger)


@pytest.fixture
def anomaly_det(ledger, fee_calc):
    return FinanceAnomalyDetector(ledger, fee_calc)


@pytest.fixture
def period_closer(ledger, anomaly_det, recognizer):
    return PeriodCloser(ledger, anomaly_det, recognizer)


@pytest.fixture
def stmt_builder(ledger):
    return FinancialStatementBuilder(ledger)


@pytest.fixture
def tax_reporter(ledger, cost_agg):
    return TaxReporter(ledger, cost_agg)


@pytest.fixture
def manager():
    return FinanceAutomationManager()


@pytest.fixture
def app():
    flask_app = Flask(__name__)
    flask_app.config['TESTING'] = True
    flask_app.register_blueprint(finance_automation_bp)
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


def _make_balanced_entries(account_a='revenue', account_b='ar', amount=Decimal('10000')):
    """균형잡힌 두 분개 항목 생성."""
    e1 = LedgerEntry(account=account_b, debit=amount, credit=Decimal('0'), memo='test debit')
    e2 = LedgerEntry(account=account_a, debit=Decimal('0'), credit=amount, memo='test credit')
    return [e1, e2]


# ══════════════════════════════════════════════════════════
# 1. 모델 테스트
# ══════════════════════════════════════════════════════════

class TestModels:
    def test_ledger_entry_defaults(self):
        entry = LedgerEntry()
        assert entry.entry_id
        assert entry.date
        assert entry.debit == Decimal('0')
        assert entry.credit == Decimal('0')
        assert entry.currency == 'KRW'
        assert entry.locked is False

    def test_ledger_entry_custom(self):
        entry = LedgerEntry(
            account='revenue',
            debit=Decimal('5000'),
            currency='USD',
            fx_rate=Decimal('1350'),
        )
        assert entry.account == 'revenue'
        assert entry.debit == Decimal('5000')
        assert entry.currency == 'USD'

    def test_revenue_record_creation(self):
        rec = RevenueRecord(
            order_id='ORD-001',
            channel='coupang',
            gross_amount=Decimal('100000'),
            net_amount=Decimal('89000'),
        )
        assert rec.order_id == 'ORD-001'
        assert rec.channel == 'coupang'
        assert rec.gross_amount == Decimal('100000')
        assert rec.refunded_amount == Decimal('0')
        assert rec.currency == 'KRW'

    def test_revenue_record_with_currency(self):
        rec = RevenueRecord(
            order_id='ORD-002',
            channel='own',
            gross_amount=Decimal('100'),
            net_amount=Decimal('100'),
            currency='USD',
        )
        assert rec.currency == 'USD'

    def test_cost_record_creation(self):
        cost = CostRecord(
            purchase_id='PUR-001',
            source='taobao',
            cogs=Decimal('30000'),
            shipping=Decimal('5000'),
            customs=Decimal('2000'),
        )
        assert cost.purchase_id == 'PUR-001'
        assert cost.cogs == Decimal('30000')
        assert cost.shipping == Decimal('5000')
        assert cost.customs == Decimal('2000')

    def test_cost_record_defaults(self):
        cost = CostRecord(purchase_id='PUR-X', source='test', cogs=Decimal('1000'))
        assert cost.shipping == Decimal('0')
        assert cost.customs == Decimal('0')
        assert cost.fx_rate_at_purchase == Decimal('1')

    def test_settlement_batch_creation(self):
        batch = SettlementBatch(
            channel='coupang',
            period_start='2026-05-01',
            period_end='2026-05-07',
            gross=Decimal('500000'),
            fees=Decimal('55000'),
            net=Decimal('445000'),
        )
        assert batch.batch_id
        assert batch.status == 'draft'
        assert batch.net == Decimal('445000')

    def test_settlement_batch_unique_ids(self):
        b1 = SettlementBatch()
        b2 = SettlementBatch()
        assert b1.batch_id != b2.batch_id

    def test_fx_pnl_creation(self):
        pnl = FxPnL(
            purchase_id='PUR-001',
            fx_at_purchase=Decimal('1300'),
            fx_at_settlement=Decimal('1400'),
            realized_pnl_krw=Decimal('10000'),
        )
        assert pnl.realized_pnl_krw == Decimal('10000')

    def test_fx_pnl_negative(self):
        pnl = FxPnL(
            purchase_id='PUR-002',
            fx_at_purchase=Decimal('1400'),
            fx_at_settlement=Decimal('1300'),
            realized_pnl_krw=Decimal('-10000'),
        )
        assert pnl.realized_pnl_krw < Decimal('0')

    def test_period_close_creation(self):
        close = PeriodClose(period='2026-05-01', type='daily')
        assert close.status == 'open'
        assert close.closed_at is None
        assert close.totals == {}

    def test_financial_statement_creation(self):
        stmt = FinancialStatement(type='pnl', period='2026-05')
        assert stmt.type == 'pnl'
        assert stmt.line_items == []
        assert stmt.totals == {}

    def test_tax_report_creation(self):
        report = TaxReport(period='2026-05')
        assert report.vat_payable == Decimal('0')
        assert report.vat_receivable == Decimal('0')
        assert report.customs_paid == Decimal('0')

    def test_finance_anomaly_creation(self):
        anomaly = FinanceAnomaly(
            type='negative_margin',
            severity='high',
            reference='ORD-001',
            detail='마진 -5000 KRW',
        )
        assert anomaly.type == 'negative_margin'
        assert anomaly.severity == 'high'
        assert anomaly.detected_at

    def test_account_code_enum(self):
        assert AccountCode.REVENUE.value == 'revenue'
        assert AccountCode.COGS.value == 'cogs'
        assert AccountCode.AR.value == 'ar'
        assert AccountCode.AP.value == 'ap'
        assert AccountCode.FX_GAIN.value == 'fx_gain'


# ══════════════════════════════════════════════════════════
# 2. 원장 (Ledger) 테스트
# ══════════════════════════════════════════════════════════

class TestLedger:
    def test_post_balanced_entries(self, ledger):
        entries = _make_balanced_entries(amount=Decimal('10000'))
        ledger.post(entries)
        assert len(ledger.all_entries()) == 2

    def test_post_unbalanced_raises_value_error(self, ledger):
        e1 = LedgerEntry(account='ar', debit=Decimal('10000'), credit=Decimal('0'))
        e2 = LedgerEntry(account='revenue', debit=Decimal('0'), credit=Decimal('9000'))
        with pytest.raises(ValueError, match='대차 불균형'):
            ledger.post([e1, e2])

    def test_post_empty_entries(self, ledger):
        ledger.post([])  # 0 == 0 균형
        assert len(ledger.all_entries()) == 0

    def test_query_by_account(self, ledger):
        entries = _make_balanced_entries('revenue', 'ar', Decimal('5000'))
        ledger.post(entries)
        ar_entries = ledger.query('ar')
        assert len(ar_entries) == 1
        assert ar_entries[0].account == 'ar'

    def test_query_by_period_start(self, ledger):
        e1 = LedgerEntry(date='2026-05-01', account='revenue', debit=Decimal('0'), credit=Decimal('100'))
        e2 = LedgerEntry(date='2026-05-01', account='ar', debit=Decimal('100'), credit=Decimal('0'))
        ledger.post([e1, e2])
        result = ledger.query('revenue', period_start='2026-05-01')
        assert len(result) == 1

    def test_query_by_period_end_excludes_later(self, ledger):
        e1 = LedgerEntry(date='2026-06-01', account='revenue', debit=Decimal('0'), credit=Decimal('100'))
        e2 = LedgerEntry(date='2026-06-01', account='ar', debit=Decimal('100'), credit=Decimal('0'))
        ledger.post([e1, e2])
        result = ledger.query('revenue', period_end='2026-05-31')
        assert len(result) == 0

    def test_query_no_filter_returns_all(self, ledger):
        entries = _make_balanced_entries(amount=Decimal('1000'))
        ledger.post(entries)
        result = ledger.query('')
        assert len(result) == 2

    def test_trial_balance_calculates_net(self, ledger):
        e1 = LedgerEntry(account='revenue', debit=Decimal('0'), credit=Decimal('10000'))
        e2 = LedgerEntry(account='ar', debit=Decimal('10000'), credit=Decimal('0'))
        ledger.post([e1, e2])
        tb = ledger.trial_balance()
        assert tb['revenue']['credit'] == Decimal('10000')
        assert tb['revenue']['net'] == Decimal('-10000')
        assert tb['ar']['debit'] == Decimal('10000')
        assert tb['ar']['net'] == Decimal('10000')

    def test_trial_balance_with_period_filter(self, ledger):
        e1 = LedgerEntry(date='2026-05-01', account='revenue', debit=Decimal('0'), credit=Decimal('5000'))
        e2 = LedgerEntry(date='2026-05-01', account='ar', debit=Decimal('5000'), credit=Decimal('0'))
        e3 = LedgerEntry(date='2026-06-01', account='revenue', debit=Decimal('0'), credit=Decimal('3000'))
        e4 = LedgerEntry(date='2026-06-01', account='ar', debit=Decimal('3000'), credit=Decimal('0'))
        ledger.post([e1, e2])
        ledger.post([e3, e4])
        tb = ledger.trial_balance('2026-05')
        assert tb['revenue']['credit'] == Decimal('5000')

    def test_lock_period(self, ledger):
        entries = _make_balanced_entries(amount=Decimal('1000'))
        for e in entries:
            e.date = '2026-05-01'
        ledger.post(entries)
        count = ledger.lock_period('2026-05-01')
        assert count == 2
        for e in ledger.all_entries():
            assert e.locked is True

    def test_lock_period_does_not_lock_future(self, ledger):
        e1 = LedgerEntry(date='2026-06-01', account='ar', debit=Decimal('100'), credit=Decimal('0'))
        e2 = LedgerEntry(date='2026-06-01', account='revenue', debit=Decimal('0'), credit=Decimal('100'))
        ledger.post([e1, e2])
        count = ledger.lock_period('2026-05-31')
        assert count == 0


# ══════════════════════════════════════════════════════════
# 3. 매출 인식 (RevenueRecognizer) 테스트
# ══════════════════════════════════════════════════════════

class TestRevenueRecognizer:
    def test_recognize_creates_record(self, recognizer):
        order = {
            'order_id': 'ORD-001',
            'channel': 'coupang',
            'gross_amount': '100000',
            'net_amount': '100000',
        }
        record = recognizer.recognize(order)
        assert record.order_id == 'ORD-001'
        assert record.channel == 'coupang'
        assert record.gross_amount == Decimal('100000')

    def test_recognize_posts_ar_and_revenue_entries(self, recognizer, ledger):
        order = {
            'order_id': 'ORD-002',
            'channel': 'naver',
            'gross_amount': '50000',
            'net_amount': '50000',
        }
        recognizer.recognize(order)
        ar_entries = ledger.query('ar')
        rev_entries = ledger.query('revenue')
        assert len(ar_entries) >= 1
        assert len(rev_entries) >= 1

    def test_recognize_ar_debit_equals_revenue_credit(self, recognizer, ledger):
        order = {
            'order_id': 'ORD-003',
            'channel': 'own',
            'gross_amount': '75000',
            'net_amount': '75000',
        }
        recognizer.recognize(order)
        ar_entries = ledger.query('ar')
        rev_entries = ledger.query('revenue')
        ar_debit = sum(e.debit for e in ar_entries)
        rev_credit = sum(e.credit for e in rev_entries)
        assert ar_debit == rev_credit

    def test_reverse_creates_refund_record(self, recognizer):
        refund = {
            'order_id': 'ORD-001',
            'channel': 'coupang',
            'refund_amount': '50000',
            'currency': 'KRW',
        }
        record = recognizer.reverse(refund)
        assert record.refunded_amount == Decimal('50000')
        assert record.gross_amount == Decimal('-50000')

    def test_reverse_posts_refund_and_ar_entries(self, recognizer, ledger):
        refund = {
            'order_id': 'ORD-005',
            'channel': 'naver',
            'refund_amount': '30000',
            'currency': 'KRW',
        }
        recognizer.reverse(refund)
        refund_entries = ledger.query('refund')
        assert len(refund_entries) >= 1

    def test_recognize_uses_net_amount_for_entries(self, recognizer, ledger):
        order = {
            'order_id': 'ORD-006',
            'channel': 'coupang',
            'gross_amount': '100000',
            'net_amount': '89000',
        }
        recognizer.recognize(order)
        rev_entries = ledger.query('revenue')
        credit_total = sum(e.credit for e in rev_entries)
        assert credit_total == Decimal('89000')


# ══════════════════════════════════════════════════════════
# 4. 매입 집계 (CostAggregator) 테스트
# ══════════════════════════════════════════════════════════

class TestCostAggregator:
    def test_record_purchase_creates_cost_record(self, cost_agg):
        data = {
            'purchase_id': 'PUR-001',
            'source': 'taobao',
            'cogs': '30000',
            'shipping': '5000',
            'customs': '2000',
        }
        record = cost_agg.record_purchase(data)
        assert record.purchase_id == 'PUR-001'
        assert record.cogs == Decimal('30000')
        assert record.shipping == Decimal('5000')
        assert record.customs == Decimal('2000')

    def test_record_purchase_posts_cogs_entry(self, cost_agg, ledger):
        cost_agg.record_purchase({
            'purchase_id': 'PUR-002',
            'source': 'alibaba',
            'cogs': '20000',
        })
        entries = ledger.query('cogs')
        assert len(entries) >= 1

    def test_record_purchase_posts_ap_entry(self, cost_agg, ledger):
        cost_agg.record_purchase({
            'purchase_id': 'PUR-003',
            'source': 'alibaba',
            'cogs': '20000',
        })
        entries = ledger.query('ap')
        assert len(entries) >= 1

    def test_record_purchase_with_shipping_and_customs(self, cost_agg, ledger):
        cost_agg.record_purchase({
            'purchase_id': 'PUR-004',
            'source': 'test',
            'cogs': '10000',
            'shipping': '3000',
            'customs': '1000',
        })
        shipping_entries = ledger.query('shipping_out')
        customs_entries = ledger.query('customs_duty')
        assert len(shipping_entries) >= 1
        assert len(customs_entries) >= 1

    def test_get_costs_by_period(self, cost_agg, ledger):
        cost_agg.record_purchase({
            'purchase_id': 'PUR-005',
            'source': 'test',
            'cogs': '5000',
        })
        records = cost_agg.get_costs_by_period('2020-01-01', '2030-12-31')
        assert any(r.purchase_id == 'PUR-005' for r in records)

    def test_get_all_records(self, cost_agg):
        cost_agg.record_purchase({'purchase_id': 'PUR-A', 'source': 'x', 'cogs': '1000'})
        cost_agg.record_purchase({'purchase_id': 'PUR-B', 'source': 'y', 'cogs': '2000'})
        records = cost_agg.get_all_records()
        assert len(records) == 2


# ══════════════════════════════════════════════════════════
# 5. 채널 수수료 계산기 (ChannelFeeCalculator) 테스트
# ══════════════════════════════════════════════════════════

class TestChannelFeeCalculator:
    def test_coupang_fee_rate(self, fee_calc):
        rate = fee_calc.get_fee_rate('coupang')
        assert rate == Decimal('0.11')

    def test_naver_fee_rate(self, fee_calc):
        rate = fee_calc.get_fee_rate('naver')
        assert rate == Decimal('0.0585')

    def test_own_fee_rate_zero(self, fee_calc):
        rate = fee_calc.get_fee_rate('own')
        assert rate == Decimal('0')

    def test_vendor_fee_rate(self, fee_calc):
        rate = fee_calc.get_fee_rate('vendor')
        assert rate == Decimal('0.08')

    def test_unknown_channel_defaults_to_8_percent(self, fee_calc):
        rate = fee_calc.get_fee_rate('unknown_channel')
        assert rate == Decimal('0.08')

    def test_calculate_channel_fee_coupang(self, fee_calc):
        fee = fee_calc.calculate_channel_fee('coupang', Decimal('100000'))
        assert fee == Decimal('11000')

    def test_calculate_channel_fee_naver(self, fee_calc):
        fee = fee_calc.calculate_channel_fee('naver', Decimal('100000'))
        assert fee == Decimal('5850')  # 5.85% quantized

    def test_calculate_channel_fee_own_zero(self, fee_calc):
        fee = fee_calc.calculate_channel_fee('own', Decimal('100000'))
        assert fee == Decimal('0')

    def test_pg_fee_toss(self, fee_calc):
        fee = fee_calc.calculate_pg_fee('toss', Decimal('100000'))
        assert fee == Decimal('1400')

    def test_pg_fee_stripe(self, fee_calc):
        fee = fee_calc.calculate_pg_fee('stripe', Decimal('100000'))
        assert fee == Decimal('2900')

    def test_pg_fee_paypal(self, fee_calc):
        fee = fee_calc.calculate_pg_fee('paypal', Decimal('100000'))
        assert fee == Decimal('3400')

    def test_pg_fee_unknown_zero(self, fee_calc):
        fee = fee_calc.calculate_pg_fee('unknown_pg', Decimal('100000'))
        assert fee == Decimal('0')

    def test_channel_fee_case_insensitive(self, fee_calc):
        rate = fee_calc.get_fee_rate('COUPANG')
        assert rate == Decimal('0.11')


# ══════════════════════════════════════════════════════════
# 6. FX 손익 계산기 (FxPnLCalculator) 테스트
# ══════════════════════════════════════════════════════════

class TestFxPnLCalculator:
    def test_calculate_positive_pnl(self, fx_calc):
        pnl = fx_calc.calculate('PUR-001', Decimal('100'), 'USD', Decimal('1300'))
        # 현재 환율(기본값 1350) > 매입 환율(1300) → 양의 손익
        assert pnl.realized_pnl_krw == (pnl.fx_at_settlement - Decimal('1300')) * Decimal('100')
        assert pnl.purchase_id == 'PUR-001'

    def test_calculate_negative_pnl(self, fx_calc):
        pnl = fx_calc.calculate('PUR-002', Decimal('100'), 'USD', Decimal('1400'))
        # 기본 환율(1350) < 매입 환율(1400) → 음의 손익
        assert pnl.realized_pnl_krw < Decimal('0')

    def test_calculate_uses_default_usd_rate(self, fx_calc):
        pnl = fx_calc.calculate('PUR-003', Decimal('1'), 'USD', Decimal('1350'))
        assert pnl.fx_at_settlement == Decimal('1350')
        assert pnl.realized_pnl_krw == Decimal('0')

    def test_calculate_eur_default_rate(self, fx_calc):
        pnl = fx_calc.calculate('PUR-004', Decimal('1'), 'EUR', Decimal('1480'))
        assert pnl.fx_at_settlement == Decimal('1480')

    def test_calculate_unknown_currency_fallback(self, fx_calc):
        pnl = fx_calc.calculate('PUR-005', Decimal('1'), 'XYZ', Decimal('1000'))
        assert pnl.fx_at_settlement == Decimal('1350')  # fallback

    def test_get_current_rate_krw_returns_one(self, fx_calc):
        rate = fx_calc._get_current_rate('KRW')
        assert rate == Decimal('1')


# ══════════════════════════════════════════════════════════
# 7. 정산 오케스트레이터 (SettlementOrchestrator) 테스트
# ══════════════════════════════════════════════════════════

class TestSettlementOrchestrator:
    def _make_revenue_records(self, channel='coupang', count=3, amount=100000):
        return [
            RevenueRecord(
                order_id=f'ORD-{i:03d}',
                channel=channel,
                gross_amount=Decimal(str(amount)),
                net_amount=Decimal(str(amount)),
            )
            for i in range(count)
        ]

    def test_create_batch(self, settlement):
        records = self._make_revenue_records('coupang', 3, 100000)
        batch = settlement.create_batch('coupang', '2026-05-01', '2026-05-07', records)
        assert batch.channel == 'coupang'
        assert batch.gross == Decimal('300000')
        assert batch.fees == Decimal('33000')  # 11%
        assert batch.net == Decimal('267000')
        assert batch.status == 'draft'

    def test_create_batch_naver(self, settlement):
        records = self._make_revenue_records('naver', 2, 100000)
        batch = settlement.create_batch('naver', '2026-05-01', '2026-05-01', records)
        assert batch.channel == 'naver'
        assert batch.gross == Decimal('200000')

    def test_finalize_batch(self, settlement):
        records = self._make_revenue_records('coupang', 1)
        batch = settlement.create_batch('coupang', '2026-05-01', '2026-05-07', records)
        finalized = settlement.finalize_batch(batch.batch_id)
        assert finalized.status == 'finalized'

    def test_finalize_nonexistent_raises(self, settlement):
        with pytest.raises(KeyError):
            settlement.finalize_batch('NONEXISTENT')

    def test_get_batch(self, settlement):
        records = self._make_revenue_records('naver', 1)
        batch = settlement.create_batch('naver', '2026-05-01', '2026-05-01', records)
        found = settlement.get_batch(batch.batch_id)
        assert found is not None
        assert found.batch_id == batch.batch_id

    def test_get_batch_not_found(self, settlement):
        assert settlement.get_batch('MISSING') is None

    def test_list_batches_all(self, settlement):
        records_c = self._make_revenue_records('coupang', 1)
        records_n = self._make_revenue_records('naver', 1)
        settlement.create_batch('coupang', '2026-05-01', '2026-05-07', records_c)
        settlement.create_batch('naver', '2026-05-01', '2026-05-01', records_n)
        batches = settlement.list_batches()
        assert len(batches) == 2

    def test_list_batches_by_channel(self, settlement):
        records_c = self._make_revenue_records('coupang', 1)
        records_n = self._make_revenue_records('naver', 1)
        settlement.create_batch('coupang', '2026-05-01', '2026-05-07', records_c)
        settlement.create_batch('naver', '2026-05-01', '2026-05-01', records_n)
        coupang_batches = settlement.list_batches('coupang')
        assert all(b.channel == 'coupang' for b in coupang_batches)
        assert len(coupang_batches) == 1

    def test_get_cycle(self, settlement):
        assert settlement.get_cycle('coupang') == 'weekly'
        assert settlement.get_cycle('naver') == 'daily'
        assert settlement.get_cycle('vendor') == 'monthly'
        assert settlement.get_cycle('own') == 'monthly'


# ══════════════════════════════════════════════════════════
# 8. 환불 대사 (RefundReconciler) 테스트
# ══════════════════════════════════════════════════════════

class TestRefundReconciler:
    def test_process_refund_event_returns_summary(self, refund_rec):
        event = {
            'order_id': 'ORD-001',
            'channel': 'coupang',
            'refund_amount': '50000',
            'currency': 'KRW',
            'pg': 'toss',
            'reason': '변심',
        }
        result = refund_rec.process_refund_event(event)
        assert result['order_id'] == 'ORD-001'
        assert result['status'] == 'reconciled'
        assert result['refund_amount'] == '50000'

    def test_process_refund_event_reverses_revenue(self, refund_rec, ledger):
        event = {
            'order_id': 'ORD-002',
            'channel': 'naver',
            'refund_amount': '30000',
            'currency': 'KRW',
        }
        refund_rec.process_refund_event(event)
        refund_entries = ledger.query('refund')
        assert len(refund_entries) >= 1

    def test_process_refund_event_channel_fee_reversal(self, refund_rec):
        event = {
            'order_id': 'ORD-003',
            'channel': 'coupang',
            'refund_amount': '100000',
            'currency': 'KRW',
        }
        result = refund_rec.process_refund_event(event)
        assert result['fee_reversal'] == '11000'

    def test_process_refund_event_pg_fee_reversal(self, refund_rec):
        event = {
            'order_id': 'ORD-004',
            'channel': 'own',
            'refund_amount': '100000',
            'currency': 'KRW',
            'pg': 'toss',
        }
        result = refund_rec.process_refund_event(event)
        assert result['pg_fee_reversal'] == '1400'

    def test_reconcile_partial_refund(self, refund_rec):
        result = refund_rec.reconcile_partial_refund('ORD-005', Decimal('25000'), 'naver')
        assert result['order_id'] == 'ORD-005'
        assert result['refund_amount'] == '25000'
        assert result['reason'] == 'partial_refund'

    def test_process_refund_no_pg_fee_without_pg(self, refund_rec):
        event = {
            'order_id': 'ORD-006',
            'channel': 'own',
            'refund_amount': '10000',
            'currency': 'KRW',
            'pg': '',
        }
        result = refund_rec.process_refund_event(event)
        assert result['pg_fee_reversal'] == '0'


# ══════════════════════════════════════════════════════════
# 9. 기간 마감 (PeriodCloser) 테스트
# ══════════════════════════════════════════════════════════

class TestPeriodCloser:
    def test_close_daily(self, period_closer):
        close = period_closer.close_daily('2026-05-01')
        assert close.type == 'daily'
        assert close.period == '2026-05-01'
        assert close.status == 'closed'
        assert close.closed_at is not None

    def test_close_daily_idempotent(self, period_closer):
        close1 = period_closer.close_daily('2026-05-02')
        close2 = period_closer.close_daily('2026-05-02')
        assert close1.closed_at == close2.closed_at

    def test_close_weekly(self, period_closer):
        close = period_closer.close_weekly('2026-W18')
        assert close.type == 'weekly'
        assert close.period == '2026-W18'
        assert close.status == 'closed'

    def test_close_weekly_idempotent(self, period_closer):
        close1 = period_closer.close_weekly('2026-W19')
        close2 = period_closer.close_weekly('2026-W19')
        assert close1.closed_at == close2.closed_at

    def test_close_monthly(self, period_closer):
        close = period_closer.close_monthly('2026-05')
        assert close.type == 'monthly'
        assert close.period == '2026-05'
        assert close.status == 'closed'

    def test_close_monthly_idempotent(self, period_closer):
        close1 = period_closer.close_monthly('2026-04')
        close2 = period_closer.close_monthly('2026-04')
        assert close1.closed_at == close2.closed_at

    def test_get_close_returns_record(self, period_closer):
        period_closer.close_daily('2026-05-03')
        close = period_closer.get_close('daily', '2026-05-03')
        assert close is not None
        assert close.period == '2026-05-03'

    def test_get_close_not_found(self, period_closer):
        result = period_closer.get_close('daily', '2099-01-01')
        assert result is None

    def test_close_daily_locks_ledger(self, ledger, anomaly_det, recognizer):
        e1 = LedgerEntry(date='2026-05-01', account='ar', debit=Decimal('100'), credit=Decimal('0'))
        e2 = LedgerEntry(date='2026-05-01', account='revenue', debit=Decimal('0'), credit=Decimal('100'))
        ledger.post([e1, e2])
        closer = PeriodCloser(ledger, anomaly_det, recognizer)
        closer.close_daily('2026-05-01')
        assert all(e.locked for e in ledger.all_entries())


# ══════════════════════════════════════════════════════════
# 10. 재무제표 빌더 (FinancialStatementBuilder) 테스트
# ══════════════════════════════════════════════════════════

class TestFinancialStatementBuilder:
    def _populate_ledger(self, ledger, revenue=100000, cogs=60000):
        e1 = LedgerEntry(date='2026-05-01', account='ar', debit=Decimal(str(revenue)), credit=Decimal('0'))
        e2 = LedgerEntry(date='2026-05-01', account='revenue', debit=Decimal('0'), credit=Decimal(str(revenue)))
        ledger.post([e1, e2])
        e3 = LedgerEntry(date='2026-05-01', account='cogs', debit=Decimal(str(cogs)), credit=Decimal('0'))
        e4 = LedgerEntry(date='2026-05-01', account='ap', debit=Decimal('0'), credit=Decimal(str(cogs)))
        ledger.post([e3, e4])

    def test_build_pnl(self, stmt_builder, ledger):
        self._populate_ledger(ledger)
        stmt = stmt_builder.build_pnl('2026-05')
        assert stmt.type == 'pnl'
        assert stmt.period == '2026-05'
        assert len(stmt.line_items) > 0
        assert 'revenue' in stmt.totals

    def test_build_pnl_revenue_line_item(self, stmt_builder, ledger):
        self._populate_ledger(ledger, revenue=200000)
        stmt = stmt_builder.build_pnl('2026-05')
        revenue_item = next(i for i in stmt.line_items if i['name'] == '매출')
        assert revenue_item['amount'] == '200000'

    def test_build_pnl_net_income(self, stmt_builder, ledger):
        self._populate_ledger(ledger, revenue=100000, cogs=60000)
        stmt = stmt_builder.build_pnl('2026-05')
        net_item = next(i for i in stmt.line_items if i['name'] == '순이익')
        assert net_item['amount'] == '40000'

    def test_build_bs(self, stmt_builder, ledger):
        self._populate_ledger(ledger)
        stmt = stmt_builder.build_bs('2026-05')
        assert stmt.type == 'bs'
        names = [i['name'] for i in stmt.line_items]
        assert '매출채권(AR)' in names
        assert '매입채무(AP)' in names

    def test_build_cf(self, stmt_builder, ledger):
        self._populate_ledger(ledger)
        stmt = stmt_builder.build_cf('2026-05')
        assert stmt.type == 'cf'
        assert 'operating_cf' in stmt.totals

    def test_build_dispatches_correctly(self, stmt_builder, ledger):
        self._populate_ledger(ledger)
        assert stmt_builder.build('pnl', '2026-05').type == 'pnl'
        assert stmt_builder.build('bs', '2026-05').type == 'bs'
        assert stmt_builder.build('cf', '2026-05').type == 'cf'

    def test_build_unknown_type_raises(self, stmt_builder):
        with pytest.raises(ValueError):
            stmt_builder.build('unknown', '2026-05')

    def test_build_pnl_empty_ledger(self, stmt_builder):
        stmt = stmt_builder.build_pnl('2026-05')
        assert stmt.totals['revenue'] == '0'
        assert stmt.totals['net_income'] == '0'


# ══════════════════════════════════════════════════════════
# 11. 세무 리포트 (TaxReporter) 테스트
# ══════════════════════════════════════════════════════════

class TestTaxReporter:
    def _populate(self, ledger, cost_agg, revenue=1000000, cogs=600000):
        e1 = LedgerEntry(date='2026-05-01', account='ar', debit=Decimal(str(revenue)), credit=Decimal('0'))
        e2 = LedgerEntry(date='2026-05-01', account='revenue', debit=Decimal('0'), credit=Decimal(str(revenue)))
        ledger.post([e1, e2])
        cost_agg.record_purchase({
            'purchase_id': 'PUR-TAX-001',
            'source': 'test',
            'cogs': str(cogs),
            'customs': '50000',
        })

    def test_generate_report(self, tax_reporter, ledger, cost_agg):
        self._populate(ledger, cost_agg)
        report = tax_reporter.generate_report('2026-05')
        assert report.period == '2026-05'
        assert report.vat_payable == Decimal('100000')  # 1000000 * 10%
        assert report.vat_receivable == Decimal('60000')  # 600000 * 10%
        assert report.customs_paid == Decimal('50000')
        assert report.total_taxable == Decimal('1000000')

    def test_generate_report_empty_period(self, tax_reporter):
        report = tax_reporter.generate_report('2099-01')
        assert report.vat_payable == Decimal('0')

    def test_export_json(self, tax_reporter, ledger, cost_agg):
        self._populate(ledger, cost_agg)
        report = tax_reporter.generate_report('2026-05')
        json_str = tax_reporter.export_json(report)
        data = json.loads(json_str)
        assert data['period'] == '2026-05'
        assert 'vat_payable' in data
        assert 'customs_paid' in data

    def test_export_csv(self, tax_reporter, ledger, cost_agg):
        self._populate(ledger, cost_agg)
        report = tax_reporter.generate_report('2026-05')
        csv_str = tax_reporter.export_csv(report)
        assert '항목' in csv_str
        assert '2026-05' in csv_str
        assert '100000' in csv_str

    def test_export_json_is_valid_json(self, tax_reporter):
        report = TaxReport(period='2026-06')
        json_str = tax_reporter.export_json(report)
        data = json.loads(json_str)
        assert isinstance(data, dict)

    def test_export_csv_has_all_fields(self, tax_reporter):
        report = TaxReport(
            period='2026-06',
            vat_payable=Decimal('5000'),
            vat_receivable=Decimal('3000'),
            customs_paid=Decimal('1000'),
            total_taxable=Decimal('50000'),
        )
        csv_str = tax_reporter.export_csv(report)
        assert 'VAT 납부세액' in csv_str
        assert 'VAT 매입세액 공제' in csv_str
        assert '관세 납부액' in csv_str


# ══════════════════════════════════════════════════════════
# 12. 이상 감지 (FinanceAnomalyDetector) 테스트
# ══════════════════════════════════════════════════════════

class TestFinanceAnomalyDetector:
    def _make_revenue(self, order_id='ORD-001', channel='coupang', amount=100000):
        return RevenueRecord(
            order_id=order_id,
            channel=channel,
            gross_amount=Decimal(str(amount)),
            net_amount=Decimal(str(amount)),
        )

    def _make_cost(self, purchase_id='PUR-001', cogs=60000, shipping=0, customs=0):
        return CostRecord(
            purchase_id=purchase_id,
            source='test',
            cogs=Decimal(str(cogs)),
            shipping=Decimal(str(shipping)),
            customs=Decimal(str(customs)),
        )

    def test_detect_negative_margin_triggers(self, anomaly_det):
        rev = self._make_revenue(amount=50000)
        cost = self._make_cost(cogs=60000)
        anomaly = anomaly_det.detect_negative_margin(rev, cost)
        assert anomaly is not None
        assert anomaly.type == 'negative_margin'
        assert anomaly.severity == 'high'

    def test_detect_negative_margin_no_anomaly(self, anomaly_det):
        rev = self._make_revenue(amount=100000)
        cost = self._make_cost(cogs=60000)
        anomaly = anomaly_det.detect_negative_margin(rev, cost)
        assert anomaly is None

    def test_detect_negative_margin_boundary(self, anomaly_det):
        rev = self._make_revenue(amount=60000)
        cost = self._make_cost(cogs=60000)
        anomaly = anomaly_det.detect_negative_margin(rev, cost)
        assert anomaly is None  # margin == 0 is not negative

    def test_detect_fx_loss_triggers(self, anomaly_det):
        pnl = FxPnL('PUR-001', Decimal('1400'), Decimal('1300'), realized_pnl_krw=Decimal('-100000'))
        anomaly = anomaly_det.detect_fx_loss(pnl, threshold_krw=Decimal('50000'))
        assert anomaly is not None
        assert anomaly.type == 'fx_loss_exceeded'
        assert anomaly.severity == 'medium'

    def test_detect_fx_loss_no_anomaly(self, anomaly_det):
        pnl = FxPnL('PUR-002', Decimal('1300'), Decimal('1400'), realized_pnl_krw=Decimal('10000'))
        anomaly = anomaly_det.detect_fx_loss(pnl)
        assert anomaly is None

    def test_detect_fx_loss_below_threshold(self, anomaly_det):
        pnl = FxPnL('PUR-003', Decimal('1350'), Decimal('1340'), realized_pnl_krw=Decimal('-1000'))
        anomaly = anomaly_det.detect_fx_loss(pnl, threshold_krw=Decimal('50000'))
        assert anomaly is None

    def test_detect_missing_settlement(self, anomaly_det):
        batches = [
            SettlementBatch(channel='coupang', status='finalized'),
        ]
        anomalies = anomaly_det.detect_missing_settlement(batches, ['coupang', 'naver'])
        assert len(anomalies) == 1
        assert anomalies[0].reference == 'naver'

    def test_detect_missing_settlement_all_present(self, anomaly_det):
        batches = [
            SettlementBatch(channel='coupang', status='finalized'),
            SettlementBatch(channel='naver', status='finalized'),
        ]
        anomalies = anomaly_det.detect_missing_settlement(batches, ['coupang', 'naver'])
        assert len(anomalies) == 0

    def test_detect_duplicate_entries(self, anomaly_det):
        entry = LedgerEntry(
            account='revenue',
            debit=Decimal('0'),
            credit=Decimal('10000'),
            reference_id='REF-001',
        )
        duplicate = LedgerEntry(
            account='revenue',
            debit=Decimal('0'),
            credit=Decimal('10000'),
            reference_id='REF-001',
        )
        anomalies = anomaly_det.detect_duplicate_entries([entry, duplicate])
        assert len(anomalies) == 1
        assert anomalies[0].type == 'duplicate_entry'
        assert anomalies[0].severity == 'critical'

    def test_detect_duplicate_entries_none(self, anomaly_det):
        e1 = LedgerEntry(account='revenue', debit=Decimal('0'), credit=Decimal('10000'), reference_id='A')
        e2 = LedgerEntry(account='revenue', debit=Decimal('0'), credit=Decimal('20000'), reference_id='B')
        anomalies = anomaly_det.detect_duplicate_entries([e1, e2])
        assert len(anomalies) == 0

    def test_detect_revenue_mismatch(self, anomaly_det):
        records = [self._make_revenue('ORD-001', 'coupang', 100000)]
        batches = [SettlementBatch(channel='coupang', gross=Decimal('90000'))]
        anomalies = anomaly_det.detect_revenue_mismatch(records, batches)
        assert len(anomalies) == 1
        assert anomalies[0].type == 'revenue_mismatch'

    def test_detect_revenue_mismatch_matching(self, anomaly_det):
        records = [self._make_revenue('ORD-001', 'coupang', 100000)]
        batches = [SettlementBatch(channel='coupang', gross=Decimal('100000'))]
        anomalies = anomaly_det.detect_revenue_mismatch(records, batches)
        assert len(anomalies) == 0

    def test_run_all_returns_list(self, anomaly_det):
        result = anomaly_det.run_all({})
        assert isinstance(result, list)


# ══════════════════════════════════════════════════════════
# 13. 통합 매니저 (FinanceAutomationManager) 테스트
# ══════════════════════════════════════════════════════════

class TestFinanceAutomationManager:
    def test_on_order_event_confirmed(self, manager):
        event = {
            'type': 'order_confirmed',
            'order_id': 'ORD-100',
            'channel': 'coupang',
            'gross_amount': '100000',
            'net_amount': '100000',
        }
        result = manager.on_order_event(event)
        assert result['status'] == 'revenue_recognized'
        assert result['order_id'] == 'ORD-100'

    def test_on_order_event_delivered(self, manager):
        event = {
            'type': 'delivered',
            'order_id': 'ORD-101',
            'channel': 'coupang',
            'gross_amount': '100000',
        }
        result = manager.on_order_event(event)
        assert result['status'] == 'fee_calculated'
        assert result['channel_fee'] == '11000'

    def test_on_order_event_cancelled(self, manager):
        event = {
            'type': 'cancelled',
            'order_id': 'ORD-102',
            'channel': 'naver',
            'gross_amount': '50000',
        }
        result = manager.on_order_event(event)
        assert result['status'] == 'revenue_reversed'

    def test_on_order_event_refunded(self, manager):
        event = {
            'type': 'refunded',
            'order_id': 'ORD-103',
            'channel': 'coupang',
            'refund_amount': '30000',
            'currency': 'KRW',
        }
        result = manager.on_order_event(event)
        assert result['status'] == 'reconciled'

    def test_on_order_event_unknown_type(self, manager):
        result = manager.on_order_event({'type': 'unknown_event'})
        assert result['status'] == 'unknown_event'

    def test_run_daily_close(self, manager):
        close = manager.run_daily_close('2026-05-01')
        assert close.type == 'daily'
        assert close.status == 'closed'

    def test_run_weekly_close(self, manager):
        close = manager.run_weekly_close('2026-W18')
        assert close.type == 'weekly'
        assert close.status == 'closed'

    def test_run_monthly_close(self, manager):
        close = manager.run_monthly_close('2026-05')
        assert close.type == 'monthly'
        assert close.status == 'closed'

    def test_generate_statement_pnl(self, manager):
        stmt = manager.generate_statement('pnl', '2026-05')
        assert stmt.type == 'pnl'

    def test_generate_statement_bs(self, manager):
        stmt = manager.generate_statement('bs', '2026-05')
        assert stmt.type == 'bs'

    def test_generate_statement_cf(self, manager):
        stmt = manager.generate_statement('cf', '2026-05')
        assert stmt.type == 'cf'

    def test_generate_tax_report(self, manager):
        report = manager.generate_tax_report('2026-05')
        assert report.period == '2026-05'

    def test_get_ledger_entries_empty(self, manager):
        entries = manager.get_ledger_entries()
        assert isinstance(entries, list)

    def test_get_settlements_empty(self, manager):
        batches = manager.get_settlements()
        assert isinstance(batches, list)

    def test_get_anomalies_empty(self, manager):
        anomalies = manager.get_anomalies()
        assert isinstance(anomalies, list)

    def test_get_fx_pnls_empty(self, manager):
        pnls = manager.get_fx_pnls()
        assert isinstance(pnls, list)

    def test_record_cost(self, manager):
        record = manager.record_cost({
            'purchase_id': 'PUR-MGR-001',
            'source': 'test',
            'cogs': '10000',
        })
        assert record.purchase_id == 'PUR-MGR-001'

    def test_metrics_returns_dict(self, manager):
        m = manager.metrics()
        assert 'revenue_records' in m
        assert 'cost_records' in m
        assert 'ledger_entries' in m

    def test_metrics_after_order_event(self, manager):
        manager.on_order_event({
            'type': 'order_confirmed',
            'order_id': 'ORD-M01',
            'channel': 'coupang',
            'gross_amount': '100000',
            'net_amount': '100000',
        })
        m = manager.metrics()
        assert m['revenue_records'] == 1
        assert int(m['total_revenue_krw']) == 100000

    def test_run_daily_close_default_date(self, manager):
        close = manager.run_daily_close()
        assert close.type == 'daily'
        assert close.status == 'closed'

    def test_detect_anomalies_method(self, manager):
        anomalies = manager.detect_anomalies()
        assert isinstance(anomalies, list)


# ══════════════════════════════════════════════════════════
# 14. API 엔드포인트 테스트
# ══════════════════════════════════════════════════════════

class TestFinanceAutomationAPI:
    def setup_method(self):
        """각 테스트 전 싱글톤 매니저 초기화."""
        import src.api.finance_automation_api as api_module
        api_module._manager = None

    def test_recognize_revenue_201(self, client):
        resp = client.post('/api/v1/finance/revenue/recognize', json={
            'order_id': 'ORD-API-001',
            'channel': 'coupang',
            'gross_amount': '100000',
            'net_amount': '100000',
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['order_id'] == 'ORD-API-001'

    def test_recognize_revenue_400_missing_order_id(self, client):
        resp = client.post('/api/v1/finance/revenue/recognize', json={
            'channel': 'coupang',
            'gross_amount': '100000',
        })
        assert resp.status_code == 400

    def test_record_cost_201(self, client):
        resp = client.post('/api/v1/finance/cost/record', json={
            'purchase_id': 'PUR-API-001',
            'source': 'test',
            'cogs': '30000',
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['purchase_id'] == 'PUR-API-001'

    def test_record_cost_400_missing_purchase_id(self, client):
        resp = client.post('/api/v1/finance/cost/record', json={
            'source': 'test',
            'cogs': '30000',
        })
        assert resp.status_code == 400

    def test_get_ledger_200(self, client):
        resp = client.get('/api/v1/finance/ledger')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'entries' in data

    def test_get_ledger_with_account_filter(self, client):
        client.post('/api/v1/finance/revenue/recognize', json={
            'order_id': 'ORD-LEDGER',
            'channel': 'naver',
            'gross_amount': '50000',
            'net_amount': '50000',
        })
        resp = client.get('/api/v1/finance/ledger?account=revenue')
        assert resp.status_code == 200

    def test_get_settlements_200(self, client):
        resp = client.get('/api/v1/finance/settlements')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'batches' in data

    def test_finalize_settlement_404(self, client):
        resp = client.post('/api/v1/finance/settlements/NONEXISTENT/finalize')
        assert resp.status_code == 404

    def test_close_period_daily_200(self, client):
        resp = client.post('/api/v1/finance/period/close', json={
            'type': 'daily',
            'date': '2026-05-01',
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['type'] == 'daily'
        assert data['status'] == 'closed'

    def test_close_period_weekly_200(self, client):
        resp = client.post('/api/v1/finance/period/close', json={
            'type': 'weekly',
            'date': '2026-W18',
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['type'] == 'weekly'

    def test_close_period_monthly_200(self, client):
        resp = client.post('/api/v1/finance/period/close', json={
            'type': 'monthly',
            'date': '2026-05',
        })
        assert resp.status_code == 200

    def test_close_period_400_missing_date(self, client):
        resp = client.post('/api/v1/finance/period/close', json={'type': 'daily'})
        assert resp.status_code == 400

    def test_close_period_400_invalid_type(self, client):
        resp = client.post('/api/v1/finance/period/close', json={
            'type': 'yearly',
            'date': '2026',
        })
        assert resp.status_code == 400

    def test_get_period_close_404(self, client):
        resp = client.get('/api/v1/finance/period/daily/9999-99-99')
        assert resp.status_code == 404

    def test_get_period_close_200_after_close(self, client):
        client.post('/api/v1/finance/period/close', json={
            'type': 'daily',
            'date': '2026-05-05',
        })
        resp = client.get('/api/v1/finance/period/daily/2026-05-05')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['period'] == '2026-05-05'

    def test_get_statements_pnl_200(self, client):
        resp = client.get('/api/v1/finance/statements?type=pnl&period=2026-05')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['type'] == 'pnl'

    def test_get_statements_400_missing_period(self, client):
        resp = client.get('/api/v1/finance/statements?type=pnl')
        assert resp.status_code == 400

    def test_get_statements_bs_200(self, client):
        resp = client.get('/api/v1/finance/statements?type=bs&period=2026-05')
        assert resp.status_code == 200

    def test_get_statements_cf_200(self, client):
        resp = client.get('/api/v1/finance/statements?type=cf&period=2026-05')
        assert resp.status_code == 200

    def test_get_tax_report_200(self, client):
        resp = client.get('/api/v1/finance/tax-report?period=2026-05')
        assert resp.status_code == 200

    def test_get_tax_report_400_missing_period(self, client):
        resp = client.get('/api/v1/finance/tax-report')
        assert resp.status_code == 400

    def test_get_tax_report_csv(self, client):
        resp = client.get('/api/v1/finance/tax-report?period=2026-05&format=csv')
        assert resp.status_code == 200
        assert b'VAT' in resp.data

    def test_get_anomalies_200(self, client):
        resp = client.get('/api/v1/finance/anomalies')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'anomalies' in data

    def test_get_fx_pnl_200(self, client):
        resp = client.get('/api/v1/finance/fx-pnl')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'fx_pnls' in data

    def test_get_metrics_200(self, client):
        resp = client.get('/api/v1/finance/metrics')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'revenue_records' in data
        assert 'ledger_entries' in data


# ══════════════════════════════════════════════════════════
# 15. Phase 118 통합 테스트 (환불 이벤트 → RefundReconciler)
# ══════════════════════════════════════════════════════════

class TestPhase118Integration:
    def test_refund_event_from_returns_automation(self, manager):
        """Phase 118 반품 처리 결과 환불 이벤트를 Phase 119에서 처리."""
        # Phase 118 반품 처리 완료 후 생성되는 환불 이벤트 형식
        refund_event = {
            'type': 'refunded',
            'order_id': 'ORD-PHASE118-001',
            'channel': 'coupang',
            'refund_amount': '85000',
            'currency': 'KRW',
            'pg': 'toss',
            'reason': 'change_of_mind',
            'source': 'returns_automation',
        }
        result = manager.on_order_event(refund_event)
        assert result['status'] == 'reconciled'
        assert result['order_id'] == 'ORD-PHASE118-001'

    def test_refund_event_posts_to_ledger(self, manager):
        """환불 이벤트 후 원장에 REFUND 분개가 생성된다."""
        manager.on_order_event({
            'type': 'refunded',
            'order_id': 'ORD-PHASE118-002',
            'channel': 'naver',
            'refund_amount': '30000',
            'currency': 'KRW',
        })
        entries = manager.get_ledger_entries(account='refund')
        assert len(entries) >= 1

    def test_partial_refund_reconciliation(self, manager):
        """부분 환불 처리."""
        result = manager._refund_rec.reconcile_partial_refund(
            'ORD-PHASE118-003',
            Decimal('15000'),
            'naver',
        )
        assert result['status'] == 'reconciled'
        assert result['refund_amount'] == '15000'

    def test_full_return_flow(self, manager):
        """주문 확정 → 환불 순서 처리."""
        manager.on_order_event({
            'type': 'order_confirmed',
            'order_id': 'ORD-FLOW-001',
            'channel': 'coupang',
            'gross_amount': '100000',
            'net_amount': '100000',
        })
        result = manager.on_order_event({
            'type': 'refunded',
            'order_id': 'ORD-FLOW-001',
            'channel': 'coupang',
            'refund_amount': '100000',
            'currency': 'KRW',
        })
        assert result['status'] == 'reconciled'
        m = manager.metrics()
        assert m['revenue_records'] >= 1


# ══════════════════════════════════════════════════════════
# 16. Phase 117 통합 테스트 (배송 완료 → RevenueRecognizer)
# ══════════════════════════════════════════════════════════

class TestPhase117Integration:
    def test_delivery_confirmed_triggers_revenue_recognition(self, manager):
        """Phase 117 배송 완료 이벤트 → 매출 인식."""
        # Phase 117 배송 완료 이벤트를 order_confirmed로 매핑
        delivery_event = {
            'type': 'order_confirmed',
            'order_id': 'ORD-PHASE117-001',
            'channel': 'naver',
            'gross_amount': '75000',
            'net_amount': '75000',
            'delivery_status': 'delivered',
        }
        result = manager.on_order_event(delivery_event)
        assert result['status'] == 'revenue_recognized'

    def test_delivery_event_creates_ledger_entries(self, manager):
        """배송 완료 후 AR + REVENUE 원장 항목 생성."""
        manager.on_order_event({
            'type': 'order_confirmed',
            'order_id': 'ORD-PHASE117-002',
            'channel': 'coupang',
            'gross_amount': '120000',
            'net_amount': '120000',
        })
        ar_entries = manager.get_ledger_entries(account='ar')
        rev_entries = manager.get_ledger_entries(account='revenue')
        assert len(ar_entries) >= 1
        assert len(rev_entries) >= 1

    def test_channel_fee_on_delivered_event(self, manager):
        """배송 완료 시 채널 수수료 계산."""
        result = manager.on_order_event({
            'type': 'delivered',
            'order_id': 'ORD-PHASE117-003',
            'channel': 'coupang',
            'gross_amount': '200000',
        })
        assert result['channel_fee'] == '22000'  # 11%

    def test_multiple_deliveries_accumulate_revenue(self, manager):
        """복수 배송 완료 시 매출 누적."""
        for i in range(3):
            manager.on_order_event({
                'type': 'order_confirmed',
                'order_id': f'ORD-MULTI-{i}',
                'channel': 'naver',
                'gross_amount': '30000',
                'net_amount': '30000',
            })
        m = manager.metrics()
        assert m['revenue_records'] == 3
        assert int(m['total_revenue_krw']) == 90000
