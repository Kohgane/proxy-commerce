"""tests/test_kpi.py — Phase 70 KPI 테스트."""
from __future__ import annotations

import pytest
from src.kpi.kpi_definition import KPIDefinition
from src.kpi.kpi_calculator import KPICalculator
from src.kpi.kpi_tracker import KPITracker
from src.kpi.kpi_alert import KPIAlert
from src.kpi.kpi_report import KPIReport
from src.kpi.kpi_manager import KPIManager


class TestKPIDefinition:
    def test_to_dict(self):
        kpi = KPIDefinition(name="GMV", formula="sum(orders)", target=1000000.0, unit="원", period="monthly")
        d = kpi.to_dict()
        assert d["name"] == "GMV"
        assert d["target"] == 1000000.0
        assert "kpi_id" in d

    def test_fields(self):
        kpi = KPIDefinition(name="test", formula="x", target=100.0, unit="%", period="daily")
        assert kpi.period == "daily"
        assert kpi.unit == "%"


class TestKPICalculator:
    def test_sum_metric(self):
        calc = KPICalculator()
        assert calc.sum_metric([1, 2, 3]) == 6.0

    def test_average_metric(self):
        calc = KPICalculator()
        assert calc.average_metric([10, 20, 30]) == 20.0

    def test_average_empty(self):
        calc = KPICalculator()
        assert calc.average_metric([]) == 0.0

    def test_ratio(self):
        calc = KPICalculator()
        assert calc.ratio(10.0, 100.0) == 0.1
        assert calc.ratio(10.0, 0) == 0.0

    def test_growth_rate(self):
        calc = KPICalculator()
        assert calc.growth_rate(110.0, 100.0) == pytest.approx(0.1)

    def test_growth_rate_zero_previous(self):
        calc = KPICalculator()
        assert calc.growth_rate(100.0, 0) == 0.0

    def test_yoy(self):
        calc = KPICalculator()
        assert calc.yoy(120.0, 100.0) == pytest.approx(0.2)

    def test_mom(self):
        calc = KPICalculator()
        assert calc.mom(105.0, 100.0) == pytest.approx(0.05)

    def test_calculate(self):
        calc = KPICalculator()
        assert calc.calculate("GMV", {"GMV": 500000.0}) == 500000.0


class TestKPITracker:
    def test_record(self):
        tracker = KPITracker()
        entry = tracker.record("GMV", 1000000.0)
        assert entry["kpi_name"] == "GMV"
        assert entry["value"] == 1000000.0

    def test_get_history(self):
        tracker = KPITracker()
        tracker.record("GMV", 100.0)
        tracker.record("GMV", 200.0)
        history = tracker.get_history("GMV")
        assert len(history) == 2

    def test_get_history_limit(self):
        tracker = KPITracker()
        for i in range(5):
            tracker.record("GMV", float(i))
        assert len(tracker.get_history("GMV", limit=3)) == 3

    def test_get_latest(self):
        tracker = KPITracker()
        tracker.record("GMV", 100.0)
        tracker.record("GMV", 999.0)
        latest = tracker.get_latest("GMV")
        assert latest["value"] == 999.0

    def test_get_latest_empty(self):
        tracker = KPITracker()
        assert tracker.get_latest("nonexistent") == {}


class TestKPIAlert:
    def test_check_goal_achieved(self):
        alert = KPIAlert()
        result = alert.check("GMV", 1000.0, 900.0)
        assert result["alert_type"] == "goal_achieved"

    def test_check_missed(self):
        alert = KPIAlert()
        result = alert.check("GMV", 500.0, 1000.0)
        assert result["alert_type"] == "missed"

    def test_check_normal(self):
        alert = KPIAlert()
        result = alert.check("GMV", 950.0, 1000.0, threshold_pct=10)
        assert result["alert_type"] == "normal"

    def test_get_alerts(self):
        alert = KPIAlert()
        alert.check("GMV", 100.0, 100.0)
        assert len(alert.get_alerts()) == 1

    def test_clear(self):
        alert = KPIAlert()
        alert.check("GMV", 100.0, 100.0)
        count = alert.clear()
        assert count == 1
        assert alert.get_alerts() == []


class TestKPIReport:
    def test_generate_summary(self):
        report = KPIReport()
        kpis = [{"name": "GMV"}, {"name": "CVR"}]
        result = report.generate_summary(kpis)
        assert result["total_kpis"] == 2
        assert "generated_at" in result

    def test_generate_trends_up(self):
        report = KPIReport()
        history = [{"value": 100}, {"value": 200}]
        result = report.generate_trends("GMV", history)
        assert result["trend"] == "up"

    def test_generate_trends_down(self):
        report = KPIReport()
        history = [{"value": 200}, {"value": 100}]
        result = report.generate_trends("GMV", history)
        assert result["trend"] == "down"

    def test_generate_comparison(self):
        report = KPIReport()
        current = {"GMV": 1200.0}
        previous = {"GMV": 1000.0}
        result = report.generate_comparison(current, previous)
        assert result["GMV"]["change_pct"] == pytest.approx(20.0)


class TestKPIManager:
    def test_builtin_kpis(self):
        mgr = KPIManager()
        kpis = mgr.list_kpis()
        names = [k["name"] for k in kpis]
        assert "GMV" in names
        assert "order_conversion_rate" in names

    def test_get_existing(self):
        mgr = KPIManager()
        kpi = mgr.get("GMV")
        assert kpi is not None
        assert kpi.name == "GMV"

    def test_get_nonexistent(self):
        mgr = KPIManager()
        assert mgr.get("nonexistent") is None

    def test_register(self):
        mgr = KPIManager()
        new_kpi = KPIDefinition(name="custom_kpi", formula="x/y", target=1.0, unit="회", period="weekly")
        mgr.register(new_kpi)
        assert mgr.get("custom_kpi") is not None

    def test_calculate_all(self):
        mgr = KPIManager()
        result = mgr.calculate_all({"GMV": 5000000.0})
        assert isinstance(result, dict)
        assert "GMV" in result
        assert result["GMV"] == 5000000.0
