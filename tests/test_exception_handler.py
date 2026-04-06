"""tests/test_exception_handler.py — Phase 105: 예외 처리 + 자동 복구 테스트."""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest


# ─── ExceptionType / ExceptionSeverity / ExceptionStatus ─────────────────────

class TestExceptionEnums:
    def test_exception_type_values(self):
        from src.exception_handler.engine import ExceptionType
        assert ExceptionType.price_change == 'price_change'
        assert ExceptionType.out_of_stock == 'out_of_stock'
        assert ExceptionType.damaged_product == 'damaged_product'
        assert ExceptionType.delivery_delay == 'delivery_delay'
        assert ExceptionType.payment_failure == 'payment_failure'
        assert ExceptionType.customs_hold == 'customs_hold'
        assert ExceptionType.seller_issue == 'seller_issue'
        assert ExceptionType.wrong_item == 'wrong_item'
        assert ExceptionType.quantity_mismatch == 'quantity_mismatch'

    def test_exception_severity_values(self):
        from src.exception_handler.engine import ExceptionSeverity
        assert ExceptionSeverity.low == 'low'
        assert ExceptionSeverity.medium == 'medium'
        assert ExceptionSeverity.high == 'high'
        assert ExceptionSeverity.critical == 'critical'

    def test_exception_status_values(self):
        from src.exception_handler.engine import ExceptionStatus
        assert ExceptionStatus.detected == 'detected'
        assert ExceptionStatus.analyzing == 'analyzing'
        assert ExceptionStatus.action_taken == 'action_taken'
        assert ExceptionStatus.waiting_response == 'waiting_response'
        assert ExceptionStatus.resolved == 'resolved'
        assert ExceptionStatus.escalated == 'escalated'
        assert ExceptionStatus.manual_required == 'manual_required'

    def test_enums_are_strings(self):
        from src.exception_handler.engine import ExceptionType, ExceptionSeverity, ExceptionStatus
        assert isinstance(ExceptionType.price_change, str)
        assert isinstance(ExceptionSeverity.high, str)
        assert isinstance(ExceptionStatus.resolved, str)


# ─── ExceptionCase ────────────────────────────────────────────────────────────

class TestExceptionCase:
    def _make_case(self, **kwargs):
        from src.exception_handler.engine import ExceptionCase, ExceptionType, ExceptionSeverity
        defaults = dict(
            case_id='exc_test001',
            type=ExceptionType.payment_failure,
            severity=ExceptionSeverity.high,
        )
        defaults.update(kwargs)
        return ExceptionCase(**defaults)

    def test_default_status_detected(self):
        from src.exception_handler.engine import ExceptionStatus
        case = self._make_case()
        assert case.status == ExceptionStatus.detected

    def test_detected_at_set(self):
        case = self._make_case()
        assert case.detected_at is not None

    def test_retry_count_default_zero(self):
        case = self._make_case()
        assert case.retry_count == 0

    def test_update_status(self):
        from src.exception_handler.engine import ExceptionStatus
        case = self._make_case()
        case.update_status(ExceptionStatus.analyzing)
        assert case.status == ExceptionStatus.analyzing

    def test_resolved_at_set_on_resolve(self):
        from src.exception_handler.engine import ExceptionStatus
        case = self._make_case()
        case.update_status(ExceptionStatus.resolved)
        assert case.resolved_at is not None

    def test_to_dict(self):
        case = self._make_case()
        d = case.to_dict()
        assert d['case_id'] == 'exc_test001'
        assert d['type'] == 'payment_failure'
        assert d['severity'] == 'high'
        assert 'detected_at' in d

    def test_metadata_default_empty(self):
        case = self._make_case()
        assert case.metadata == {}


# ─── ExceptionEngine ──────────────────────────────────────────────────────────

class TestExceptionEngine:
    def _make_engine(self):
        from src.exception_handler.engine import ExceptionEngine
        return ExceptionEngine()

    def test_detect_creates_case(self):
        from src.exception_handler.engine import ExceptionType
        engine = self._make_engine()
        case = engine.detect(ExceptionType.payment_failure, order_id='ORD001')
        assert case.case_id.startswith('exc_')
        assert case.type == ExceptionType.payment_failure
        assert case.order_id == 'ORD001'

    def test_detect_default_severity(self):
        from src.exception_handler.engine import ExceptionType, ExceptionSeverity
        engine = self._make_engine()
        case = engine.detect(ExceptionType.payment_failure)
        assert case.severity == ExceptionSeverity.high

    def test_detect_custom_severity(self):
        from src.exception_handler.engine import ExceptionType, ExceptionSeverity
        engine = self._make_engine()
        case = engine.detect(ExceptionType.price_change, severity=ExceptionSeverity.critical)
        assert case.severity == ExceptionSeverity.critical

    def test_get_case(self):
        from src.exception_handler.engine import ExceptionType
        engine = self._make_engine()
        case = engine.detect(ExceptionType.delivery_delay)
        fetched = engine.get_case(case.case_id)
        assert fetched is not None
        assert fetched.case_id == case.case_id

    def test_get_case_not_found(self):
        engine = self._make_engine()
        assert engine.get_case('nonexistent') is None

    def test_list_cases(self):
        from src.exception_handler.engine import ExceptionType
        engine = self._make_engine()
        engine.detect(ExceptionType.payment_failure)
        engine.detect(ExceptionType.delivery_delay)
        assert len(engine.list_cases()) == 2

    def test_list_cases_filter_type(self):
        from src.exception_handler.engine import ExceptionType
        engine = self._make_engine()
        engine.detect(ExceptionType.payment_failure)
        engine.detect(ExceptionType.delivery_delay)
        pf_cases = engine.list_cases(exception_type=ExceptionType.payment_failure)
        assert len(pf_cases) == 1

    def test_analyze(self):
        from src.exception_handler.engine import ExceptionType, ExceptionStatus
        engine = self._make_engine()
        case = engine.detect(ExceptionType.seller_issue)
        engine.analyze(case.case_id)
        assert case.status == ExceptionStatus.analyzing

    def test_take_action(self):
        from src.exception_handler.engine import ExceptionType, ExceptionStatus
        engine = self._make_engine()
        case = engine.detect(ExceptionType.seller_issue)
        engine.take_action(case.case_id, '이메일 발송')
        assert case.status == ExceptionStatus.action_taken
        assert case.notes == '이메일 발송'

    def test_resolve(self):
        from src.exception_handler.engine import ExceptionType, ExceptionStatus
        engine = self._make_engine()
        case = engine.detect(ExceptionType.payment_failure)
        engine.resolve(case.case_id, '환불 완료')
        assert case.status == ExceptionStatus.resolved
        assert case.resolution == '환불 완료'
        assert case.resolved_at is not None

    def test_escalate(self):
        from src.exception_handler.engine import ExceptionType, ExceptionStatus
        engine = self._make_engine()
        case = engine.detect(ExceptionType.customs_hold)
        engine.escalate(case.case_id, '수동 처리 필요')
        assert case.status == ExceptionStatus.escalated

    def test_increment_retry(self):
        from src.exception_handler.engine import ExceptionType
        engine = self._make_engine()
        case = engine.detect(ExceptionType.payment_failure)
        engine.increment_retry(case.case_id)
        engine.increment_retry(case.case_id)
        assert case.retry_count == 2

    def test_get_case_not_found_raises(self):
        engine = self._make_engine()
        with pytest.raises(KeyError):
            engine.resolve('nonexistent')

    def test_get_stats_empty(self):
        engine = self._make_engine()
        stats = engine.get_stats()
        assert stats['total'] == 0
        assert stats['resolution_rate'] == 0.0

    def test_get_stats(self):
        from src.exception_handler.engine import ExceptionType
        engine = self._make_engine()
        case = engine.detect(ExceptionType.payment_failure)
        engine.resolve(case.case_id, 'ok')
        stats = engine.get_stats()
        assert stats['total'] == 1
        assert stats['resolved'] == 1
        assert stats['resolution_rate'] == 1.0

    def test_mark_manual_required(self):
        from src.exception_handler.engine import ExceptionType, ExceptionStatus
        engine = self._make_engine()
        case = engine.detect(ExceptionType.wrong_item)
        engine.mark_manual_required(case.case_id)
        assert case.status == ExceptionStatus.manual_required


