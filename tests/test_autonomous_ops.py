"""tests/test_autonomous_ops.py — Phase 106: 완전 자유 운영 대시보드 테스트."""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest


# ─── OperationMode ────────────────────────────────────────────────────────────

class TestOperationMode:
    def test_values(self):
        from src.autonomous_ops.engine import OperationMode
        assert OperationMode.fully_auto == 'fully_auto'
        assert OperationMode.semi_auto == 'semi_auto'
        assert OperationMode.manual == 'manual'
        assert OperationMode.emergency == 'emergency'

    def test_is_str(self):
        from src.autonomous_ops.engine import OperationMode
        assert isinstance(OperationMode.fully_auto, str)


# ─── OperationStatus ──────────────────────────────────────────────────────────

class TestOperationStatus:
    def _make(self):
        from src.autonomous_ops.engine import OperationStatus, OperationMode
        return OperationStatus(
            mode=OperationMode.fully_auto,
            health_score=95.0,
            active_alerts=2,
            auto_actions_count=10,
            last_check='2025-01-01T00:00:00+00:00',
            uptime_seconds=3600.0,
        )

    def test_to_dict_keys(self):
        s = self._make()
        d = s.to_dict()
        assert 'mode' in d
        assert 'health_score' in d
        assert 'active_alerts' in d
        assert 'auto_actions_count' in d
        assert 'last_check' in d
        assert 'uptime_seconds' in d

    def test_to_dict_values(self):
        s = self._make()
        d = s.to_dict()
        assert d['mode'] == 'fully_auto'
        assert d['health_score'] == 95.0
        assert d['active_alerts'] == 2
        assert d['auto_actions_count'] == 10


# ─── AutonomousOperationEngine ────────────────────────────────────────────────

class TestAutonomousOperationEngine:
    def _engine(self):
        from src.autonomous_ops.engine import AutonomousOperationEngine
        return AutonomousOperationEngine()

    def test_get_status_default(self):
        eng = self._engine()
        status = eng.get_status()
        assert status.mode.value == 'fully_auto'
        assert status.health_score == 100.0
        assert status.active_alerts == 0
        assert status.auto_actions_count == 0

    def test_get_status_to_dict(self):
        eng = self._engine()
        d = eng.get_status().to_dict()
        assert isinstance(d, dict)
        assert 'mode' in d

    def test_set_mode(self):
        from src.autonomous_ops.engine import OperationMode
        eng = self._engine()
        status = eng.set_mode(OperationMode.manual)
        assert status.mode == OperationMode.manual

    def test_set_mode_emergency(self):
        from src.autonomous_ops.engine import OperationMode
        eng = self._engine()
        status = eng.set_mode(OperationMode.emergency)
        assert status.mode.value == 'emergency'

    def test_run_health_check(self):
        eng = self._engine()
        result = eng.run_health_check()
        assert 'score' in result
        assert 'operation_mode' in result
        assert isinstance(result['score'], float)

    def test_record_alert(self):
        eng = self._engine()
        eng.record_alert('alert_001')
        assert 'alert_001' in eng.get_alerts()

    def test_record_alert_deduplication(self):
        eng = self._engine()
        eng.record_alert('alert_dup')
        eng.record_alert('alert_dup')
        assert eng.get_alerts().count('alert_dup') == 1

    def test_acknowledge_alert_found(self):
        eng = self._engine()
        eng.record_alert('alert_x')
        result = eng.acknowledge_alert('alert_x')
        assert result is True
        assert 'alert_x' not in eng.get_alerts()

    def test_acknowledge_alert_not_found(self):
        eng = self._engine()
        result = eng.acknowledge_alert('nonexistent')
        assert result is False

    def test_record_auto_action(self):
        eng = self._engine()
        eng.record_auto_action()
        eng.record_auto_action()
        assert eng.get_status().auto_actions_count == 2

    def test_get_alerts_empty(self):
        eng = self._engine()
        assert eng.get_alerts() == []

    def test_auto_switch_mode_fully_auto(self):
        from src.autonomous_ops.engine import OperationMode
        eng = self._engine()
        mode = eng.auto_switch_mode(90.0)
        assert mode == OperationMode.fully_auto

    def test_auto_switch_mode_semi_auto(self):
        from src.autonomous_ops.engine import OperationMode
        eng = self._engine()
        mode = eng.auto_switch_mode(70.0)
        assert mode == OperationMode.semi_auto

    def test_auto_switch_mode_manual(self):
        from src.autonomous_ops.engine import OperationMode
        eng = self._engine()
        mode = eng.auto_switch_mode(50.0)
        assert mode == OperationMode.manual

    def test_auto_switch_mode_emergency(self):
        from src.autonomous_ops.engine import OperationMode
        eng = self._engine()
        mode = eng.auto_switch_mode(20.0)
        assert mode == OperationMode.emergency

    def test_auto_switch_mode_boundary_80(self):
        from src.autonomous_ops.engine import OperationMode
        eng = self._engine()
        mode = eng.auto_switch_mode(80.0)
        assert mode == OperationMode.fully_auto

    def test_uptime_non_negative(self):
        import time
        from src.autonomous_ops.engine import AutonomousOperationEngine
        eng = AutonomousOperationEngine()
        time.sleep(0.01)
        assert eng.get_status().uptime_seconds >= 0


# ─── RevenueStream ────────────────────────────────────────────────────────────

class TestRevenueStream:
    def test_values(self):
        from src.autonomous_ops.revenue_model import RevenueStream
        assert RevenueStream.proxy_buy == 'proxy_buy'
        assert RevenueStream.import_ == 'import_'
        assert RevenueStream.export == 'export'
        assert RevenueStream.commission == 'commission'
        assert RevenueStream.service_fee == 'service_fee'

    def test_is_str(self):
        from src.autonomous_ops.revenue_model import RevenueStream
        assert isinstance(RevenueStream.export, str)


# ─── RevenueRecord ────────────────────────────────────────────────────────────

class TestRevenueRecord:
    def _make(self):
        from src.autonomous_ops.revenue_model import RevenueRecord, RevenueStream
        return RevenueRecord(
            record_id='rev_abc123',
            stream=RevenueStream.proxy_buy,
            amount=100000.0,
            cost=70000.0,
            currency='KRW',
            timestamp='2025-01-01T00:00:00+00:00',
            metadata={'channel': 'web'},
        )

    def test_to_dict_keys(self):
        r = self._make()
        d = r.to_dict()
        for k in ['record_id', 'stream', 'amount', 'cost', 'currency', 'timestamp', 'metadata']:
            assert k in d

    def test_to_dict_stream_value(self):
        r = self._make()
        assert r.to_dict()['stream'] == 'proxy_buy'

    def test_to_dict_metadata(self):
        r = self._make()
        assert r.to_dict()['metadata']['channel'] == 'web'


