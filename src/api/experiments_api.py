"""src/api/experiments_api.py — A/B 테스트 API Blueprint (Phase 50)."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

experiments_bp = Blueprint("experiments", __name__, url_prefix="/api/v1/experiments")

_exp_mgr = None
_assigner = None
_tracker = None
_analyzer = None
_reporter = None


def _get_services():
    global _exp_mgr, _assigner, _tracker, _analyzer, _reporter
    if _exp_mgr is None:
        from ..ab_testing.experiment_manager import ExperimentManager
        from ..ab_testing.variant_assigner import VariantAssigner
        from ..ab_testing.metrics_tracker import MetricsTracker
        from ..ab_testing.statistical_analyzer import StatisticalAnalyzer
        from ..ab_testing.experiment_report import ExperimentReport
        _exp_mgr = ExperimentManager()
        _assigner = VariantAssigner()
        _tracker = MetricsTracker()
        _analyzer = StatisticalAnalyzer()
        _reporter = ExperimentReport()
    return _exp_mgr, _assigner, _tracker, _analyzer, _reporter


@experiments_bp.get("/status")
def status():
    return jsonify({"status": "ok", "module": "ab_testing"})


@experiments_bp.get("/")
def list_experiments():
    mgr, _, _, _, _ = _get_services()
    status_filter = request.args.get("status")
    return jsonify(mgr.list(status=status_filter))


@experiments_bp.post("/")
def create_experiment():
    mgr, _, _, _, _ = _get_services()
    data = request.get_json(force=True) or {}
    try:
        exp = mgr.create(
            name=data.get("name", ""),
            variants=data.get("variants"),
        )
        return jsonify(exp), 201
    except ValueError:
        return jsonify({"error": "name은 필수입니다."}), 400


@experiments_bp.get("/<experiment_id>")
def get_experiment(experiment_id: str):
    mgr, _, _, _, _ = _get_services()
    exp = mgr.get(experiment_id)
    if not exp:
        return jsonify({"error": "실험 없음"}), 404
    return jsonify(exp)


@experiments_bp.post("/<experiment_id>/start")
def start_experiment(experiment_id: str):
    mgr, _, _, _, _ = _get_services()
    try:
        return jsonify(mgr.start(experiment_id))
    except KeyError:
        return jsonify({"error": "실험 없음"}), 404


@experiments_bp.post("/<experiment_id>/stop")
def stop_experiment(experiment_id: str):
    mgr, _, _, _, _ = _get_services()
    try:
        return jsonify(mgr.stop(experiment_id))
    except KeyError:
        return jsonify({"error": "실험 없음"}), 404


@experiments_bp.post("/<experiment_id>/assign")
def assign_variant(experiment_id: str):
    mgr, assigner, _, _, _ = _get_services()
    data = request.get_json(force=True) or {}
    exp = mgr.get(experiment_id)
    if not exp:
        return jsonify({"error": "실험 없음"}), 404
    user_id = data.get("user_id", "")
    variant = assigner.assign(experiment_id, user_id, exp.get("variants"))
    return jsonify({"experiment_id": experiment_id, "user_id": user_id, "variant": variant})


@experiments_bp.post("/<experiment_id>/track")
def track_event(experiment_id: str):
    _, _, tracker, _, _ = _get_services()
    data = request.get_json(force=True) or {}
    event_type = data.get("event_type", "impression")
    variant = data.get("variant", "control")
    user_id = data.get("user_id", "")
    revenue = float(data.get("revenue", 0.0))

    if event_type == "impression":
        tracker.record_impression(experiment_id, variant, user_id)
    elif event_type == "click":
        tracker.record_click(experiment_id, variant, user_id)
    elif event_type == "conversion":
        tracker.record_conversion(experiment_id, variant, user_id, revenue)

    return jsonify({"tracked": True, "event_type": event_type})


@experiments_bp.get("/<experiment_id>/report")
def get_report(experiment_id: str):
    mgr, _, tracker, analyzer, reporter = _get_services()
    exp = mgr.get(experiment_id)
    if not exp:
        return jsonify({"error": "실험 없음"}), 404

    metrics = tracker.get_metrics(experiment_id)
    variants = exp.get("variants", ["control", "treatment"])

    analysis = {}
    if len(variants) >= 2:
        m1 = metrics.get(variants[0], {})
        m2 = metrics.get(variants[1], {})
        analysis = analyzer.z_test(
            n1=m1.get("impressions", 0), conv1=m1.get("conversions", 0),
            n2=m2.get("impressions", 0), conv2=m2.get("conversions", 0),
        )

    report = reporter.generate(exp, metrics, analysis)
    return jsonify(report)