# ─── DamageType / DamageGrade ────────────────────────────────────────────────

class TestDamageEnums:
    def test_damage_type_values(self):
        from src.exception_handler.damage_handler import DamageType
        assert DamageType.scratched == 'scratched'
        assert DamageType.dented == 'dented'
        assert DamageType.broken == 'broken'
        assert DamageType.water_damage == 'water_damage'
        assert DamageType.missing_parts == 'missing_parts'
        assert DamageType.wrong_color == 'wrong_color'

    def test_damage_grade_values(self):
        from src.exception_handler.damage_handler import DamageGrade
        assert DamageGrade.A == 'A'
        assert DamageGrade.B == 'B'
        assert DamageGrade.C == 'C'
        assert DamageGrade.D == 'D'


# ─── DamageReport ────────────────────────────────────────────────────────────

class TestDamageReport:
    def _make_report(self, **kwargs):
        from src.exception_handler.damage_handler import DamageReport, DamageType, DamageGrade
        defaults = dict(
            report_id='dmg_test001',
            order_id='ORD001',
            damage_type=DamageType.scratched,
            grade=DamageGrade.A,
        )
        defaults.update(kwargs)
        return DamageReport(**defaults)

    def test_to_dict(self):
        report = self._make_report()
        d = report.to_dict()
        assert d['report_id'] == 'dmg_test001'
        assert d['order_id'] == 'ORD001'
        assert d['damage_type'] == 'scratched'
        assert d['grade'] == 'A'

    def test_default_photos_empty(self):
        report = self._make_report()
        assert report.photos == []

    def test_claim_sent_default_false(self):
        report = self._make_report()
        assert report.claim_sent is False


# ─── DamageHandler ────────────────────────────────────────────────────────────

class TestDamageHandler:
    def _make_handler(self):
        from src.exception_handler.damage_handler import DamageHandler
        return DamageHandler()

    def test_report_damage(self):
        from src.exception_handler.damage_handler import DamageType, DamageGrade
        handler = self._make_handler()
        report = handler.report_damage('ORD001', DamageType.scratched, DamageGrade.A)
        assert report.report_id.startswith('dmg_')
        assert report.order_id == 'ORD001'

    def test_get_report(self):
        from src.exception_handler.damage_handler import DamageType, DamageGrade
        handler = self._make_handler()
        report = handler.report_damage('ORD002', DamageType.broken, DamageGrade.D)
        fetched = handler.get_report(report.report_id)
        assert fetched is not None

    def test_get_report_not_found(self):
        handler = self._make_handler()
        assert handler.get_report('nonexistent') is None

    def test_determine_action_grade_a(self):
        from src.exception_handler.damage_handler import DamageType, DamageGrade
        handler = self._make_handler()
        report = handler.report_damage('ORD003', DamageType.scratched, DamageGrade.A)
        action = handler.determine_action(report.report_id, item_price=100000.0)
        assert action['compensation_rate'] == pytest.approx(0.08)
        assert action['send_claim'] is False

    def test_determine_action_grade_d(self):
        from src.exception_handler.damage_handler import DamageType, DamageGrade
        handler = self._make_handler()
        report = handler.report_damage('ORD004', DamageType.broken, DamageGrade.D)
        action = handler.determine_action(report.report_id, item_price=50000.0)
        assert action['compensation_rate'] == pytest.approx(1.0)
        assert action['send_claim'] is True
        assert action['file_insurance'] is True
        assert report.claim_sent is True
        assert report.insurance_filed is True

    def test_determine_action_grade_c_sends_claim(self):
        from src.exception_handler.damage_handler import DamageType, DamageGrade
        handler = self._make_handler()
        report = handler.report_damage('ORD005', DamageType.dented, DamageGrade.C)
        action = handler.determine_action(report.report_id, 0.0)
        assert action['send_claim'] is True
        assert action['file_insurance'] is False

    def test_list_reports(self):
        from src.exception_handler.damage_handler import DamageType, DamageGrade
        handler = self._make_handler()
        handler.report_damage('ORD010', DamageType.scratched, DamageGrade.A)
        handler.report_damage('ORD011', DamageType.broken, DamageGrade.D)
        assert len(handler.list_reports()) == 2

    def test_list_reports_filter_order(self):
        from src.exception_handler.damage_handler import DamageType, DamageGrade
        handler = self._make_handler()
        handler.report_damage('ORD010', DamageType.scratched, DamageGrade.A)
        handler.report_damage('ORD011', DamageType.broken, DamageGrade.D)
        reports = handler.list_reports(order_id='ORD010')
        assert len(reports) == 1

    def test_get_stats(self):
        from src.exception_handler.damage_handler import DamageType, DamageGrade
        handler = self._make_handler()
        handler.report_damage('ORD020', DamageType.scratched, DamageGrade.A)
        stats = handler.get_stats()
        assert stats['total'] == 1
        assert 'A' in stats['by_grade']

    def test_send_seller_claim(self):
        from src.exception_handler.damage_handler import DamageType, DamageGrade
        handler = self._make_handler()
        report = handler.report_damage('ORD030', DamageType.broken, DamageGrade.C)
        result = handler.send_seller_claim(report.report_id)
        assert result is True
        assert report.claim_sent is True

    def test_file_insurance_claim(self):
        from src.exception_handler.damage_handler import DamageType, DamageGrade
        handler = self._make_handler()
        report = handler.report_damage('ORD031', DamageType.water_damage, DamageGrade.D)
        result = handler.file_insurance_claim(report.report_id)
        assert result is True
        assert report.insurance_filed is True