# ─── CostBreakdown ────────────────────────────────────────────────────────────

class TestCostBreakdown:
    def _make(self):
        from src.autonomous_ops.revenue_model import CostBreakdown
        return CostBreakdown(
            product_cost=60000,
            shipping=10000,
            customs=5000,
            commission=3000,
            operation=2000,
            fx_loss=1000,
        )

    def test_total_property(self):
        cb = self._make()
        assert cb.total == 81000

    def test_to_dict_keys(self):
        d = self._make().to_dict()
        for k in ['product_cost', 'shipping', 'customs', 'commission', 'operation', 'fx_loss', 'total']:
            assert k in d

    def test_to_dict_total_matches(self):
        cb = self._make()
        d = cb.to_dict()
        assert d['total'] == cb.total

    def test_default_zero(self):
        from src.autonomous_ops.revenue_model import CostBreakdown
        cb = CostBreakdown()
        assert cb.total == 0.0


# ─── RevenueTracker ──────────────────────────────────────────────────────────

class TestRevenueTracker:
    def _tracker(self):
        from src.autonomous_ops.revenue_model import RevenueTracker
        return RevenueTracker()

    def test_add_record_returns_record(self):
        from src.autonomous_ops.revenue_model import RevenueStream
        t = self._tracker()
        r = t.add_record(RevenueStream.proxy_buy, 50000, 30000)
        assert r.record_id.startswith('rev_')
        assert r.amount == 50000
        assert r.cost == 30000

    def test_add_record_default_currency(self):
        from src.autonomous_ops.revenue_model import RevenueStream
        t = self._tracker()
        r = t.add_record(RevenueStream.export, 100000, 50000)
        assert r.currency == 'KRW'

    def test_add_record_custom_currency(self):
        from src.autonomous_ops.revenue_model import RevenueStream
        t = self._tracker()
        r = t.add_record(RevenueStream.export, 100, 50, currency='USD')
        assert r.currency == 'USD'

    def test_add_record_with_metadata(self):
        from src.autonomous_ops.revenue_model import RevenueStream
        t = self._tracker()
        r = t.add_record(RevenueStream.commission, 5000, 0, metadata={'source': 'api'})
        assert r.metadata['source'] == 'api'

    def test_get_daily_revenue_empty(self):
        t = self._tracker()
        daily = t.get_daily_revenue()
        assert isinstance(daily, dict)
        assert all(v == 0.0 for v in daily.values())

    def test_get_daily_revenue_today(self):
        from src.autonomous_ops.revenue_model import RevenueStream
        t = self._tracker()
        t.add_record(RevenueStream.proxy_buy, 50000, 30000)
        daily = t.get_daily_revenue()
        assert daily['proxy_buy'] == 50000

    def test_get_weekly_summary(self):
        from src.autonomous_ops.revenue_model import RevenueStream
        t = self._tracker()
        t.add_record(RevenueStream.export, 200000, 120000)
        summary = t.get_weekly_summary()
        assert 'total_revenue' in summary
        assert 'total_cost' in summary
        assert 'net' in summary
        assert summary['total_revenue'] == 200000

    def test_get_monthly_summary(self):
        from src.autonomous_ops.revenue_model import RevenueStream
        t = self._tracker()
        t.add_record(RevenueStream.service_fee, 10000, 0)
        summary = t.get_monthly_summary()
        assert summary['period_days'] == 30
        assert summary['total_revenue'] == 10000

    def test_list_records_empty(self):
        t = self._tracker()
        assert t.list_records() == []

    def test_list_records_limit(self):
        from src.autonomous_ops.revenue_model import RevenueStream
        t = self._tracker()
        for i in range(5):
            t.add_record(RevenueStream.commission, float(i * 1000), 0)
        records = t.list_records(limit=3)
        assert len(records) == 3

    def test_list_records_returns_dicts(self):
        from src.autonomous_ops.revenue_model import RevenueStream
        t = self._tracker()
        t.add_record(RevenueStream.proxy_buy, 1000, 500)
        records = t.list_records()
        assert isinstance(records[0], dict)
        assert 'record_id' in records[0]


# ─── ProfitCalculator ────────────────────────────────────────────────────────

class TestProfitCalculator:
    def _calc(self):
        from src.autonomous_ops.revenue_model import ProfitCalculator
        return ProfitCalculator()

    def test_calculate_basic(self):
        from src.autonomous_ops.revenue_model import CostBreakdown
        calc = self._calc()
        cb = CostBreakdown(product_cost=70000)
        result = calc.calculate(100000, cb)
        assert result['net_profit'] == 30000
        assert result['revenue'] == 100000

    def test_calculate_includes_margin(self):
        from src.autonomous_ops.revenue_model import CostBreakdown
        calc = self._calc()
        cb = CostBreakdown(product_cost=50000)
        result = calc.calculate(100000, cb)
        assert result['margin_rate'] == 0.5

    def test_calculate_margin_zero_revenue(self):
        calc = self._calc()
        assert calc.calculate_margin(0, 100) == 0.0

    def test_calculate_margin_positive(self):
        calc = self._calc()
        margin = calc.calculate_margin(200000, 150000)
        assert abs(margin - 0.25) < 0.0001

    def test_calculate_breakdown_included(self):
        from src.autonomous_ops.revenue_model import CostBreakdown
        calc = self._calc()
        cb = CostBreakdown(shipping=5000)
        result = calc.calculate(50000, cb)
        assert 'cost_breakdown' in result


# ─── MarginAnalyzer ──────────────────────────────────────────────────────────

