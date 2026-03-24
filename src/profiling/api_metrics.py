"""
API 메트릭 수집 — 엔드포인트별 요청 수, 응답 시간, 에러율.

환경변수:
    METRICS_ENABLED: 1이면 활성화 (기본: 1)
    METRICS_API_ENABLED: /api/metrics 엔드포인트 활성화 여부 (기본: 1)
"""

import logging
import os
import threading
import time
from collections import defaultdict
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_METRICS_ENABLED = int(os.getenv("METRICS_ENABLED", "1"))

# 지원되는 외부 API 목록
EXTERNAL_APIS = ["shopify", "woocommerce", "google_sheets", "deepl", "telegram", "frankfurter"]


class EndpointMetrics:
    """단일 엔드포인트(또는 API) 메트릭."""

    def __init__(self):
        self.request_count: int = 0
        self.error_count: int = 0
        self.total_response_ms: float = 0.0
        self._times: List[float] = []  # 최근 100개 응답 시간 보관
        self._lock = threading.Lock()

    def record(self, elapsed_ms: float, is_error: bool = False) -> None:
        """요청 결과를 기록한다."""
        with self._lock:
            self.request_count += 1
            if is_error:
                self.error_count += 1
            self.total_response_ms += elapsed_ms
            self._times.append(elapsed_ms)
            if len(self._times) > 100:
                self._times.pop(0)

    @property
    def avg_response_ms(self) -> float:
        if self.request_count == 0:
            return 0.0
        return self.total_response_ms / self.request_count

    @property
    def error_rate(self) -> float:
        if self.request_count == 0:
            return 0.0
        return self.error_count / self.request_count

    def to_dict(self) -> dict:
        return {
            "request_count": self.request_count,
            "error_count": self.error_count,
            "avg_response_ms": round(self.avg_response_ms, 1),
            "error_rate": round(self.error_rate, 4),
        }

    def reset(self) -> None:
        with self._lock:
            self.request_count = 0
            self.error_count = 0
            self.total_response_ms = 0.0
            self._times.clear()


class ApiMetrics:
    """API 메트릭 수집기 (싱글톤).

    엔드포인트별 요청 수, 평균 응답 시간, 에러율을 수집한다.
    """

    _instance: Optional["ApiMetrics"] = None

    def __new__(cls) -> "ApiMetrics":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._endpoints: Dict[str, EndpointMetrics] = defaultdict(EndpointMetrics)
            cls._instance._external: Dict[str, EndpointMetrics] = defaultdict(EndpointMetrics)
            cls._instance._start_time = time.time()
        return cls._instance

    # ── 기록 ──────────────────────────────────────────────────

    def record_endpoint(self, endpoint: str, elapsed_ms: float, is_error: bool = False) -> None:
        """엔드포인트 요청 결과를 기록한다.

        인자:
            endpoint: 엔드포인트 식별자 (예: "GET /api/health")
            elapsed_ms: 응답 시간(ms)
            is_error: 에러 여부
        """
        if not _METRICS_ENABLED:
            return
        self._endpoints[endpoint].record(elapsed_ms, is_error)

    def record_external(self, api_name: str, elapsed_ms: float, is_error: bool = False) -> None:
        """외부 API 호출 결과를 기록한다.

        인자:
            api_name: 외부 API 이름 (예: "shopify", "google_sheets")
            elapsed_ms: 응답 시간(ms)
            is_error: 에러 여부
        """
        if not _METRICS_ENABLED:
            return
        self._external[api_name].record(elapsed_ms, is_error)

    # ── 조회 ──────────────────────────────────────────────────

    def get_endpoint_metrics(self) -> dict:
        """모든 엔드포인트 메트릭을 반환한다."""
        return {k: v.to_dict() for k, v in self._endpoints.items()}

    def get_external_metrics(self) -> dict:
        """모든 외부 API 메트릭을 반환한다."""
        return {k: v.to_dict() for k, v in self._external.items()}

    def get_summary(self) -> dict:
        """전체 메트릭 요약을 반환한다."""
        uptime_s = int(time.time() - self._start_time)
        return {
            "uptime_seconds": uptime_s,
            "endpoints": self.get_endpoint_metrics(),
            "external_apis": self.get_external_metrics(),
        }

    # ── 리셋 ──────────────────────────────────────────────────

    def reset(self) -> None:
        """모든 메트릭을 초기화한다."""
        for m in self._endpoints.values():
            m.reset()
        for m in self._external.values():
            m.reset()
        self._endpoints.clear()
        self._external.clear()
        self._start_time = time.time()
        logger.info("API 메트릭 리셋 완료")


# 전역 인스턴스
_metrics = ApiMetrics()


def get_metrics() -> ApiMetrics:
    """전역 ApiMetrics 인스턴스를 반환한다."""
    return _metrics