# ─── PriceAlertType ───────────────────────────────────────────────────────────

class TestPriceAlertType:
    def test_values(self):
        from src.exception_handler.price_detector import PriceAlertType
        assert PriceAlertType.price_drop == 'price_drop'
        assert PriceAlertType.price_surge == 'price_surge'
        assert PriceAlertType.out_of_budget == 'out_of_budget'
        assert PriceAlertType.better_deal_found == 'better_deal_found'


# ─── PriceAlert ───────────────────────────────────────────────────────────────

class TestPriceAlert:
    def _make_alert(self, **kwargs):
        from src.exception_handler.price_detector import PriceAlert, PriceAlertType
        defaults = dict(
            alert_id='pa_test001',
            product_id='PROD001',
            old_price=10000.0,
            new_price=8000.0,
            change_percent=-20.0,
            alert_type=PriceAlertType.price_drop,
        )
        defaults.update(kwargs)
        return PriceAlert(**defaults)

    def test_to_dict(self):
        alert = self._make_alert()
        d = alert.to_dict()
        assert d['alert_id'] == 'pa_test001'
        assert d['product_id'] == 'PROD001'
        assert d['change_percent'] == -20.0

    def test_acknowledged_default_false(self):
        alert = self._make_alert()
        assert alert.acknowledged is False


# ─── PriceChangeDetector ──────────────────────────────────────────────────────

class TestPriceChangeDetector:
    def _make_detector(self, **kwargs):
        from src.exception_handler.price_detector import PriceChangeDetector
        return PriceChangeDetector(**kwargs)

    def test_no_alert_on_first_record(self):
        detector = self._make_detector()
        alert = detector.record_price('PROD001', 10000.0)
        assert alert is None

    def test_price_drop_alert(self):
        from src.exception_handler.price_detector import PriceAlertType
        detector = self._make_detector(drop_threshold_pct=-10.0)
        detector.record_price('PROD001', 10000.0)
        alert = detector.record_price('PROD001', 8000.0)  # -20%
        assert alert is not None
        assert alert.alert_type == PriceAlertType.price_drop

    def test_price_surge_alert(self):
        from src.exception_handler.price_detector import PriceAlertType
        detector = self._make_detector(surge_threshold_pct=10.0)
        detector.record_price('PROD001', 10000.0)
        alert = detector.record_price('PROD001', 12000.0)  # +20%
        assert alert is not None
        assert alert.alert_type == PriceAlertType.price_surge

    def test_no_alert_within_threshold(self):
        detector = self._make_detector(drop_threshold_pct=-10.0, surge_threshold_pct=10.0)
        detector.record_price('PROD001', 10000.0)
        alert = detector.record_price('PROD001', 10500.0)  # +5%
        assert alert is None

    def test_out_of_budget_alert(self):
        from src.exception_handler.price_detector import PriceAlertType
        detector = self._make_detector()
        detector.set_budget('PROD001', 15000.0)
        detector.record_price('PROD001', 10000.0)
        alert = detector.record_price('PROD001', 16000.0)
        assert alert is not None
        assert alert.alert_type == PriceAlertType.out_of_budget

    def test_get_price_history(self):
        detector = self._make_detector()
        detector.record_price('PROD002', 10000.0)
        detector.record_price('PROD002', 11000.0)
        history = detector.get_price_history('PROD002')
        assert len(history) == 2
        assert history[0]['price'] == 10000.0

    def test_get_trend_rising(self):
        detector = self._make_detector()
        for p in [1000, 1100, 1200, 1300, 1400]:
            detector.record_price('PROD003', p)
        assert detector.get_trend('PROD003') == 'rising'

    def test_get_trend_falling(self):
        detector = self._make_detector()
        for p in [1400, 1300, 1200, 1100, 1000]:
            detector.record_price('PROD003', p)
        assert detector.get_trend('PROD003') == 'falling'

    def test_get_trend_stable(self):
        detector = self._make_detector()
        detector.record_price('PROD004', 1000.0)
        assert detector.get_trend('PROD004') == 'stable'

    def test_acknowledge(self):
        from src.exception_handler.price_detector import PriceAlertType
        detector = self._make_detector(drop_threshold_pct=-10.0)
        detector.record_price('PROD005', 10000.0)
        alert = detector.record_price('PROD005', 8000.0)
        assert alert is not None
        detector.acknowledge(alert.alert_id)
        assert alert.acknowledged is True

    def test_list_alerts_filter_acknowledged(self):
        from src.exception_handler.price_detector import PriceAlertType
        detector = self._make_detector(drop_threshold_pct=-10.0)
        detector.record_price('PROD006', 10000.0)
        alert = detector.record_price('PROD006', 8000.0)
        assert alert is not None
        unacked = detector.list_alerts(acknowledged=False)
        assert len(unacked) == 1
        detector.acknowledge(alert.alert_id)
        acked = detector.list_alerts(acknowledged=True)
        assert len(acked) == 1

    def test_configure(self):
        detector = self._make_detector()
        detector.configure(-5.0, 5.0)
        assert detector.drop_threshold_pct == -5.0
        assert detector.surge_threshold_pct == 5.0

    def test_check_price(self):
        detector = self._make_detector(drop_threshold_pct=-10.0)
        detector.record_price('PROD007', 10000.0)
        alert = detector.check_price('PROD007', 8000.0)
        assert alert is not None

    def test_suggest_alternative(self):
        detector = self._make_detector(surge_threshold_pct=10.0)
        detector.record_price('PROD008', 10000.0)
        alert = detector.record_price('PROD008', 12000.0)
        assert alert is not None
        new_alert = detector.suggest_alternative(alert.alert_id, {'price': 9000.0, 'url': 'http://x'})
        assert new_alert is not None