class TestMarginAnalyzer:
    def test_analyze_by_stream_empty(self):
        from src.autonomous_ops.revenue_model import MarginAnalyzer
        a = MarginAnalyzer()
        result = a.analyze_by_stream([])
        assert result == {}

    def test_analyze_by_stream_with_records(self):
        from src.autonomous_ops.revenue_model import MarginAnalyzer, RevenueRecord, RevenueStream
        a = MarginAnalyzer()
        records = [
            RevenueRecord('r1', RevenueStream.proxy_buy, 100000, 60000, 'KRW', '2025-01-01T00:00:00+00:00'),
            RevenueRecord('r2', RevenueStream.proxy_buy, 50000, 30000, 'KRW', '2025-01-01T00:00:00+00:00'),
        ]
        result = a.analyze_by_stream(records)
        assert 'proxy_buy' in result
        assert result['proxy_buy']['revenue'] == 150000
        assert result['proxy_buy']['cost'] == 90000

    def test_analyze_by_stream_margin_rate(self):
        from src.autonomous_ops.revenue_model import MarginAnalyzer, RevenueRecord, RevenueStream
        a = MarginAnalyzer()
        records = [
            RevenueRecord('r1', RevenueStream.export, 100000, 50000, 'KRW', '2025-01-01T00:00:00+00:00'),
        ]
        result = a.analyze_by_stream(records)
        assert result['export']['margin_rate'] == 0.5

    def test_analyze_by_channel_empty(self):
        from src.autonomous_ops.revenue_model import MarginAnalyzer
        a = MarginAnalyzer()
        result = a.analyze_by_channel([])
        assert result == {}

    def test_analyze_by_channel_default(self):
        from src.autonomous_ops.revenue_model import MarginAnalyzer, RevenueRecord, RevenueStream
        a = MarginAnalyzer()
        records = [
            RevenueRecord('r1', RevenueStream.service_fee, 10000, 5000, 'KRW', '2025-01-01T00:00:00+00:00',
                          metadata={'channel': 'mobile'}),
        ]
        result = a.analyze_by_channel(records)
        assert 'mobile' in result


# ─── RevenueForecaster ────────────────────────────────────────────────────────

class TestRevenueForecaster:
    def _f(self):
        from src.autonomous_ops.revenue_model import RevenueForecaster
        return RevenueForecaster()

    def test_forecast_empty_returns_zeros(self):
        f = self._f()
        result = f.forecast_next_period([], periods=3)
        assert result == [0.0, 0.0, 0.0]

    def test_forecast_length(self):
        f = self._f()
        result = f.forecast_next_period([1000, 2000, 3000], periods=5)
        assert len(result) == 5

    def test_forecast_moving_average(self):
        f = self._f()
        data = [1000.0, 1000.0, 1000.0]
        result = f.forecast_next_period(data, periods=3)
        assert all(v == 1000.0 for v in result)

    def test_forecast_single_value(self):
        f = self._f()
        result = f.forecast_next_period([5000.0], periods=7)
        assert len(result) == 7
        assert all(v == 5000.0 for v in result)


# ─── AnomalyType ─────────────────────────────────────────────────────────────

class TestAnomalyType:
    def test_values(self):
        from src.autonomous_ops.anomaly_detector import AnomalyType
        assert AnomalyType.revenue_drop == 'revenue_drop'
        assert AnomalyType.cost_spike == 'cost_spike'
        assert AnomalyType.order_surge == 'order_surge'
        assert AnomalyType.order_drought == 'order_drought'
        assert AnomalyType.conversion_drop == 'conversion_drop'
        assert AnomalyType.refund_spike == 'refund_spike'
        assert AnomalyType.delivery_delay_spike == 'delivery_delay_spike'
        assert AnomalyType.seller_issue == 'seller_issue'
        assert AnomalyType.system_error == 'system_error'


# ─── AnomalyAlert ────────────────────────────────────────────────────────────

class TestAnomalyAlert:
    def _make(self):
        from src.autonomous_ops.anomaly_detector import AnomalyAlert, AnomalyType, AnomalySeverity
        return AnomalyAlert(
            alert_id='ano_test001',
            type=AnomalyType.revenue_drop,
            severity=AnomalySeverity.high,
            metric_name='daily_revenue',
            expected_value=100000.0,
            actual_value=60000.0,
            deviation_percent=40.0,
            detected_at='2025-01-01T00:00:00+00:00',
        )

    def test_to_dict_keys(self):
        a = self._make()
        d = a.to_dict()
        for k in ['alert_id', 'type', 'severity', 'metric_name', 'expected_value', 'actual_value',
                  'deviation_percent', 'detected_at', 'acknowledged', 'consecutive_count', 'metadata']:
            assert k in d

    def test_to_dict_type_value(self):
        a = self._make()
        assert a.to_dict()['type'] == 'revenue_drop'

    def test_default_acknowledged_false(self):
        a = self._make()
        assert a.acknowledged is False

    def test_default_consecutive_count(self):
        a = self._make()
        assert a.consecutive_count == 1


# ─── AnomalyDetector ─────────────────────────────────────────────────────────

