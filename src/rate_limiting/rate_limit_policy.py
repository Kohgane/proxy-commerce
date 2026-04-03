"""src/rate_limiting/rate_limit_policy.py — 레이트 리미팅 정책 관리."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class RateLimitPolicy:
    """엔드포인트/사용자/테넌트별 정책 정의."""

    def __init__(self) -> None:
        self._policies: Dict[str, dict] = {}

    def set_policy(self, endpoint: str, limit: int, window: int) -> dict:
        policy = {
            "endpoint": endpoint,
            "limit": limit,
            "window": window,
            "updated_at": _now_iso(),
        }
        self._policies[endpoint] = policy
        return dict(policy)

    def get_policy(self, endpoint: str) -> Optional[dict]:
        p = self._policies.get(endpoint)
        return dict(p) if p else None

    def list_policies(self) -> List[dict]:
        return [dict(p) for p in self._policies.values()]

    def delete_policy(self, endpoint: str) -> None:
        self._policies.pop(endpoint, None)