# ─── BackoffStrategy / RetryPolicy ────────────────────────────────────────────

class TestBackoffStrategy:
    def test_values(self):
        from src.exception_handler.retry_manager import BackoffStrategy
        assert BackoffStrategy.fixed == 'fixed'
        assert BackoffStrategy.exponential == 'exponential'
        assert BackoffStrategy.linear == 'linear'
        assert BackoffStrategy.jitter == 'jitter'


class TestRetryPolicy:
    def _make_policy(self, **kwargs):
        from src.exception_handler.retry_manager import RetryPolicy, BackoffStrategy
        defaults = dict(max_retries=3, backoff_strategy=BackoffStrategy.exponential, delay_seconds=1.0)
        defaults.update(kwargs)
        return RetryPolicy(**defaults)

    def test_default_values(self):
        from src.exception_handler.retry_manager import RetryPolicy, BackoffStrategy
        p = RetryPolicy()
        assert p.max_retries == 3
        assert p.backoff_strategy == BackoffStrategy.exponential

    def test_compute_delay_fixed(self):
        from src.exception_handler.retry_manager import RetryPolicy, BackoffStrategy
        p = RetryPolicy(backoff_strategy=BackoffStrategy.fixed, delay_seconds=5.0)
        assert p.compute_delay(1) == 5.0
        assert p.compute_delay(3) == 5.0

    def test_compute_delay_exponential(self):
        from src.exception_handler.retry_manager import RetryPolicy, BackoffStrategy
        p = RetryPolicy(backoff_strategy=BackoffStrategy.exponential, delay_seconds=1.0)
        assert p.compute_delay(1) == pytest.approx(1.0)
        assert p.compute_delay(2) == pytest.approx(2.0)
        assert p.compute_delay(3) == pytest.approx(4.0)

    def test_compute_delay_linear(self):
        from src.exception_handler.retry_manager import RetryPolicy, BackoffStrategy
        p = RetryPolicy(backoff_strategy=BackoffStrategy.linear, delay_seconds=2.0)
        assert p.compute_delay(1) == pytest.approx(2.0)
        assert p.compute_delay(3) == pytest.approx(6.0)

    def test_compute_delay_jitter(self):
        from src.exception_handler.retry_manager import RetryPolicy, BackoffStrategy
        p = RetryPolicy(backoff_strategy=BackoffStrategy.jitter, delay_seconds=1.0, max_delay_seconds=100.0)
        delay = p.compute_delay(2)
        assert 0 <= delay <= 2.0

    def test_compute_delay_max_cap(self):
        from src.exception_handler.retry_manager import RetryPolicy, BackoffStrategy
        p = RetryPolicy(backoff_strategy=BackoffStrategy.exponential, delay_seconds=1.0, max_delay_seconds=5.0)
        assert p.compute_delay(10) == 5.0

    def test_to_dict(self):
        p = self._make_policy()
        d = p.to_dict()
        assert 'max_retries' in d
        assert 'backoff_strategy' in d


# ─── RetryManager ─────────────────────────────────────────────────────────────

class TestRetryManager:
    def _make_manager(self):
        from src.exception_handler.retry_manager import RetryManager
        return RetryManager()

    def test_register(self):
        mgr = self._make_manager()
        record = mgr.register('payment', order_id='ORD001')
        assert record.record_id.startswith('retry_')
        assert record.task_type == 'payment'

    def test_execute_success(self):
        from src.exception_handler.retry_manager import RetryStatus
        mgr = self._make_manager()
        record = mgr.register('api_call')
        result = mgr.execute(record.record_id, lambda: {'ok': True})
        assert result.status == RetryStatus.succeeded
        assert result.attempt_count == 1

    def test_execute_fail_then_succeed(self):
        from src.exception_handler.retry_manager import RetryStatus
        mgr = self._make_manager()
        record = mgr.register('api_call')
        call_count = [0]

        def task():
            call_count[0] += 1
            if call_count[0] < 2:
                raise RuntimeError('일시적 오류')
            return {'ok': True}

        result = mgr.execute(record.record_id, task)
        assert result.status == RetryStatus.succeeded
        assert call_count[0] == 2

    def test_execute_exhausted(self):
        from src.exception_handler.retry_manager import RetryPolicy, RetryStatus
        mgr = self._make_manager()
        policy = RetryPolicy(max_retries=2, delay_seconds=0.0)
        record = mgr.register('api_call', policy=policy)
        result = mgr.execute(record.record_id, lambda: (_ for _ in ()).throw(RuntimeError('fail')))
        assert result.status == RetryStatus.manual_required

    def test_list_records(self):
        mgr = self._make_manager()
        mgr.register('payment')
        mgr.register('api_call')
        assert len(mgr.list_records()) == 2

    def test_list_records_filter_task_type(self):
        mgr = self._make_manager()
        mgr.register('payment')
        mgr.register('api_call')
        pay_records = mgr.list_records(task_type='payment')
        assert len(pay_records) == 1

    def test_get_record(self):
        mgr = self._make_manager()
        record = mgr.register('payment')
        fetched = mgr.get_record(record.record_id)
        assert fetched is not None

    def test_get_stats(self):
        mgr = self._make_manager()
        record = mgr.register('payment')
        mgr.execute(record.record_id, lambda: 'ok')
        stats = mgr.get_stats()
        assert stats['total'] == 1
        assert stats['succeeded'] == 1
        assert stats['success_rate'] == 1.0

    def test_get_stats_empty(self):
        mgr = self._make_manager()
        stats = mgr.get_stats()
        assert stats['success_rate'] == 0.0

    def test_record_to_dict(self):
        mgr = self._make_manager()
        record = mgr.register('payment', order_id='ORD001')
        d = record.to_dict()
        assert d['task_type'] == 'payment'
        assert d['order_id'] == 'ORD001'