class TestAnomalyDetector:
    def _det(self):
        from src.autonomous_ops.anomaly_detector import AnomalyDetector
        return AnomalyDetector()

    def test_add_metric_value(self):
        d = self._det()
        d.add_metric_value('revenue', 100000)
        d.add_metric_value('revenue', 110000)
        assert len(d._metric_history['revenue']) == 2

    def test_check_metric_no_history(self):
        from src.autonomous_ops.anomaly_detector import AnomalyType
        d = self._det()
        result = d.check_metric('new_metric', 100, AnomalyType.revenue_drop)
        assert result is None

    def test_check_metric_no_anomaly(self):
        from src.autonomous_ops.anomaly_detector import AnomalyType
        d = self._det()
        for v in [100, 102, 98, 101, 99]:
            d.add_metric_value('stable', float(v))
        result = d.check_metric('stable', 100.0, AnomalyType.revenue_drop)
        assert result is None

    def test_check_metric_detects_anomaly(self):
        from src.autonomous_ops.anomaly_detector import AnomalyType
        d = self._det()
        # Use values with some variance so std != 0
        for v in [100, 102, 98, 101, 99, 100, 103]:
            d.add_metric_value('revenue', float(v))
        result = d.check_metric('revenue', 1000.0, AnomalyType.revenue_drop)
        assert result is not None
        assert result.alert_id.startswith('ano_')

    def test_check_metric_saved_to_alerts(self):
        from src.autonomous_ops.anomaly_detector import AnomalyType
        d = self._det()
        for v in [100, 100, 100, 100]:
            d.add_metric_value('m', float(v))
        alert = d.check_metric('m', 500.0, AnomalyType.cost_spike)
        if alert:
            assert any(a['alert_id'] == alert.alert_id for a in d.list_alerts())

    def test_check_change_rate_no_anomaly(self):
        from src.autonomous_ops.anomaly_detector import AnomalyType
        d = self._det()
        result = d.check_change_rate('rev', 110.0, 100.0, AnomalyType.revenue_drop)
        assert result is None

    def test_check_change_rate_detects_anomaly(self):
        from src.autonomous_ops.anomaly_detector import AnomalyType
        d = self._det()
        result = d.check_change_rate('rev', 200.0, 100.0, AnomalyType.order_surge)
        assert result is not None
        assert result.deviation_percent >= 100.0

    def test_check_change_rate_zero_previous(self):
        from src.autonomous_ops.anomaly_detector import AnomalyType
        d = self._det()
        result = d.check_change_rate('rev', 100.0, 0.0, AnomalyType.revenue_drop)
        assert result is None

    def test_check_threshold_above(self):
        from src.autonomous_ops.anomaly_detector import AnomalyType
        d = self._det()
        result = d.check_threshold('refund_rate', 0.5, 0.3, AnomalyType.refund_spike, above=True)
        assert result is not None

    def test_check_threshold_below(self):
        from src.autonomous_ops.anomaly_detector import AnomalyType
        d = self._det()
        result = d.check_threshold('conversion', 0.01, 0.05, AnomalyType.conversion_drop, above=False)
        assert result is not None

    def test_check_threshold_not_triggered(self):
        from src.autonomous_ops.anomaly_detector import AnomalyType
        d = self._det()
        result = d.check_threshold('refund_rate', 0.1, 0.3, AnomalyType.refund_spike, above=True)
        assert result is None

    def test_acknowledge_existing(self):
        from src.autonomous_ops.anomaly_detector import AnomalyType
        d = self._det()
        alert = d.check_threshold('x', 100, 50, AnomalyType.cost_spike, above=True)
        assert alert is not None
        ok = d.acknowledge(alert.alert_id)
        assert ok is True

    def test_acknowledge_nonexistent(self):
        d = self._det()
        assert d.acknowledge('nonexistent_id') is False

    def test_get_active_alerts(self):
        from src.autonomous_ops.anomaly_detector import AnomalyType
        d = self._det()
        d.check_threshold('y', 200, 100, AnomalyType.order_surge, above=True)
        active = d.get_active_alerts()
        assert len(active) == 1
        assert active[0]['acknowledged'] is False

    def test_get_active_alerts_excludes_acknowledged(self):
        from src.autonomous_ops.anomaly_detector import AnomalyType
        d = self._det()
        alert = d.check_threshold('z', 200, 100, AnomalyType.system_error, above=True)
        d.acknowledge(alert.alert_id)
        active = d.get_active_alerts()
        assert len(active) == 0

    def test_list_alerts_all(self):
        from src.autonomous_ops.anomaly_detector import AnomalyType
        d = self._det()
        d.check_threshold('a', 200, 100, AnomalyType.cost_spike, above=True)
        alert2 = d.check_threshold('b', 200, 100, AnomalyType.order_surge, above=True)
        d.acknowledge(alert2.alert_id)
        all_alerts = d.list_alerts()
        assert len(all_alerts) == 2

    def test_list_alerts_filter_acknowledged_false(self):
        from src.autonomous_ops.anomaly_detector import AnomalyType
        d = self._det()
        d.check_threshold('a', 200, 100, AnomalyType.cost_spike, above=True)
        alerts = d.list_alerts(acknowledged=False)
        assert all(not a['acknowledged'] for a in alerts)

    def test_determine_severity_low(self):
        d = self._det()
        from src.autonomous_ops.anomaly_detector import AnomalySeverity
        assert d._determine_severity(30.0) == AnomalySeverity.low

    def test_determine_severity_medium(self):
        d = self._det()
        from src.autonomous_ops.anomaly_detector import AnomalySeverity
        assert d._determine_severity(75.0) == AnomalySeverity.medium

    def test_determine_severity_high(self):
        d = self._det()
        from src.autonomous_ops.anomaly_detector import AnomalySeverity
        assert d._determine_severity(150.0) == AnomalySeverity.high

    def test_determine_severity_critical(self):
        d = self._det()
        from src.autonomous_ops.anomaly_detector import AnomalySeverity
        assert d._determine_severity(300.0) == AnomalySeverity.critical

    def test_calculate_moving_avg_std(self):
        d = self._det()
        avg, std = d._calculate_moving_avg_std([10.0, 20.0, 30.0])
        assert abs(avg - 20.0) < 0.001
        assert std > 0

    def test_calculate_moving_avg_std_empty(self):
        d = self._det()
        avg, std = d._calculate_moving_avg_std([])
        assert avg == 0.0
        assert std == 0.0


# ─── ActionRecord ────────────────────────────────────────────────────────────

class TestActionRecord:
    def _make(self):
        from src.autonomous_ops.autopilot import ActionRecord, ActionStatus
        return ActionRecord(
            action_id='act_001',
            action_type='pause_ordering',
            trigger_alert_id='ano_001',
            status=ActionStatus.completed,
            started_at='2025-01-01T00:00:00+00:00',
            completed_at='2025-01-01T00:00:01+00:00',
            result={'paused': True},
        )

    def test_to_dict_keys(self):
        r = self._make()
        d = r.to_dict()
        for k in ['action_id', 'action_type', 'trigger_alert_id', 'status', 'started_at', 'completed_at', 'result', 'metadata']:
            assert k in d

    def test_to_dict_status_value(self):
        r = self._make()
        assert r.to_dict()['status'] == 'completed'


# ─── AutoActions ─────────────────────────────────────────────────────────────

class TestAutoActions:
    def _alert(self):
        from src.autonomous_ops.anomaly_detector import AnomalyAlert, AnomalyType, AnomalySeverity
        return AnomalyAlert(
            alert_id='ano_test', type=AnomalyType.revenue_drop,
            severity=AnomalySeverity.high, metric_name='rev',
            expected_value=100, actual_value=50, deviation_percent=50,
            detected_at='2025-01-01T00:00:00+00:00',
        )

    def test_pause_ordering_action(self):
        from src.autonomous_ops.autopilot import PauseOrderingAction
        action = PauseOrderingAction()
        assert action.action_type == 'pause_ordering'
        result = action.execute(self._alert(), {})
        assert result['paused'] is True
        assert 'reason' in result

    def test_adjust_pricing_action(self):
        from src.autonomous_ops.autopilot import AdjustPricingAction
        action = AdjustPricingAction()
        assert action.action_type == 'adjust_pricing'
        result = action.execute(self._alert(), {})
        assert result['adjusted'] is True
        assert 'adjustment_pct' in result

    def test_scale_inventory_action(self):
        from src.autonomous_ops.autopilot import ScaleInventoryAction
        action = ScaleInventoryAction()
        assert action.action_type == 'scale_inventory'
        result = action.execute(self._alert(), {})
        assert result['scaled'] is True
        assert result['scale_factor'] == 1.5

    def test_notify_admin_action(self):
        from src.autonomous_ops.autopilot import NotifyAdminAction
        action = NotifyAdminAction()
        assert action.action_type == 'notify_admin'
        result = action.execute(self._alert(), {})
        assert result['notified'] is True
        assert 'channels' in result

    def test_activate_backup_action(self):
        from src.autonomous_ops.autopilot import ActivateBackupAction
        action = ActivateBackupAction()
        assert action.action_type == 'activate_backup'
        result = action.execute(self._alert(), {})
        assert result['backup_activated'] is True


