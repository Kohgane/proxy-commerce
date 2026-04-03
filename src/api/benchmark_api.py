"""src/api/benchmark_api.py — Phase 54: 벤치마크 API Blueprint."""
import logging

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

benchmark_bp = Blueprint('benchmark', __name__, url_prefix='/api/v1/benchmark')


@benchmark_bp.get('/status')
def benchmark_status():
    return jsonify({'status': 'ok', 'module': 'benchmark'})


@benchmark_bp.post('/run')
def run_benchmark():
    from ..benchmark.load_profile import LoadProfile
    from ..benchmark.benchmark_runner import BenchmarkRunner
    body = request.get_json(silent=True) or {}
    target_url = body.get('target_url', '')
    if not target_url:
        return jsonify({'error': 'target_url required'}), 400
    try:
        profile = LoadProfile(
            concurrent_users=int(body.get('concurrent_users', 10)),
            duration_seconds=int(body.get('duration_seconds', 30)),
            ramp_up_seconds=int(body.get('ramp_up_seconds', 5)),
            target_url=target_url,
            method=body.get('method', 'GET'),
            body=body.get('body'),
        )

        def mock_request(url, method='GET', b=None):
            import random
            return random.uniform(10, 100)

        runner = BenchmarkRunner(request_func=mock_request)
        result = runner.run(profile)
        return jsonify(result)
    except Exception as exc:
        logger.error("벤치마크 실행 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


@benchmark_bp.get('/results')
def list_results():
    from ..benchmark.regression_detector import RegressionDetector
    try:
        detector = RegressionDetector()
        return jsonify(detector.list_results())
    except Exception as exc:
        logger.error("벤치마크 결과 조회 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


@benchmark_bp.post('/compare')
def compare_results():
    from ..benchmark.regression_detector import RegressionDetector
    body = request.get_json(silent=True) or {}
    name = body.get('name', '')
    new_result = body.get('result', {})
    if not name:
        return jsonify({'error': 'name required'}), 400
    try:
        detector = RegressionDetector()
        comparison = detector.compare(name, new_result)
        return jsonify(comparison)
    except Exception as exc:
        logger.error("비교 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500
