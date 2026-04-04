"""src/subscriptions/plan_manager.py — 플랜 정의 및 관리 (Phase 92).

Free / Starter / Pro / Enterprise 플랜과 제한, 가격을 관리한다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

ANNUAL_DISCOUNT = 0.20  # 연간 결제 20% 할인


@dataclass
class PlanLimits:
    """플랜별 사용 제한."""

    max_products: int  # 최대 상품 수 (-1 = 무제한)
    max_orders_per_month: int  # 월 최대 주문 수 (-1 = 무제한)
    max_api_calls_per_day: int  # 일 최대 API 호출 수 (-1 = 무제한)
    max_storage_mb: int  # 최대 스토리지 (MB, -1 = 무제한)

    def to_dict(self) -> dict:
        """딕셔너리로 변환한다."""
        return {
            "max_products": self.max_products,
            "max_orders_per_month": self.max_orders_per_month,
            "max_api_calls_per_day": self.max_api_calls_per_day,
            "max_storage_mb": self.max_storage_mb,
        }


@dataclass
class Plan:
    """구독 플랜 정의."""

    plan_id: str
    name: str
    monthly_price: int  # 원화 기준 월 가격
    limits: PlanLimits
    description: str = ""
    features: List[str] = field(default_factory=list)

    @property
    def annual_price(self) -> int:
        """연간 결제 가격 (20% 할인 적용, 월 환산)."""
        return int(self.monthly_price * (1 - ANNUAL_DISCOUNT))

    @property
    def annual_total(self) -> int:
        """연간 결제 총액."""
        return self.annual_price * 12

    def to_dict(self, billing_cycle: str = "monthly") -> dict:
        """딕셔너리로 변환한다."""
        price = self.annual_price if billing_cycle == "annual" else self.monthly_price
        return {
            "plan_id": self.plan_id,
            "name": self.name,
            "monthly_price": self.monthly_price,
            "annual_price_per_month": self.annual_price,
            "annual_total": self.annual_total,
            "current_price": price,
            "billing_cycle": billing_cycle,
            "limits": self.limits.to_dict(),
            "description": self.description,
            "features": self.features,
        }


# 기본 플랜 정의
_DEFAULT_PLANS: Dict[str, Plan] = {
    "free": Plan(
        plan_id="free",
        name="Free",
        monthly_price=0,
        limits=PlanLimits(
            max_products=50,
            max_orders_per_month=100,
            max_api_calls_per_day=1_000,
            max_storage_mb=512,
        ),
        description="소규모 셀러를 위한 무료 플랜",
        features=["기본 대시보드", "상품 수집", "주문 관리"],
    ),
    "starter": Plan(
        plan_id="starter",
        name="Starter",
        monthly_price=29_000,
        limits=PlanLimits(
            max_products=500,
            max_orders_per_month=1_000,
            max_api_calls_per_day=10_000,
            max_storage_mb=5_120,
        ),
        description="성장하는 셀러를 위한 스타터 플랜",
        features=["Free 플랜 포함", "자동화 규칙", "이메일 알림", "포인트 시스템"],
    ),
    "pro": Plan(
        plan_id="pro",
        name="Pro",
        monthly_price=99_000,
        limits=PlanLimits(
            max_products=5_000,
            max_orders_per_month=10_000,
            max_api_calls_per_day=100_000,
            max_storage_mb=51_200,
        ),
        description="전문 셀러를 위한 프로 플랜",
        features=["Starter 플랜 포함", "고급 분석", "API 접근", "우선 지원"],
    ),
    "enterprise": Plan(
        plan_id="enterprise",
        name="Enterprise",
        monthly_price=299_000,
        limits=PlanLimits(
            max_products=-1,
            max_orders_per_month=-1,
            max_api_calls_per_day=-1,
            max_storage_mb=-1,
        ),
        description="대형 셀러/기업을 위한 엔터프라이즈 플랜",
        features=["Pro 플랜 포함", "무제한 사용", "전담 매니저", "커스텀 통합", "SLA 보장"],
    ),
}


class PlanManager:
    """구독 플랜 관리자.

    플랜 정의 조회, 플랜 비교표 생성을 담당한다.
    """

    def __init__(self) -> None:
        self._plans: Dict[str, Plan] = dict(_DEFAULT_PLANS)

    def get_plan(self, plan_id: str) -> Optional[Plan]:
        """플랜을 조회한다."""
        return self._plans.get(plan_id.lower())

    def list_plans(self) -> List[Plan]:
        """전체 플랜 목록을 반환한다."""
        return list(self._plans.values())

    def get_comparison_table(self) -> List[dict]:
        """플랜 비교표를 생성한다."""
        return [p.to_dict() for p in self._plans.values()]

    def is_valid_plan(self, plan_id: str) -> bool:
        """플랜 ID 유효성을 확인한다."""
        return plan_id.lower() in self._plans

    def get_upgrade_path(self, current_plan_id: str) -> List[Plan]:
        """업그레이드 가능한 상위 플랜 목록을 반환한다."""
        plan_order = list(self._plans.keys())
        try:
            idx = plan_order.index(current_plan_id.lower())
        except ValueError:
            return []
        return [self._plans[pid] for pid in plan_order[idx + 1:]]