# ─── AutoPilotController ─────────────────────────────────────────────────────

class TestAutoPilotController:
    def _controller(self):
        from src.autonomous_ops.autopilot import AutoPilotController
        return AutoPilotController()

    def _alert(self, atype='revenue_drop'):
        from src.autonomous_ops.anomaly_detector import AnomalyAlert, AnomalyType, AnomalySeverity
        return AnomalyAlert(
            alert_id='ano_ctrl', type=AnomalyType(atype),
            severity=AnomalySeverity.medium, metric_name='rev',
            expected_value=100, actual_value=70, deviation_percent=30,
            detected_at='2025-01-01T00:00:00+00:00',
        )

    def test_register_action(self):
        from src.autonomous_ops.autopilot import AutoPilotController, PauseOrderingAction
        ctrl = AutoPilotController()
        ctrl.register_action(PauseOrderingAction())
        assert 'pause_ordering' in ctrl._actions

    def test_respond_to_alert_returns_record(self):
        ctrl = self._controller()
        record = ctrl.respond_to_alert(self._alert())
        assert record.action_id.startswith('act_')

    def test_respond_to_alert_completed(self):
        from src.autonomous_ops.autopilot import ActionStatus
        ctrl = self._controller()
        record = ctrl.respond_to_alert(self._alert())
        assert record.status == ActionStatus.completed

    def test_respond_to_alert_cost_spike(self):
        ctrl = self._controller()
        record = ctrl.respond_to_alert(self._alert('cost_spike'))
        assert record.action_type == 'pause_ordering'

    def test_respond_to_alert_seller_issue(self):
        ctrl = self._controller()
        record = ctrl.respond_to_alert(self._alert('seller_issue'))
        assert record.action_type == 'activate_backup'

    def test_respond_to_alert_order_surge(self):
        ctrl = self._controller()
        record = ctrl.respond_to_alert(self._alert('order_surge'))
        assert record.action_type == 'scale_inventory'

    def test_get_history_empty(self):
        ctrl = self._controller()
        assert ctrl.get_history() == []

    def test_get_history_after_action(self):
        ctrl = self._controller()
        ctrl.respond_to_alert(self._alert())
        history = ctrl.get_history()
        assert len(history) == 1
        assert isinstance(history[0], dict)

    def test_get_history_limit(self):
        ctrl = self._controller()
        for _ in range(10):
            ctrl.respond_to_alert(self._alert())
        history = ctrl.get_history(limit=3)
        assert len(history) == 3

    def test_get_stats(self):
        ctrl = self._controller()
        ctrl.respond_to_alert(self._alert())
        stats = ctrl.get_stats()
        assert 'total' in stats
        assert 'by_status' in stats
        assert 'success_rate' in stats
        assert stats['total'] == 1

    def test_get_stats_success_rate(self):
        from src.autonomous_ops.autopilot import ActionStatus
        ctrl = self._controller()
        ctrl.respond_to_alert(self._alert())
        stats = ctrl.get_stats()
        assert stats['success_rate'] == 1.0


# ─── ManualTask ──────────────────────────────────────────────────────────────

class TestManualTask:
    def _make(self):
        from src.autonomous_ops.intervention import ManualTask, TaskPriority
        return ManualTask(
            task_id='tsk_001',
            description='수동 처리 필요',
            priority=TaskPriority.high,
            reason='자동화 불가',
            created_at='2025-01-01T00:00:00+00:00',
        )

    def test_to_dict_keys(self):
        t = self._make()
        d = t.to_dict()
        for k in ['task_id', 'description', 'priority', 'reason', 'created_at', 'resolved_at', 'resolved']:
            assert k in d

    def test_to_dict_priority_value(self):
        t = self._make()
        assert t.to_dict()['priority'] == 'high'

    def test_default_not_resolved(self):
        t = self._make()
        assert t.resolved is False
        assert t.resolved_at is None


# ─── InterventionTracker ─────────────────────────────────────────────────────

class TestInterventionTracker:
    def _tracker(self):
        from src.autonomous_ops.intervention import InterventionTracker
        return InterventionTracker()

    def test_record_intervention(self):
        t = self._tracker()
        record = t.record_intervention('manual needed', 'tsk_001')
        assert record.record_id.startswith('int_')
        assert record.reason == 'manual needed'

    def test_record_intervention_increments(self):
        t = self._tracker()
        t.record_intervention('r1')
        t.record_intervention('r2')
        assert len(t._records) == 2

    def test_record_auto_handled(self):
        t = self._tracker()
        t.record_auto_handled()
        t.record_auto_handled()
        assert t._auto_handled == 2

    def test_get_automation_coverage_zero(self):
        t = self._tracker()
        assert t.get_automation_coverage() == 0.0

    def test_get_automation_coverage(self):
        t = self._tracker()
        t.record_auto_handled()
        t.record_auto_handled()
        t.record_auto_handled()
        t.record_intervention('reason')
        coverage = t.get_automation_coverage()
        assert abs(coverage - 0.75) < 0.001

    def test_get_stats(self):
        t = self._tracker()
        t.record_auto_handled()
        t.record_intervention('r')
        stats = t.get_stats()
        assert 'automation_coverage' in stats
        assert 'auto_handled' in stats
        assert 'manual_interventions' in stats

    def test_intervention_record_to_dict(self):
        t = self._tracker()
        record = t.record_intervention('test reason', 'tsk_x')
        d = record.to_dict()
        assert d['reason'] == 'test reason'
        assert d['task_id'] == 'tsk_x'


# ─── ManualTaskQueue ─────────────────────────────────────────────────────────

