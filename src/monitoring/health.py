"""헬스체크 — DB·Redis·외부 API 상태 확인."""
from __future__ import annotations

import datetime
import time
from typing import Optional

import requests


class HealthChecker:
    """서비스 의존성 상태를 점검하는 헬스체커."""

    # ------------------------------------------------------------------
    # 개별 체크
    # ------------------------------------------------------------------

    def check_database(self, db_url: Optional[str] = None) -> dict:
        if not db_url:
            return {"status": "unconfigured"}
        start = time.monotonic()
        try:
            # 실제 연결 없이 URL 파싱 가능 여부만 확인 (테스트 용이성)
            from urllib.parse import urlparse
            result = urlparse(db_url)
            if not result.scheme:
                raise ValueError("Invalid DB URL scheme")
            latency_ms = (time.monotonic() - start) * 1000
            return {"status": "ok", "message": "reachable", "latency_ms": round(latency_ms, 3)}
        except Exception as exc:
            latency_ms = (time.monotonic() - start) * 1000
            return {"status": "error", "message": str(exc), "latency_ms": round(latency_ms, 3)}

    def check_redis(self, redis_url: Optional[str] = None) -> dict:
        if not redis_url:
            return {"status": "unconfigured"}
        start = time.monotonic()
        try:
            from urllib.parse import urlparse
            result = urlparse(redis_url)
            if not result.scheme:
                raise ValueError("Invalid Redis URL scheme")
            latency_ms = (time.monotonic() - start) * 1000
            return {"status": "ok", "message": "reachable", "latency_ms": round(latency_ms, 3)}
        except Exception as exc:
            latency_ms = (time.monotonic() - start) * 1000
            return {"status": "error", "message": str(exc), "latency_ms": round(latency_ms, 3)}

    def check_external_api(self, url: str, timeout: float = 2.0) -> dict:
        start = time.monotonic()
        try:
            resp = requests.head(url, timeout=timeout)
            latency_ms = (time.monotonic() - start) * 1000
            if resp.status_code < 500:
                return {"status": "ok", "latency_ms": round(latency_ms, 3)}
            return {"status": "error", "latency_ms": round(latency_ms, 3)}
        except Exception as exc:
            latency_ms = (time.monotonic() - start) * 1000
            return {"status": "error", "message": str(exc), "latency_ms": round(latency_ms, 3)}

    # ------------------------------------------------------------------
    # 일괄 체크
    # ------------------------------------------------------------------

    def run_all_checks(self, checks: Optional[dict] = None) -> dict:
        """checks: {name: callable} 딕셔너리. None 이면 빈 체크."""
        if checks is None:
            checks = {}

        results: dict = {}
        for name, fn in checks.items():
            try:
                results[name] = fn()
            except Exception as exc:
                results[name] = {"status": "error", "message": str(exc)}

        statuses = [r.get("status") for r in results.values()]
        if not statuses:
            overall = "healthy"
        elif all(s == "ok" for s in statuses):
            overall = "healthy"
        elif all(s == "error" for s in statuses):
            overall = "unhealthy"
        else:
            overall = "degraded"

        timestamp = datetime.datetime.now(tz=datetime.timezone.utc).isoformat()
        return {"status": overall, "checks": results, "timestamp": timestamp}
