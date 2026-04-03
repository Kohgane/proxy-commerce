"""tests/test_payment_recovery.py — Phase 82: 결제 복구 테스트."""
from __future__ import annotations

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.payment_recovery import (
    FailedPayment,
    PaymentRecoveryManager,
    RetryStrategy,
    RecoveryAction,
    DunningManager,
    PaymentFallback,
    RecoveryReport,
)


class TestFailedPayment:
    def test_default_status(self):
        fp = FailedPayment(
            payment_id='p1', order_id='o1', amount=10000, error_code='CARD_DECLINED'
        )
        assert fp.status == 'failed'
        assert fp.attempts == 0


class TestRetryStrategy:
    def test_immediate(self):
        strategy = RetryStrategy('immediate')
        assert strategy.next_delay(1) == 0

    def test_exponential(self):
        strategy = RetryStrategy('exponential')
        assert strategy.next_delay(1) == 60
        assert strategy.next_delay(2) == 120
        assert strategy.next_delay(3) == 240

    def test_fixed(self):
        strategy = RetryStrategy('fixed', interval=120)
        assert strategy.next_delay(1) == 120
        assert strategy.next_delay(5) == 120


class TestRecoveryAction:
    def test_retry(self):
        action = RecoveryAction()
        result = action.execute('retry', 'p1')
        assert result['action'] == 'retry'
        assert result['status'] == 'scheduled'

    def test_notify(self):
        action = RecoveryAction()
        result = action.execute('notify', 'p1')
        assert result['action'] == 'notify'

    def test_suggest_alternative(self):
        action = RecoveryAction()
        result = action.execute('suggest_alternative', 'p1')
        assert 'alternatives' in result
        assert len(result['alternatives']) > 0

    def test_cancel(self):
        action = RecoveryAction()
        result = action.execute('cancel', 'p1')
        assert result['status'] == 'cancelled'


class TestPaymentRecoveryManager:
    def test_track_failure(self):
        mgr = PaymentRecoveryManager()
        result = mgr.track_failure('p1', 'o1', 10000, 'CARD_DECLINED')
        assert result['payment_id'] == 'p1'
        assert result['status'] == 'failed'

    def test_list_failures(self):
        mgr = PaymentRecoveryManager()
        mgr.track_failure('p1', 'o1', 10000, 'CARD_DECLINED')
        mgr.track_failure('p2', 'o2', 20000, 'INSUFFICIENT_FUNDS')
        failures = mgr.list_failures()
        assert len(failures) == 2

    def test_retry_not_found(self):
        mgr = PaymentRecoveryManager()
        with pytest.raises(KeyError):
            mgr.retry('nonexistent')

    def test_retry_increments_attempts(self):
        mgr = PaymentRecoveryManager()
        mgr.track_failure('p1', 'o1', 10000, 'CARD_DECLINED')
        result = mgr.retry('p1')
        assert result['attempts'] == 1

    def test_retry_recovers_on_third(self):
        mgr = PaymentRecoveryManager()
        mgr.track_failure('p1', 'o1', 10000, 'CARD_DECLINED')
        mgr.retry('p1')
        mgr.retry('p1')
        result = mgr.retry('p1')
        assert result['success'] is True


class TestDunningManager:
    def test_send_dunning(self):
        mgr = DunningManager()
        result = mgr.send_dunning('p1', 1)
        assert result['level'] == 1
        assert result['status'] == 'sent'

    def test_escalate(self):
        mgr = DunningManager()
        result = mgr.escalate('p1', 1)
        assert result['level'] == 2

    def test_get_history(self):
        mgr = DunningManager()
        mgr.send_dunning('p1', 1)
        mgr.send_dunning('p1', 2)
        history = mgr.get_history('p1')
        assert len(history) == 2


class TestPaymentFallback:
    def test_suggest_card_declined(self):
        fb = PaymentFallback()
        alts = fb.suggest_alternatives('CARD_DECLINED')
        assert len(alts) > 0
        assert 'virtual_account' in alts

    def test_suggest_default(self):
        fb = PaymentFallback()
        alts = fb.suggest_alternatives('UNKNOWN_ERROR')
        assert len(alts) > 0

    def test_try_alternative(self):
        fb = PaymentFallback()
        result = fb.try_alternative('p1', 'virtual_account')
        assert result['status'] == 'attempted'


class TestRecoveryReport:
    def test_empty_report(self):
        report = RecoveryReport()
        result = report.generate()
        assert result['total_failures'] == 0
        assert result['recovery_rate'] == 0.0

    def test_report_with_records(self):
        report = RecoveryReport()
        report.add_record('p1', True, 10000, 'CARD_DECLINED')
        report.add_record('p2', False, 20000, 'CARD_DECLINED')
        report.add_record('p3', True, 15000, 'INSUFFICIENT_FUNDS')
        result = report.generate()
        assert result['total_failures'] == 3
        assert result['recovered_count'] == 2
        assert result['failed_count'] == 1
        assert abs(result['recovery_rate'] - 2/3) < 0.01
        assert len(result['top_error_codes']) >= 1
