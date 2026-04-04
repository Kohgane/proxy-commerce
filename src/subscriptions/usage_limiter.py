"""src/subscriptions/usage_limiter.py — 플랜별 사용량 제한 (Phase 92).

플랜 제한 체크, 초과 경고/차단, 사용량 현황 대시보드 데이터를 관리한다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict

logger = logging.getLogger(__name__)

WARNING_THRESHOLD = 0.80  # 80% 도달 시 경고


@dataclass
class UsageRecord:
    """사용자/테넌트별 사용량 현황."""

    tenant_id: str
    products_count: int = 0
    orders_this_month: int = 0
    api_calls_today: int = 0
    storage_mb: float = 0.0
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        """딕셔너리로 변환한다."""
        return {
            "tenant_id": self.tenant_id,
            "products_count": self.products_count,
            "orders_this_month": self.orders_this_month,
            "api_calls_today": self.api_calls_today,
            "storage_mb": self.storage_mb,
            "updated_at": self.updated_at,
        }


class UsageLimiter:
    """플랜별 사용량 제한 체크 및 경고 관리자."""

    def __init__(self, plan_manager=None) -> None:
        self._usage: Dict[str, UsageRecord] = {}
        self._plan_manager = plan_manager

    def _get_plan_manager(self):
        if self._plan_manager is None:
            from .plan_manager import PlanManager
            self._plan_manager = PlanManager()
        return self._plan_manager

    def _get_or_create(self, tenant_id: str) -> UsageRecord:
        """사용량 레코드를 조회하거나 생성한다."""
        if tenant_id not in self._usage:
            self._usage[tenant_id] = UsageRecord(tenant_id=tenant_id)
        return self._usage[tenant_id]

    def get_usage(self, tenant_id: str) -> UsageRecord:
        """사용량 현황을 반환한다."""
        return self._get_or_create(tenant_id)

    def update_usage(self, tenant_id: str, **kwargs) -> UsageRecord:
        """사용량을 업데이트한다.

        Kwargs: products_count, orders_this_month, api_calls_today, storage_mb
        """
        rec = self._get_or_create(tenant_id)
        for key, value in kwargs.items():
            if hasattr(rec, key):
                setattr(rec, key, value)
        rec.updated_at = datetime.now(timezone.utc).isoformat()
        return rec

    def increment(self, tenant_id: str, field_name: str, delta: int = 1) -> UsageRecord:
        """사용량을 증분한다."""
        rec = self._get_or_create(tenant_id)
        current = getattr(rec, field_name, 0)
        setattr(rec, field_name, current + delta)
        rec.updated_at = datetime.now(timezone.utc).isoformat()
        return rec

    def check_limit(self, tenant_id: str, plan_id: str, resource: str) -> dict:
        """특정 리소스의 제한 초과 여부를 확인한다.

        Args:
            tenant_id: 테넌트 ID
            plan_id: 플랜 ID
            resource: "products" | "orders" | "api_calls" | "storage"

        Returns:
            {"allowed": bool, "warning": bool, "usage": int/float, "limit": int, "ratio": float}
        """
        pm = self._get_plan_manager()
        plan = pm.get_plan(plan_id)
        if plan is None:
            raise ValueError(f"플랜을 찾을 수 없습니다: {plan_id}")

        rec = self._get_or_create(tenant_id)
        limits = plan.limits

        resource_map = {
            "products": (rec.products_count, limits.max_products),
            "orders": (rec.orders_this_month, limits.max_orders_per_month),
            "api_calls": (rec.api_calls_today, limits.max_api_calls_per_day),
            "storage": (rec.storage_mb, limits.max_storage_mb),
        }
        if resource not in resource_map:
            raise ValueError(f"알 수 없는 리소스: {resource}")

        usage, limit = resource_map[resource]
        # -1은 무제한
        if limit == -1:
            return {"allowed": True, "warning": False, "usage": usage, "limit": limit, "ratio": 0.0}

        ratio = usage / limit if limit > 0 else 0.0
        allowed = ratio < 1.0
        warning = ratio >= WARNING_THRESHOLD and allowed

        if not allowed:
            logger.warning("사용량 제한 초과: tenant=%s resource=%s %s/%s", tenant_id, resource, usage, limit)
        elif warning:
            logger.info("사용량 경고: tenant=%s resource=%s %.0f%%", tenant_id, resource, ratio * 100)

        return {
            "allowed": allowed,
            "warning": warning,
            "usage": usage,
            "limit": limit,
            "ratio": round(ratio, 4),
        }

    def get_dashboard(self, tenant_id: str, plan_id: str) -> dict:
        """사용량 현황 대시보드 데이터를 반환한다."""
        resources = ["products", "orders", "api_calls", "storage"]
        dashboard: Dict[str, dict] = {}
        for resource in resources:
            try:
                dashboard[resource] = self.check_limit(tenant_id, plan_id, resource)
            except ValueError as exc:
                dashboard[resource] = {"error": str(exc)}
        return {
            "tenant_id": tenant_id,
            "plan_id": plan_id,
            "usage": self._get_or_create(tenant_id).to_dict(),
            "limits": dashboard,
        }
