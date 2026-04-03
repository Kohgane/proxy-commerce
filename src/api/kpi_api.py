"""src/api/kpi_api.py — KPI 대시보드 API Blueprint (Phase 70)."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

kpi_bp = Blueprint("kpi", __name__, url_prefix="/api/v1/kpi")


@kpi_bp.get("/definitions")
def definitions():
    """KPI 정의 목록 조회."""
    from ..kpi.kpi_manager import KPIManager
    mgr = KPIManager()
    return jsonify(mgr.list_kpis())


@kpi_bp.post("/calculate")
def calculate():
    """KPI 계산."""
    body = request.get_json(silent=True) or {}
    data = body.get("data", {})
    from ..kpi.kpi_manager import KPIManager
    mgr = KPIManager()
    return jsonify(mgr.calculate_all(data))


@kpi_bp.post("/track")
def track():
    """KPI 값 기록."""
    body = request.get_json(silent=True) or {}
    kpi_name = body.get("kpi_name", "")
    value = body.get("value", 0.0)
    period = body.get("period", "daily")
    from ..kpi.kpi_tracker import KPITracker
    tracker = KPITracker()
    return jsonify(tracker.record(kpi_name, value, period))


@kpi_bp.get("/alerts")
def alerts():
    """KPI 알림 목록 조회."""
    from ..kpi.kpi_alert import KPIAlert
    alert = KPIAlert()
    return jsonify(alert.get_alerts())


@kpi_bp.get("/reports/summary")
def report_summary():
    """KPI 요약 리포트."""
    from ..kpi.kpi_manager import KPIManager
    from ..kpi.kpi_report import KPIReport
    mgr = KPIManager()
    report = KPIReport()
    return jsonify(report.generate_summary(mgr.list_kpis()))