class TestManualTaskQueue:
    def _queue(self):
        from src.autonomous_ops.intervention import ManualTaskQueue
        return ManualTaskQueue()

    def test_add_task_returns_task(self):
        from src.autonomous_ops.intervention import TaskPriority
        q = self._queue()
        task = q.add_task('Handle refund', TaskPriority.high, 'Needs manual review')
        assert task.task_id.startswith('tsk_')
        assert task.description == 'Handle refund'

    def test_resolve_task(self):
        from src.autonomous_ops.intervention import TaskPriority
        q = self._queue()
        task = q.add_task('Task to resolve', TaskPriority.medium, 'reason')
        result = q.resolve_task(task.task_id)
        assert result is True
        assert task.resolved is True

    def test_resolve_task_not_found(self):
        q = self._queue()
        result = q.resolve_task('nonexistent_id')
        assert result is False

    def test_list_pending_excludes_resolved(self):
        from src.autonomous_ops.intervention import TaskPriority
        q = self._queue()
        t1 = q.add_task('t1', TaskPriority.low, 'r')
        t2 = q.add_task('t2', TaskPriority.high, 'r')
        q.resolve_task(t1.task_id)
        pending = q.list_pending()
        assert len(pending) == 1
        assert pending[0]['task_id'] == t2.task_id

    def test_list_pending_sorted_by_priority(self):
        from src.autonomous_ops.intervention import TaskPriority
        q = self._queue()
        q.add_task('low task', TaskPriority.low, 'r')
        q.add_task('critical task', TaskPriority.critical, 'r')
        q.add_task('medium task', TaskPriority.medium, 'r')
        pending = q.list_pending()
        assert pending[0]['priority'] == 'critical'
        assert pending[1]['priority'] == 'medium'
        assert pending[2]['priority'] == 'low'

    def test_list_pending_limit(self):
        from src.autonomous_ops.intervention import TaskPriority
        q = self._queue()
        for i in range(10):
            q.add_task(f'task_{i}', TaskPriority.low, 'r')
        pending = q.list_pending(limit=3)
        assert len(pending) == 3

    def test_get_stats(self):
        from src.autonomous_ops.intervention import TaskPriority
        q = self._queue()
        q.add_task('t1', TaskPriority.high, 'r')
        t2 = q.add_task('t2', TaskPriority.low, 'r')
        q.resolve_task(t2.task_id)
        stats = q.get_stats()
        assert stats['total'] == 2
        assert stats['resolved'] == 1
        assert stats['pending'] == 1


# ─── AutomationCoverage ──────────────────────────────────────────────────────

class TestAutomationCoverage:
    def _ac(self):
        from src.autonomous_ops.intervention import AutomationCoverage
        return AutomationCoverage()

    def test_calculate_keys(self):
        ac = self._ac()
        result = ac.calculate(95, 5)
        for k in ['coverage_rate', 'auto', 'manual', 'total', 'target_reached']:
            assert k in result

    def test_calculate_values(self):
        ac = self._ac()
        result = ac.calculate(95, 5)
        assert result['auto'] == 95
        assert result['manual'] == 5
        assert result['total'] == 100
        assert abs(result['coverage_rate'] - 0.95) < 0.0001

    def test_calculate_target_reached(self):
        ac = self._ac()
        result = ac.calculate(95, 5)
        assert result['target_reached'] is True

    def test_calculate_target_not_reached(self):
        ac = self._ac()
        result = ac.calculate(50, 50)
        assert result['target_reached'] is False

    def test_calculate_zero_total(self):
        ac = self._ac()
        result = ac.calculate(0, 0)
        assert result['coverage_rate'] == 0.0
        assert result['total'] == 0


# ─── InterventionReport ──────────────────────────────────────────────────────

class TestInterventionReport:
    def test_generate(self):
        from src.autonomous_ops.intervention import InterventionReport, InterventionTracker, ManualTaskQueue
        report = InterventionReport()
        tracker = InterventionTracker()
        queue = ManualTaskQueue()
        result = report.generate(tracker, queue)
        assert 'tracker' in result
        assert 'queue' in result
        assert 'automation_coverage' in result
        assert 'improvement_suggestions' in result

    def test_generate_suggestion_low_coverage(self):
        from src.autonomous_ops.intervention import InterventionReport, InterventionTracker, ManualTaskQueue
        report = InterventionReport()
        tracker = InterventionTracker()
        tracker.record_intervention('reason')
        queue = ManualTaskQueue()
        result = report.generate(tracker, queue)
        assert len(result['improvement_suggestions']) > 0

    def test_generate_target_reached(self):
        from src.autonomous_ops.intervention import InterventionReport, InterventionTracker, ManualTaskQueue
        report = InterventionReport()
        tracker = InterventionTracker()
        for _ in range(100):
            tracker.record_auto_handled()
        queue = ManualTaskQueue()
        result = report.generate(tracker, queue)
        assert result['target_reached'] is True


# ─── Scenario ────────────────────────────────────────────────────────────────

class TestScenario:
    def _make(self):
        from src.autonomous_ops.simulation import Scenario, ScenarioType
        return Scenario(
            scenario_id='scn_001',
            name='가격 폭락 시나리오',
            type=ScenarioType.price_crash,
            parameters={'crash_pct': -30},
            duration_hours=24.0,
            created_at='2025-01-01T00:00:00+00:00',
        )

    def test_to_dict_keys(self):
        s = self._make()
        d = s.to_dict()
        for k in ['scenario_id', 'name', 'type', 'parameters', 'duration_hours', 'created_at']:
            assert k in d

    def test_to_dict_type_value(self):
        s = self._make()
        assert s.to_dict()['type'] == 'price_crash'


# ─── SimulationResult ────────────────────────────────────────────────────────

class TestSimulationResult:
    def _make(self):
        from src.autonomous_ops.simulation import SimulationResult, SimulationStatus
        return SimulationResult(
            result_id='res_001',
            scenario_id='scn_001',
            status=SimulationStatus.completed,
            revenue_impact=-200000.0,
            cost_impact=0.0,
            order_impact=10,
            risk_score=60.0,
            recommendations=['전략 수립'],
            completed_at='2025-01-01T00:00:00+00:00',
        )

    def test_to_dict_keys(self):
        r = self._make()
        d = r.to_dict()
        for k in ['result_id', 'scenario_id', 'status', 'revenue_impact', 'cost_impact',
                  'order_impact', 'risk_score', 'recommendations', 'completed_at']:
            assert k in d

    def test_to_dict_status_value(self):
        r = self._make()
        assert r.to_dict()['status'] == 'completed'


# ─── SimulationEngine ────────────────────────────────────────────────────────

