"""src/api/benchmark_api.py — 벤치마크 API Blueprint (Phase 54)."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

benchmark_bp = Blueprint("benchmark", __name__, url_prefix="/api/v1/benchmark")

_runner = None
_detector = None
_reports: list = []


def _get_services():
    global _runner, _detector
    if _runner is None:
        from ..benchmark.benchmark_runner import BenchmarkRunner
        from ..benchmark.regression_detector import RegressionDetector
        _detector = RegressionDetector()
        _runner = BenchmarkRunner(detector=_detector)
    return _runner, _detector


@benchmark_bp.get("/status")
def status():
    return jsonify({"status": "ok", "module": "benchmark"})


@benchmark_bp.post("/run")
def run_benchmark():
    """벤치마크 실행 (모의 실행으로 네트워크 호출 없음)."""
    runner, _ = _get_services()
    data = request.get_json(force=True) or {}

    from ..benchmark.load_profile import LoadProfile
    profile = LoadProfile(
        name=data.get("name", "api_test"),
        concurrent_users=int(data.get("concurrent_users", 10)),
        duration_seconds=int(data.get("duration_seconds", 5)),
        target_url=data.get("target_url", "http://localhost:8000/health"),
        method=data.get("method", "GET"),
    )

    try:
        mock_times = data.get("mock_response_times_ms")
        report = runner.run_mock(profile, response_times_ms=mock_times)
        _reports.append(report)
        return jsonify(report)
    except ValueError:
        return jsonify({"error": "유효하지 않은 프로파일 설정입니다."}), 400


@benchmark_bp.get("/results")
def get_results():
    """저장된 벤치마크 결과 목록."""
    _, detector = _get_services()
    return jsonify(detector.get_history())


@benchmark_bp.post("/compare")
def compare_results():
    """성능 회귀 비교."""
    _, detector = _get_services()
    data = request.get_json(force=True) or {}
    history = detector.get_history()

    if len(history) < 2:
        return jsonify({"error": "비교할 데이터 부족 (최소 2개 필요)"}), 400

    current = history[-1]
    baseline = history[-2]
    comparison = detector.compare(current, baseline)
    return jsonify(comparison)
