"""src/tenancy/usage_tracker.py — 테넌트별 사용량 추적."""
from __future__ import annotations

from collections import defaultdict
from typing import Dict


class UsageTracker:
    """테넌트별 API 호출/주문수/상품수 사용량 추적."""

    def __init__(self) -> None:
        self._usage: Dict[str, Dict[str, int]] = defaultdict(lambda: {
            "api_calls": 0,
            "orders": 0,
            "products": 0,
        })

    def increment(self, tenant_id: str, resource: str, amount: int = 1) -> int:
        """사용량 증가. 현재 값 반환."""
        self._usage[tenant_id][resource] = self._usage[tenant_id].get(resource, 0) + amount
        return self._usage[tenant_id][resource]

    def get(self, tenant_id: str) -> dict:
        """테넌트 전체 사용량 조회."""
        return dict(self._usage.get(tenant_id, {"api_calls": 0, "orders": 0, "products": 0}))

    def get_resource(self, tenant_id: str, resource: str) -> int:
        """특정 리소스 사용량 조회."""
        return self._usage.get(tenant_id, {}).get(resource, 0)

    def reset(self, tenant_id: str, resource: str = None) -> None:
        """사용량 초기화 (월별 리셋 등)."""
        if resource:
            if tenant_id in self._usage:
                self._usage[tenant_id][resource] = 0
        else:
            self._usage[tenant_id] = {"api_calls": 0, "orders": 0, "products": 0}

    def reset_all(self) -> None:
        """모든 테넌트 사용량 초기화."""
        self._usage.clear()

    def summary(self) -> list:
        """모든 테넌트 사용량 요약."""
        return [
            {"tenant_id": tid, **usage}
            for tid, usage in self._usage.items()
        ]
