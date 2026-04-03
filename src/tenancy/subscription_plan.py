"""src/tenancy/subscription_plan.py — 구독 플랜 관리."""
from __future__ import annotations

from enum import Enum
from typing import Dict, Optional


class PlanTier(str, Enum):
    FREE = "free"
    BASIC = "basic"
    PRO = "pro"
    ENTERPRISE = "enterprise"


_PLAN_LIMITS: Dict[str, dict] = {
    PlanTier.FREE: {
        "tier": PlanTier.FREE,
        "monthly_api_calls": 1_000,
        "monthly_orders": 50,
        "max_products": 100,
        "max_users": 1,
        "features": ["basic_api", "order_management"],
        "price_krw": 0,
    },
    PlanTier.BASIC: {
        "tier": PlanTier.BASIC,
        "monthly_api_calls": 10_000,
        "monthly_orders": 500,
        "max_products": 1_000,
        "max_users": 5,
        "features": ["basic_api", "order_management", "analytics", "coupons"],
        "price_krw": 29_000,
    },
    PlanTier.PRO: {
        "tier": PlanTier.PRO,
        "monthly_api_calls": 100_000,
        "monthly_orders": 5_000,
        "max_products": 10_000,
        "max_users": 20,
        "features": [
            "basic_api", "order_management", "analytics", "coupons",
            "ab_testing", "webhooks", "advanced_pricing",
        ],
        "price_krw": 99_000,
    },
    PlanTier.ENTERPRISE: {
        "tier": PlanTier.ENTERPRISE,
        "monthly_api_calls": -1,  # unlimited
        "monthly_orders": -1,
        "max_products": -1,
        "max_users": -1,
        "features": ["all"],
        "price_krw": 299_000,
    },
}


class SubscriptionPlan:
    """구독 플랜 관리."""

    def get_plan(self, tier: str) -> dict:
        """플랜 정보 조회."""
        t = PlanTier(tier)
        return dict(_PLAN_LIMITS[t])

    def list_plans(self) -> list:
        """모든 플랜 목록."""
        return [dict(v) for v in _PLAN_LIMITS.values()]

    def check_limit(self, tier: str, resource: str, current_usage: int) -> bool:
        """사용량이 플랜 한도 내인지 확인. -1이면 무제한."""
        plan = self.get_plan(tier)
        limit = plan.get(resource, 0)
        if limit == -1:
            return True
        return current_usage <= limit

    def has_feature(self, tier: str, feature: str) -> bool:
        """해당 플랜에 특정 기능이 포함되는지 확인."""
        plan = self.get_plan(tier)
        features = plan.get("features", [])
        return "all" in features or feature in features

    def upgrade_path(self, current_tier: str) -> Optional[str]:
        """다음 업그레이드 경로."""
        order = [PlanTier.FREE, PlanTier.BASIC, PlanTier.PRO, PlanTier.ENTERPRISE]
        try:
            idx = order.index(PlanTier(current_tier))
        except ValueError:
            return None
        if idx + 1 < len(order):
            return order[idx + 1].value
        return None
