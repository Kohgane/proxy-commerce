"""src/rate_limiting/rate_limit_dashboard.py — 레이트 리밋 대시보드."""
from __future__ import annotations

from typing import Dict, List


class RateLimitDashboard:
    """현재 사용량/제한 통계 조회."""

    def __init__(self, limiter=None, policy=None) -> None:
        self._limiter = limiter
        self._policy = policy

    def get_stats(self) -> dict:
        policies = self._policy.list_policies() if self._policy else []
        usage_list = []
        for p in policies:
            endpoint = p["endpoint"]
            key = endpoint
            usage = self._limiter.get_usage(key) if self._limiter else {}
            usage_list.append({
                "endpoint": endpoint,
                "limit": p["limit"],
                "window": p["window"],
                "usage": usage,
            })
        return {"total_policies": len(policies), "usage": usage_list}

    def get_usage_all(self) -> List[dict]:
        return self.get_stats().get("usage", [])