class TestSimulationEngine:
    def _engine(self):
        from src.autonomous_ops.simulation import SimulationEngine
        return SimulationEngine()

    def test_create_scenario(self):
        from src.autonomous_ops.simulation import ScenarioType
        eng = self._engine()
        sc = eng.create_scenario('test', ScenarioType.price_crash, {'crash_pct': -20})
        assert sc.scenario_id.startswith('scn_')
        assert sc.type == ScenarioType.price_crash

    def test_create_scenario_default_duration(self):
        from src.autonomous_ops.simulation import ScenarioType
        eng = self._engine()
        sc = eng.create_scenario('test', ScenarioType.demand_surge, {})
        assert sc.duration_hours == 24.0

    def test_run_simulation_price_crash(self):
        from src.autonomous_ops.simulation import ScenarioType, SimulationStatus
        eng = self._engine()
        sc = eng.create_scenario('crash', ScenarioType.price_crash, {'crash_pct': -20})
        result = eng.run_simulation(sc.scenario_id, {'revenue': 1000000, 'cost': 700000, 'orders': 100})
        assert result.status == SimulationStatus.completed
        assert result.revenue_impact < 0

    def test_run_simulation_demand_surge(self):
        from src.autonomous_ops.simulation import ScenarioType
        eng = self._engine()
        sc = eng.create_scenario('surge', ScenarioType.demand_surge, {'surge_pct': 50})
        result = eng.run_simulation(sc.scenario_id, {})
        assert result.revenue_impact > 0
        assert result.order_impact > 0

    def test_run_simulation_supply_disruption(self):
        from src.autonomous_ops.simulation import ScenarioType
        eng = self._engine()
        sc = eng.create_scenario('dis', ScenarioType.supply_disruption, {'disruption_pct': 30})
        result = eng.run_simulation(sc.scenario_id, {})
        assert result.revenue_impact < 0

    def test_run_simulation_currency_shock(self):
        from src.autonomous_ops.simulation import ScenarioType
        eng = self._engine()
        sc = eng.create_scenario('fx', ScenarioType.currency_shock, {'fx_change_pct': 10})
        result = eng.run_simulation(sc.scenario_id, {})
        assert result.cost_impact != 0

    def test_run_simulation_system_failure(self):
        from src.autonomous_ops.simulation import ScenarioType
        eng = self._engine()
        sc = eng.create_scenario('fail', ScenarioType.system_failure, {'duration_hours': 4})
        result = eng.run_simulation(sc.scenario_id, {})
        assert result.revenue_impact < 0

    def test_run_simulation_competitor_action(self):
        from src.autonomous_ops.simulation import ScenarioType
        eng = self._engine()
        sc = eng.create_scenario('comp', ScenarioType.competitor_action, {'impact_pct': -10})
        result = eng.run_simulation(sc.scenario_id, {})
        assert result.revenue_impact < 0

    def test_run_simulation_not_found(self):
        eng = self._engine()
        with pytest.raises(KeyError):
            eng.run_simulation('nonexistent_id', {})

    def test_get_scenario(self):
        from src.autonomous_ops.simulation import ScenarioType
        eng = self._engine()
        sc = eng.create_scenario('t', ScenarioType.price_crash, {})
        found = eng.get_scenario(sc.scenario_id)
        assert found is not None
        assert found.scenario_id == sc.scenario_id

    def test_get_scenario_not_found(self):
        eng = self._engine()
        assert eng.get_scenario('nonexistent') is None

    def test_get_result(self):
        from src.autonomous_ops.simulation import ScenarioType
        eng = self._engine()
        sc = eng.create_scenario('t', ScenarioType.demand_surge, {})
        res = eng.run_simulation(sc.scenario_id, {})
        found = eng.get_result(res.result_id)
        assert found is not None

    def test_get_result_not_found(self):
        eng = self._engine()
        assert eng.get_result('nonexistent') is None

    def test_list_scenarios(self):
        from src.autonomous_ops.simulation import ScenarioType
        eng = self._engine()
        eng.create_scenario('s1', ScenarioType.price_crash, {})
        eng.create_scenario('s2', ScenarioType.demand_surge, {})
        scenarios = eng.list_scenarios()
        assert len(scenarios) == 2
        assert isinstance(scenarios[0], dict)

    def test_list_results(self):
        from src.autonomous_ops.simulation import ScenarioType
        eng = self._engine()
        sc = eng.create_scenario('t', ScenarioType.system_failure, {})
        eng.run_simulation(sc.scenario_id, {})
        results = eng.list_results()
        assert len(results) == 1

    def test_what_if_analysis(self):
        eng = self._engine()
        result = eng.what_if_analysis(1000000, price_change_pct=-10, demand_change_pct=5)
        assert 'base_revenue' in result
        assert 'adjusted_revenue' in result
        assert 'adjusted_cost' in result
        assert 'net_profit' in result
        assert 'margin_rate' in result

    def test_what_if_analysis_price_drop(self):
        eng = self._engine()
        result = eng.what_if_analysis(1000000, price_change_pct=-20)
        assert result['adjusted_revenue'] < 1000000

    def test_simulation_result_recommendations(self):
        from src.autonomous_ops.simulation import ScenarioType
        eng = self._engine()
        sc = eng.create_scenario('t', ScenarioType.price_crash, {})
        result = eng.run_simulation(sc.scenario_id, {})
        assert isinstance(result.recommendations, list)
        assert len(result.recommendations) > 0


# ─── UnifiedDashboard ────────────────────────────────────────────────────────