# ─── RecoveryAction / AutoRecoveryService ────────────────────────────────────

class TestRecoveryActions:
    def test_reorder_action(self):
        from src.exception_handler.auto_recovery import ReorderAction
        action = ReorderAction()
        result = action.execute({'order_id': 'ORD001', 'alternative_seller': 'sel_X'})
        assert result['success'] is True
        assert 'new_order_id' in result

    def test_refund_action(self):
        from src.exception_handler.auto_recovery import RefundAction
        action = RefundAction()
        result = action.execute({'order_id': 'ORD001', 'refund_amount': 30000.0})
        assert result['success'] is True
        assert result['amount'] == 30000.0

    def test_reroute_action(self):
        from src.exception_handler.auto_recovery import RerouteAction
        action = RerouteAction()
        result = action.execute({'order_id': 'ORD001', 'new_route': 'express'})
        assert result['success'] is True
        assert result['new_route'] == 'express'

    def test_escalate_action(self):
        from src.exception_handler.auto_recovery import EscalateAction
        action = EscalateAction()
        result = action.execute({'case_id': 'exc_001', 'reason': '복구 불가'})
        assert result['success'] is True
        assert 'ticket_id' in result

    def test_compensate_action_coupon(self):
        from src.exception_handler.auto_recovery import CompensateAction
        action = CompensateAction()
        result = action.execute({'order_id': 'ORD001', 'compensation_type': 'coupon', 'compensation_amount': 5000.0})
        assert result['success'] is True
        assert result['coupon_code'] is not None

    def test_compensate_action_points(self):
        from src.exception_handler.auto_recovery import CompensateAction
        action = CompensateAction()
        result = action.execute({'order_id': 'ORD001', 'compensation_type': 'points', 'compensation_amount': 3000.0})
        assert result['success'] is True
        assert result['coupon_code'] is None

    def test_estimated_cost(self):
        from src.exception_handler.auto_recovery import RefundAction
        action = RefundAction()
        cost = action.estimated_cost({'refund_amount': 10000.0})
        assert cost == 10000.0


class TestAutoRecoveryService:
    def _make_service(self):
        from src.exception_handler.auto_recovery import AutoRecoveryService
        return AutoRecoveryService()

    def test_execute_reorder(self):
        svc = self._make_service()
        attempt = svc.execute('reorder', 'exc_001', {'order_id': 'ORD001'})
        assert attempt.success is True
        assert attempt.action_name == 'reorder'

    def test_execute_refund(self):
        svc = self._make_service()
        attempt = svc.execute('refund', 'exc_001', {'refund_amount': 50000.0})
        assert attempt.success is True

    def test_execute_unknown_action_raises(self):
        svc = self._make_service()
        with pytest.raises(ValueError):
            svc.execute('unknown_action', 'exc_001')

    def test_list_attempts(self):
        svc = self._make_service()
        svc.execute('reorder', 'exc_001', {'order_id': 'ORD001'})
        svc.execute('refund', 'exc_002', {'refund_amount': 1000.0})
        assert len(svc.list_attempts()) == 2

    def test_list_attempts_filter_case(self):
        svc = self._make_service()
        svc.execute('reorder', 'exc_001', {'order_id': 'ORD001'})
        svc.execute('refund', 'exc_002', {'refund_amount': 1000.0})
        attempts = svc.list_attempts(case_id='exc_001')
        assert len(attempts) == 1

    def test_get_stats(self):
        svc = self._make_service()
        svc.execute('reorder', 'exc_001', {'order_id': 'ORD001'})
        stats = svc.get_stats()
        assert stats['total_attempts'] == 1
        assert stats['succeeded'] == 1
        assert stats['success_rate'] == 1.0

    def test_get_stats_empty(self):
        svc = self._make_service()
        stats = svc.get_stats()
        assert stats['success_rate'] == 0.0

    def test_attempt_to_dict(self):
        svc = self._make_service()
        attempt = svc.execute('escalate', 'exc_001', {'reason': '테스트'})
        d = attempt.to_dict()
        assert 'attempt_id' in d
        assert d['action_name'] == 'escalate'


# ─── DelayStage / DeliveryDelayHandler ───────────────────────────────────────

class TestDelayEnums:
    def test_delay_stage_values(self):
        from src.exception_handler.delay_handler import DelayStage
        assert DelayStage.minor == 'minor'
        assert DelayStage.moderate == 'moderate'
        assert DelayStage.severe == 'severe'


