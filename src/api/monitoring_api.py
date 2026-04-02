"""모니터링 API Blueprint — /api/v1/metrics, /api/v1/health."""
from flask import Blueprint, Response, jsonify

from ..monitoring import MetricsCollector, HealthChecker

monitoring_bp = Blueprint("monitoring", __name__, url_prefix="/api/v1")

# 앱 전역 메트릭 인스턴스 (싱글톤)
_metrics = MetricsCollector()
_health_checker = HealthChecker()


def get_metrics_collector() -> MetricsCollector:
    """앱 전역 MetricsCollector 반환 (테스트에서 교체 가능)."""
    return _metrics


@monitoring_bp.get("/metrics")
def prometheus_metrics():
    """Prometheus 텍스트 형식 메트릭 반환."""
    text = get_metrics_collector().export_prometheus_text()
    return Response(text, status=200, mimetype="text/plain; version=0.0.4; charset=utf-8")


@monitoring_bp.get("/health")
def health_check():
    """헬스체크 엔드포인트 — 전체 서비스 상태 반환."""
    result = _health_checker.run_all_checks()
    status_code = 200 if result["status"] in ("healthy", "degraded") else 503
    return jsonify(result), status_code
