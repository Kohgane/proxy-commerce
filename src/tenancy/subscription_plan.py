"""src/tenancy/subscription_plan.py — 구독 플랜."""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

PLANS = {
    'free': {
        'name': 'Free',
        'feature_limits': {'api_access': True, 'analytics': False, 'webhooks': False},
        'usage_limits': {
            'max_products': 100,
            'max_orders_per_month': 50,
            'max_api_calls_per_day': 1000,
        },
    },
    'basic': {
        'name': 'Basic',
        'feature_limits': {'api_access': True, 'analytics': True, 'webhooks': False},
        'usage_limits': {
            'max_products': 1000,
            'max_orders_per_month': 500,
            'max_api_calls_per_day': 10000,
        },
    },
    'pro': {
        'name': 'Pro',
        'feature_limits': {'api_access': True, 'analytics': True, 'webhooks': True},
        'usage_limits': {
            'max_products': 10000,
            'max_orders_per_month': 5000,
            'max_api_calls_per_day': 100000,
        },
    },
    'enterprise': {
        'name': 'Enterprise',
        'feature_limits': {'api_access': True, 'analytics': True, 'webhooks': True},
        'usage_limits': {
            'max_products': -1,
            'max_orders_per_month': -1,
            'max_api_calls_per_day': -1,
        },
    },
}


class SubscriptionPlan:
    """구독 플랜 조회 및 제한 확인."""

    def get_plan(self, name: str) -> Optional[dict]:
        return PLANS.get(name)

    def check_limit(self, plan_name: str, feature: str, current_usage: int) -> bool:
        """현재 사용량이 제한 이하이면 True 반환."""
        plan = PLANS.get(plan_name)
        if plan is None:
            return False
        limit = plan['usage_limits'].get(feature, 0)
        if limit == -1:
            return True
        return current_usage <= limit