class TestDeliveryDelayHandler:
    def _make_handler(self):
        from src.exception_handler.delay_handler import DeliveryDelayHandler
        return DeliveryDelayHandler()

    def test_detect_delay_minor(self):
        from src.exception_handler.delay_handler import DelayStage, DelayAction
        handler = self._make_handler()
        record = handler.detect_delay('ORD001', '2026-04-01', '2026-04-03', 2.0)
        assert record.stage == DelayStage.minor
        assert DelayAction.notify_customer.value in record.actions_taken

    def test_detect_delay_moderate(self):
        from src.exception_handler.delay_handler import DelayStage, DelayAction
        handler = self._make_handler()
        record = handler.detect_delay('ORD002', '2026-04-01', '2026-04-05', 4.0)
        assert record.stage == DelayStage.moderate
        assert DelayAction.query_carrier.value in record.actions_taken
        assert DelayAction.offer_compensation.value in record.actions_taken
        assert record.carrier_response is not None
        assert record.compensation is not None

    def test_detect_delay_severe(self):
        from src.exception_handler.delay_handler import DelayStage, DelayAction
        handler = self._make_handler()
        record = handler.detect_delay('ORD003', '2026-04-01', '2026-04-08', 7.0)
        assert record.stage == DelayStage.severe
        assert DelayAction.reship_or_refund.value in record.actions_taken

    def test_record_to_dict(self):
        handler = self._make_handler()
        record = handler.detect_delay('ORD004', '2026-04-01', '2026-04-02', 1.0)
        d = record.to_dict()
        assert d['order_id'] == 'ORD004'
        assert d['delay_days'] == 1.0

    def test_resolve(self):
        handler = self._make_handler()
        record = handler.detect_delay('ORD005', '2026-04-01', '2026-04-03', 2.0)
        handler.resolve(record.record_id)
        assert record.resolved is True

    def test_list_records(self):
        handler = self._make_handler()
        handler.detect_delay('ORD010', '2026-04-01', '2026-04-02', 1.0)
        handler.detect_delay('ORD011', '2026-04-01', '2026-04-06', 5.0)
        assert len(handler.list_records()) == 2

    def test_list_records_filter_resolved(self):
        handler = self._make_handler()
        r1 = handler.detect_delay('ORD012', '2026-04-01', '2026-04-02', 1.0)
        handler.detect_delay('ORD013', '2026-04-01', '2026-04-06', 5.0)
        handler.resolve(r1.record_id)
        resolved = handler.list_records(resolved=True)
        assert len(resolved) == 1

    def test_get_stats(self):
        handler = self._make_handler()
        handler.detect_delay('ORD020', '2026-04-01', '2026-04-02', 1.5)
        stats = handler.get_stats()
        assert stats['total'] == 1
        assert 'minor' in stats['by_stage']
        assert stats['avg_delay_days'] == 1.5

    def test_get_stats_empty(self):
        handler = self._make_handler()
        stats = handler.get_stats()
        assert stats['avg_delay_days'] == 0.0


# ─── PaymentFailureReason / PaymentFailureHandler ────────────────────────────

class TestPaymentFailureEnums:
    def test_reason_values(self):
        from src.exception_handler.payment_failure import PaymentFailureReason
        assert PaymentFailureReason.insufficient_balance == 'insufficient_balance'
        assert PaymentFailureReason.card_expired == 'card_expired'
        assert PaymentFailureReason.limit_exceeded == 'limit_exceeded'
        assert PaymentFailureReason.system_error == 'system_error'
        assert PaymentFailureReason.invalid_card == 'invalid_card'
        assert PaymentFailureReason.declined == 'declined'

    def test_status_values(self):
        from src.exception_handler.payment_failure import PaymentFailureStatus
        assert PaymentFailureStatus.detected == 'detected'
        assert PaymentFailureStatus.retrying == 'retrying'
        assert PaymentFailureStatus.alternative_attempted == 'alternative_attempted'
        assert PaymentFailureStatus.resolved == 'resolved'
        assert PaymentFailureStatus.failed == 'failed'


class TestPaymentFailureHandler:
    def _make_handler(self):
        from src.exception_handler.payment_failure import PaymentFailureHandler
        return PaymentFailureHandler()

    def test_detect_creates_record(self):
        from src.exception_handler.payment_failure import PaymentFailureReason
        handler = self._make_handler()
        record = handler.detect('ORD001', 50000.0, PaymentFailureReason.insufficient_balance)
        assert record.record_id.startswith('pf_')
        assert record.order_id == 'ORD001'
        assert record.amount == 50000.0

    def test_detect_system_error_schedules_retry(self):
        from src.exception_handler.payment_failure import PaymentFailureReason, PaymentFailureStatus
        handler = self._make_handler()
        record = handler.detect('ORD002', 30000.0, PaymentFailureReason.system_error)
        assert record.status == PaymentFailureStatus.retrying

    def test_detect_card_issue_switches_alternative(self):
        from src.exception_handler.payment_failure import PaymentFailureReason, PaymentFailureStatus
        handler = self._make_handler()
        record = handler.detect('ORD003', 20000.0, PaymentFailureReason.card_expired)
        assert record.status == PaymentFailureStatus.alternative_attempted
        assert record.alternative_method is not None

    def test_resolve(self):
        from src.exception_handler.payment_failure import PaymentFailureReason, PaymentFailureStatus
        handler = self._make_handler()
        record = handler.detect('ORD004', 10000.0, PaymentFailureReason.declined)
        handler.resolve(record.record_id)
        assert record.resolved is True
        assert record.status == PaymentFailureStatus.resolved
        assert record.resolved_at is not None

    def test_retry(self):
        from src.exception_handler.payment_failure import PaymentFailureReason, PaymentFailureStatus
        handler = self._make_handler()
        record = handler.detect('ORD005', 15000.0, PaymentFailureReason.system_error)
        handler.retry(record.record_id)
        assert record.resolved is True

    def test_list_records(self):
        from src.exception_handler.payment_failure import PaymentFailureReason
        handler = self._make_handler()
        handler.detect('ORD010', 1000.0, PaymentFailureReason.declined)
        handler.detect('ORD011', 2000.0, PaymentFailureReason.card_expired)
        assert len(handler.list_records()) == 2

    def test_list_records_filter_resolved(self):
        from src.exception_handler.payment_failure import PaymentFailureReason
        handler = self._make_handler()
        r = handler.detect('ORD012', 1000.0, PaymentFailureReason.declined)
        handler.detect('ORD013', 2000.0, PaymentFailureReason.card_expired)
        handler.resolve(r.record_id)
        resolved = handler.list_records(resolved=True)
        assert len(resolved) == 1

    def test_get_record(self):
        from src.exception_handler.payment_failure import PaymentFailureReason
        handler = self._make_handler()
        record = handler.detect('ORD020', 1000.0, PaymentFailureReason.declined)
        fetched = handler.get_record(record.record_id)
        assert fetched is not None

    def test_get_stats(self):
        from src.exception_handler.payment_failure import PaymentFailureReason
        handler = self._make_handler()
        r = handler.detect('ORD030', 5000.0, PaymentFailureReason.declined)
        handler.resolve(r.record_id)
        stats = handler.get_stats()
        assert stats['total'] == 1
        assert stats['resolved'] == 1
        assert stats['resolution_rate'] == 1.0
        assert stats['total_amount_affected'] == 5000.0

    def test_record_to_dict(self):
        from src.exception_handler.payment_failure import PaymentFailureReason
        handler = self._make_handler()
        record = handler.detect('ORD040', 3000.0, PaymentFailureReason.limit_exceeded)
        d = record.to_dict()
        assert d['order_id'] == 'ORD040'
        assert d['amount'] == 3000.0
        assert d['reason'] == 'limit_exceeded'