class TestUnifiedDashboard:
    def _dashboard(self):
        from src.autonomous_ops.engine import AutonomousOperationEngine
        from src.autonomous_ops.revenue_model import RevenueTracker
        from src.autonomous_ops.anomaly_detector import AnomalyDetector
        from src.autonomous_ops.autopilot import AutoPilotController
        from src.autonomous_ops.intervention import InterventionTracker, ManualTaskQueue
        from src.autonomous_ops.dashboard import UnifiedDashboard
        return UnifiedDashboard(
            engine=AutonomousOperationEngine(),
            revenue_tracker=RevenueTracker(),
            anomaly_detector=AnomalyDetector(),
            autopilot=AutoPilotController(),
            intervention_tracker=InterventionTracker(),
            task_queue=ManualTaskQueue(),
        )

    def test_get_realtime_metrics_keys(self):
        d = self._dashboard()
        metrics = d.get_realtime_metrics()
        for k in ['revenue_today', 'profit_today', 'margin_rate', 'automation_rate',
                  'active_alerts', 'health_score', 'operation_mode']:
            assert k in metrics

    def test_get_realtime_metrics_types(self):
        d = self._dashboard()
        metrics = d.get_realtime_metrics()
        assert isinstance(metrics['revenue_today'], float)
        assert isinstance(metrics['health_score'], float)

    def test_get_revenue_analysis(self):
        d = self._dashboard()
        analysis = d.get_revenue_analysis()
        assert 'by_stream' in analysis
        assert 'by_channel' in analysis

    def test_get_cost_analysis(self):
        d = self._dashboard()
        cost = d.get_cost_analysis()
        assert 'total' in cost
        assert 'product_cost' in cost

    def test_get_trend_data(self):
        d = self._dashboard()
        trend = d.get_trend_data()
        assert 'weekly' in trend
        assert 'monthly' in trend

    def test_get_alert_history(self):
        d = self._dashboard()
        history = d.get_alert_history()
        assert isinstance(history, list)

    def test_get_full_dashboard(self):
        d = self._dashboard()
        full = d.get_full_dashboard()
        for k in ['realtime', 'revenue', 'costs', 'trends', 'alerts', 'autopilot_stats', 'intervention', 'manual_queue']:
            assert k in full


# ─── API Tests ────────────────────────────────────────────────────────────────

class TestAutonomousOpsAPI:
    @pytest.fixture
    def client(self):
        import flask
        app = flask.Flask(__name__)
        from src.api.autonomous_ops_api import autonomous_ops_bp
        # Reset module-level singletons for test isolation
        import src.api.autonomous_ops_api as api_mod
        api_mod._engine = None
        api_mod._revenue_tracker = None
        api_mod._anomaly_detector = None
        api_mod._autopilot = None
        api_mod._intervention_tracker = None
        api_mod._task_queue = None
        api_mod._forecaster = None
        api_mod._margin_analyzer = None
        api_mod._simulation_engine = None
        api_mod._dashboard = None
        app.register_blueprint(autonomous_ops_bp)
        app.config['TESTING'] = True
        with app.test_client() as c:
            yield c

    def test_get_status(self, client):
        resp = client.get('/api/v1/autonomous-ops/status')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'mode' in data
        assert data['mode'] == 'fully_auto'

    def test_set_mode_valid(self, client):
        resp = client.post('/api/v1/autonomous-ops/mode', json={'mode': 'manual'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['mode'] == 'manual'

    def test_set_mode_invalid(self, client):
        resp = client.post('/api/v1/autonomous-ops/mode', json={'mode': 'invalid'})
        assert resp.status_code == 400

    def test_set_mode_missing_field(self, client):
        resp = client.post('/api/v1/autonomous-ops/mode', json={})
        assert resp.status_code == 400

    def test_get_revenue(self, client):
        resp = client.get('/api/v1/autonomous-ops/revenue')
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, dict)

    def test_get_revenue_forecast(self, client):
        resp = client.get('/api/v1/autonomous-ops/revenue/forecast?periods=5')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'forecast' in data
        assert len(data['forecast']) == 5

    def test_get_revenue_breakdown(self, client):
        resp = client.get('/api/v1/autonomous-ops/revenue/breakdown?product_cost=60000&shipping=10000')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'total' in data
        assert data['product_cost'] == 60000.0

    def test_get_margins(self, client):
        resp = client.get('/api/v1/autonomous-ops/margins')
        assert resp.status_code == 200

    def test_list_anomalies_empty(self, client):
        resp = client.get('/api/v1/autonomous-ops/anomalies')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['total'] == 0

    def test_get_anomaly_not_found(self, client):
        resp = client.get('/api/v1/autonomous-ops/anomalies/nonexistent')
        assert resp.status_code == 404

    def test_acknowledge_anomaly_not_found(self, client):
        resp = client.post('/api/v1/autonomous-ops/anomalies/nonexistent/acknowledge')
        assert resp.status_code == 404

    def test_get_automation(self, client):
        resp = client.get('/api/v1/autonomous-ops/automation')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'automation_coverage' in data

    def test_get_manual_queue_empty(self, client):
        resp = client.get('/api/v1/autonomous-ops/manual-queue')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['total'] == 0

    def test_run_simulation(self, client):
        resp = client.post('/api/v1/autonomous-ops/simulate', json={
            'name': 'Test Sim',
            'type': 'price_crash',
            'parameters': {'crash_pct': -20},
            'base_metrics': {'revenue': 1000000, 'cost': 700000, 'orders': 100},
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert 'scenario' in data
        assert 'result' in data

    def test_run_simulation_invalid_type(self, client):
        resp = client.post('/api/v1/autonomous-ops/simulate', json={'type': 'invalid_type'})
        assert resp.status_code == 400

    def test_get_simulation_result_not_found(self, client):
        resp = client.get('/api/v1/autonomous-ops/simulate/nonexistent_id')
        assert resp.status_code == 404

    def test_get_simulation_result(self, client):
        # run first
        resp = client.post('/api/v1/autonomous-ops/simulate', json={
            'name': 'sim',
            'type': 'demand_surge',
            'parameters': {},
        })
        result_id = resp.get_json()['result']['result_id']
        resp2 = client.get(f'/api/v1/autonomous-ops/simulate/{result_id}')
        assert resp2.status_code == 200

    def test_get_dashboard(self, client):
        resp = client.get('/api/v1/autonomous-ops/dashboard')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'realtime' in data

    def test_get_health(self, client):
        resp = client.get('/api/v1/autonomous-ops/health')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'score' in data

    def test_get_actions_empty(self, client):
        resp = client.get('/api/v1/autonomous-ops/actions')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['total'] == 0

    def test_list_anomalies_with_filter(self, client):
        resp = client.get('/api/v1/autonomous-ops/anomalies?acknowledged=false')
        assert resp.status_code == 200

    def test_set_mode_emergency(self, client):
        resp = client.post('/api/v1/autonomous-ops/mode', json={'mode': 'emergency'})
        assert resp.status_code == 200
        assert resp.get_json()['mode'] == 'emergency'

    def test_set_mode_semi_auto(self, client):
        resp = client.post('/api/v1/autonomous-ops/mode', json={'mode': 'semi_auto'})
        assert resp.status_code == 200
        assert resp.get_json()['mode'] == 'semi_auto'

    def test_revenue_forecast_default_periods(self, client):
        resp = client.get('/api/v1/autonomous-ops/revenue/forecast')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['periods'] == 7