# ─── ExceptionDashboard ──────────────────────────────────────────────────────

class TestExceptionDashboard:
    def _make_dashboard(self):
        from src.exception_handler.engine import ExceptionEngine
        from src.exception_handler.damage_handler import DamageHandler
        from src.exception_handler.price_detector import PriceChangeDetector
        from src.exception_handler.retry_manager import RetryManager
        from src.exception_handler.auto_recovery import AutoRecoveryService
        from src.exception_handler.delay_handler import DeliveryDelayHandler
        from src.exception_handler.payment_failure import PaymentFailureHandler
        from src.exception_handler.dashboard import ExceptionDashboard
        return ExceptionDashboard(
            engine=ExceptionEngine(),
            damage_handler=DamageHandler(),
            price_detector=PriceChangeDetector(),
            retry_manager=RetryManager(),
            recovery_service=AutoRecoveryService(),
            delay_handler=DeliveryDelayHandler(),
            payment_handler=PaymentFailureHandler(),
        )

    def test_get_summary_keys(self):
        db = self._make_dashboard()
        summary = db.get_summary()
        assert 'exceptions' in summary
        assert 'damage' in summary
        assert 'price_alerts' in summary
        assert 'retries' in summary
        assert 'recovery' in summary
        assert 'delivery_delays' in summary
        assert 'payment_failures' in summary

    def test_get_exception_trend(self):
        db = self._make_dashboard()
        trend = db.get_exception_trend()
        assert 'weekly' in trend
        assert 'monthly' in trend

    def test_get_cost_impact(self):
        db = self._make_dashboard()
        cost = db.get_cost_impact()
        assert 'damage_compensation' in cost
        assert 'recovery_cost' in cost
        assert 'total_impact' in cost

    def test_get_resolution_metrics(self):
        db = self._make_dashboard()
        metrics = db.get_resolution_metrics()
        assert 'auto_recovery_rate' in metrics
        assert 'avg_resolution_hours' in metrics
        assert 'escalation_rate' in metrics

    def test_dashboard_no_components(self):
        from src.exception_handler.dashboard import ExceptionDashboard
        db = ExceptionDashboard()
        summary = db.get_summary()
        assert summary == {}


# ─── API Blueprint ───────────────────────────────────────────────────────────

class TestExceptionHandlerAPI:
    @pytest.fixture
    def client(self):
        import flask
        app = flask.Flask(__name__)
        from src.api.exception_handler_api import exception_handler_bp
        app.register_blueprint(exception_handler_bp)
        app.config['TESTING'] = True
        with app.test_client() as c:
            yield c

    def test_list_cases_empty(self, client):
        resp = client.get('/api/v1/exceptions/cases')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['total'] == 0

    def test_get_case_not_found(self, client):
        resp = client.get('/api/v1/exceptions/cases/nonexistent')
        assert resp.status_code == 404

    def test_simulate_exception(self, client):
        resp = client.post('/api/v1/exceptions/simulate', json={'type': 'payment_failure', 'order_id': 'ORD_TEST'})
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['simulated'] is True
        assert 'case' in data

    def test_simulate_invalid_type(self, client):
        resp = client.post('/api/v1/exceptions/simulate', json={'type': 'invalid_type'})
        assert resp.status_code == 400

    def test_resolve_case(self, client):
        # simulate먼저
        resp = client.post('/api/v1/exceptions/simulate', json={'type': 'payment_failure'})
        case_id = resp.get_json()['case']['case_id']
        # resolve
        resp2 = client.post(f'/api/v1/exceptions/cases/{case_id}/resolve', json={'resolution': '처리 완료'})
        assert resp2.status_code == 200

    def test_escalate_case(self, client):
        resp = client.post('/api/v1/exceptions/simulate', json={'type': 'delivery_delay'})
        case_id = resp.get_json()['case']['case_id']
        resp2 = client.post(f'/api/v1/exceptions/cases/{case_id}/escalate', json={'reason': '수동 필요'})
        assert resp2.status_code == 200

    def test_retry_case(self, client):
        resp = client.post('/api/v1/exceptions/simulate', json={'type': 'payment_failure'})
        case_id = resp.get_json()['case']['case_id']
        resp2 = client.post(f'/api/v1/exceptions/cases/{case_id}/retry')
        assert resp2.status_code == 200

    def test_damage_report(self, client):
        resp = client.post('/api/v1/exceptions/damage/report', json={
            'order_id': 'ORD_DMG001',
            'damage_type': 'scratched',
            'grade': 'A',
            'item_price': 50000.0,
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert 'report' in data
        assert 'action' in data

    def test_damage_report_missing_fields(self, client):
        resp = client.post('/api/v1/exceptions/damage/report', json={'order_id': 'ORD001'})
        assert resp.status_code == 400

    def test_damage_report_invalid_type(self, client):
        resp = client.post('/api/v1/exceptions/damage/report', json={
            'order_id': 'ORD001', 'damage_type': 'invalid', 'grade': 'A',
        })
        assert resp.status_code == 400

    def test_get_damage_not_found(self, client):
        resp = client.get('/api/v1/exceptions/damage/nonexistent')
        assert resp.status_code == 404

    def test_list_price_alerts_empty(self, client):
        resp = client.get('/api/v1/exceptions/price-alerts')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['total'] == 0

    def test_configure_price_alerts(self, client):
        resp = client.post('/api/v1/exceptions/price-alerts/configure', json={
            'drop_threshold_pct': -15.0,
            'surge_threshold_pct': 15.0,
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['drop_threshold_pct'] == -15.0

    def test_list_retries_empty(self, client):
        resp = client.get('/api/v1/exceptions/retries')
        assert resp.status_code == 200

    def test_get_retry_not_found(self, client):
        resp = client.get('/api/v1/exceptions/retries/nonexistent')
        assert resp.status_code == 404

    def test_recovery_stats(self, client):
        resp = client.get('/api/v1/exceptions/recovery/stats')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'total_attempts' in data

    def test_dashboard(self, client):
        resp = client.get('/api/v1/exceptions/dashboard')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'summary' in data
        assert 'trend' in data
        assert 'cost_impact' in data
        assert 'resolution_metrics' in data

    def test_list_cases_filter_invalid_status(self, client):
        resp = client.get('/api/v1/exceptions/cases?status=invalid')
        assert resp.status_code == 400

    def test_list_cases_filter_invalid_type(self, client):
        resp = client.get('/api/v1/exceptions/cases?type=invalid')
        assert resp.status_code == 400

    def test_list_cases_filter_invalid_severity(self, client):
        resp = client.get('/api/v1/exceptions/cases?severity=invalid')
        assert resp.status_code == 400


# ─── 봇 커맨드 ────────────────────────────────────────────────────────────────

class TestExceptionBotCommands:
    def test_cmd_exceptions(self):
        from src.bot.commands import cmd_exceptions
        result = cmd_exceptions()
        assert isinstance(result, str)
        assert '예외' in result or 'exception' in result.lower() or '현황' in result

    def test_cmd_exception_detail_no_args(self):
        from src.bot.commands import cmd_exception_detail
        result = cmd_exception_detail('')
        assert '사용법' in result or 'error' in result.lower() or 'case_id' in result

    def test_cmd_exception_detail_not_found(self):
        from src.bot.commands import cmd_exception_detail
        result = cmd_exception_detail('nonexistent_case')
        assert isinstance(result, str)

    def test_cmd_price_alerts(self):
        from src.bot.commands import cmd_price_alerts
        result = cmd_price_alerts()
        assert isinstance(result, str)

    def test_cmd_retry_no_args(self):
        from src.bot.commands import cmd_retry
        result = cmd_retry('')
        assert '사용법' in result or 'error' in result.lower()

    def test_cmd_retry_not_found(self):
        from src.bot.commands import cmd_retry
        result = cmd_retry('nonexistent_case')
        assert isinstance(result, str)

    def test_cmd_exception_dashboard(self):
        from src.bot.commands import cmd_exception_dashboard
        result = cmd_exception_dashboard()
        assert isinstance(result, str)
        assert '대시보드' in result or 'dashboard' in result.lower()


# ─── 포맷터 ───────────────────────────────────────────────────────────────────

class TestExceptionFormatters:
    def test_format_exception_case(self):
        from src.bot.formatters import format_message
        data = {
            'case_id': 'exc_001',
            'type': 'payment_failure',
            'severity': 'high',
            'status': 'detected',
            'order_id': 'ORD001',
            'retry_count': 0,
        }
        result = format_message('exception_case', data)
        assert isinstance(result, str)
        assert 'exc_001' in result

    def test_format_exception_stats(self):
        from src.bot.formatters import format_message
        data = {
            'total': 10,
            'resolved': 8,
            'resolution_rate': 0.8,
            'by_severity': {'high': 5, 'medium': 5},
        }
        result = format_message('exception_stats', data)
        assert isinstance(result, str)
        assert '10' in result

    def test_format_damage_report(self):
        from src.bot.formatters import format_message
        data = {
            'report_id': 'dmg_001',
            'order_id': 'ORD001',
            'damage_type': 'scratched',
            'grade': 'A',
            'compensation_amount': 5000.0,
            'claim_sent': False,
        }
        result = format_message('damage_report', data)
        assert isinstance(result, str)
        assert 'dmg_001' in result

    def test_format_price_alert(self):
        from src.bot.formatters import format_message
        data = {
            'alert_id': 'pa_001',
            'product_id': 'PROD001',
            'old_price': 10000.0,
            'new_price': 8000.0,
            'change_percent': -20.0,
            'alert_type': 'price_drop',
        }
        result = format_message('price_alert', data)
        assert isinstance(result, str)
        assert 'PROD001' in result

    def test_format_retry_record(self):
        from src.bot.formatters import format_message
        data = {
            'record_id': 'retry_001',
            'task_type': 'payment',
            'status': 'succeeded',
            'attempt_count': 2,
        }
        result = format_message('retry_record', data)
        assert isinstance(result, str)
        assert 'payment' in result

    def test_format_exception_dashboard(self):
        from src.bot.formatters import format_message
        data = {
            'exceptions': {'total': 5, 'resolution_rate': 0.8},
            'recovery': {'success_rate': 0.9},
        }
        result = format_message('exception_dashboard', data)
        assert isinstance(result, str)

    def test_format_info_fallback(self):
        from src.bot.formatters import format_message
        result = format_message('info', '테스트 메시지')
        assert isinstance(result, str)


# ─── __init__ 임포트 ──────────────────────────────────────────────────────────

class TestExceptionHandlerPackage:
    def test_imports(self):
        from src.exception_handler import (
            ExceptionEngine, ExceptionCase, ExceptionType, ExceptionSeverity, ExceptionStatus,
            DamageHandler, DamageReport, DamageType, DamageGrade,
            PriceChangeDetector, PriceAlert, PriceAlertType,
            RetryManager, RetryPolicy, BackoffStrategy, RetryRecord, RetryStatus,
            AutoRecoveryService, RecoveryAction, ReorderAction, RefundAction,
            RerouteAction, EscalateAction, CompensateAction, RecoveryAttempt,
            DeliveryDelayHandler, DelayRecord, DelayStage, DelayAction,
            PaymentFailureHandler, PaymentFailureRecord, PaymentFailureReason, PaymentFailureStatus,
            ExceptionDashboard,
        )
        assert ExceptionEngine is not None
        assert DamageHandler is not None
        assert PriceChangeDetector is not None
        assert RetryManager is not None
        assert AutoRecoveryService is not None
        assert DeliveryDelayHandler is not None
        assert PaymentFailureHandler is not None
        assert ExceptionDashboard is not None

    def test_recovery_action_is_abstract(self):
        from src.exception_handler.auto_recovery import RecoveryAction
        with pytest.raises(TypeError):
            RecoveryAction()  # type: ignore[abstract]
