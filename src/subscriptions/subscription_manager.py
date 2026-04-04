"""src/subscriptions/subscription_manager.py — 구독 CRUD 및 상태 관리 (Phase 92).

구독 라이프사이클:
    trial → active → past_due → cancelled / expired
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

TRIAL_DAYS = 14


class SubscriptionStatus(str, Enum):
    """구독 상태."""

    TRIAL = "trial"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


# 허용된 상태 전환
_VALID_TRANSITIONS: Dict[SubscriptionStatus, List[SubscriptionStatus]] = {
    SubscriptionStatus.TRIAL: [SubscriptionStatus.ACTIVE, SubscriptionStatus.CANCELLED],
    SubscriptionStatus.ACTIVE: [SubscriptionStatus.PAST_DUE, SubscriptionStatus.CANCELLED],
    SubscriptionStatus.PAST_DUE: [SubscriptionStatus.ACTIVE, SubscriptionStatus.CANCELLED, SubscriptionStatus.EXPIRED],
    SubscriptionStatus.CANCELLED: [],
    SubscriptionStatus.EXPIRED: [],
}


@dataclass
class Subscription:
    """구독 엔티티."""

    subscription_id: str
    tenant_id: str
    user_id: str
    plan_id: str
    billing_cycle: str  # "monthly" | "annual"
    status: SubscriptionStatus
    trial_ends_at: Optional[str]
    current_period_start: str
    current_period_end: str
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    cancelled_at: Optional[str] = None
    auto_renew: bool = True
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """딕셔너리로 변환한다."""
        return {
            "subscription_id": self.subscription_id,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "plan_id": self.plan_id,
            "billing_cycle": self.billing_cycle,
            "status": self.status.value,
            "trial_ends_at": self.trial_ends_at,
            "current_period_start": self.current_period_start,
            "current_period_end": self.current_period_end,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "cancelled_at": self.cancelled_at,
            "auto_renew": self.auto_renew,
            "metadata": self.metadata,
        }


class SubscriptionManager:
    """구독 CRUD 및 상태 전환 관리자."""

    def __init__(self) -> None:
        self._subscriptions: Dict[str, Subscription] = {}

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create(
        self,
        tenant_id: str,
        user_id: str,
        plan_id: str,
        billing_cycle: str = "monthly",
        start_trial: bool = True,
    ) -> Subscription:
        """구독을 생성한다.

        Args:
            tenant_id: 테넌트 ID
            user_id: 사용자 ID
            plan_id: 플랜 ID
            billing_cycle: "monthly" | "annual"
            start_trial: True이면 trial 상태로 시작

        Returns:
            생성된 Subscription
        """
        if billing_cycle not in ("monthly", "annual"):
            raise ValueError(f"잘못된 billing_cycle: {billing_cycle}")

        now = datetime.now(timezone.utc)
        if billing_cycle == "annual":
            period_days = 365
        else:
            period_days = 30

        trial_ends_at: Optional[str] = None
        if start_trial and plan_id != "free":
            status = SubscriptionStatus.TRIAL
            trial_ends_at = (now + timedelta(days=TRIAL_DAYS)).isoformat()
            period_end = now + timedelta(days=TRIAL_DAYS + period_days)
        else:
            status = SubscriptionStatus.ACTIVE
            period_end = now + timedelta(days=period_days)

        sub = Subscription(
            subscription_id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            user_id=user_id,
            plan_id=plan_id,
            billing_cycle=billing_cycle,
            status=status,
            trial_ends_at=trial_ends_at,
            current_period_start=now.isoformat(),
            current_period_end=period_end.isoformat(),
        )
        self._subscriptions[sub.subscription_id] = sub
        logger.info("구독 생성: id=%s plan=%s status=%s", sub.subscription_id, plan_id, status.value)
        return sub

    def get(self, subscription_id: str) -> Optional[Subscription]:
        """구독을 조회한다."""
        return self._subscriptions.get(subscription_id)

    def list(
        self,
        tenant_id: Optional[str] = None,
        user_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Subscription]:
        """구독 목록을 조회한다."""
        subs = list(self._subscriptions.values())
        if tenant_id:
            subs = [s for s in subs if s.tenant_id == tenant_id]
        if user_id:
            subs = [s for s in subs if s.user_id == user_id]
        if status:
            subs = [s for s in subs if s.status.value == status]
        return subs

    # ------------------------------------------------------------------
    # 플랜 변경
    # ------------------------------------------------------------------

    def change_plan(self, subscription_id: str, new_plan_id: str, billing_cycle: Optional[str] = None) -> Subscription:
        """플랜을 변경한다 (업그레이드/다운그레이드)."""
        sub = self._subscriptions.get(subscription_id)
        if sub is None:
            raise ValueError(f"구독을 찾을 수 없습니다: {subscription_id}")
        if sub.status in (SubscriptionStatus.CANCELLED, SubscriptionStatus.EXPIRED):
            raise ValueError(f"취소/만료된 구독은 플랜 변경이 불가합니다: {sub.status.value}")

        sub.plan_id = new_plan_id
        if billing_cycle:
            if billing_cycle not in ("monthly", "annual"):
                raise ValueError(f"잘못된 billing_cycle: {billing_cycle}")
            sub.billing_cycle = billing_cycle
        sub.updated_at = datetime.now(timezone.utc).isoformat()
        logger.info("플랜 변경: id=%s → plan=%s", subscription_id, new_plan_id)
        return sub

    # ------------------------------------------------------------------
    # 취소
    # ------------------------------------------------------------------

    def cancel(self, subscription_id: str, reason: str = "") -> Subscription:
        """구독을 취소한다."""
        sub = self._subscriptions.get(subscription_id)
        if sub is None:
            raise ValueError(f"구독을 찾을 수 없습니다: {subscription_id}")
        if sub.status in (SubscriptionStatus.CANCELLED, SubscriptionStatus.EXPIRED):
            raise ValueError(f"이미 취소/만료된 구독입니다: {sub.status.value}")

        self._transition(sub, SubscriptionStatus.CANCELLED)
        sub.cancelled_at = datetime.now(timezone.utc).isoformat()
        sub.auto_renew = False
        if reason:
            sub.metadata["cancel_reason"] = reason
        logger.info("구독 취소: id=%s reason=%s", subscription_id, reason)
        return sub

    # ------------------------------------------------------------------
    # 자동 갱신
    # ------------------------------------------------------------------

    def renew(self, subscription_id: str) -> Subscription:
        """구독을 갱신한다 (결제 성공 후 호출)."""
        sub = self._subscriptions.get(subscription_id)
        if sub is None:
            raise ValueError(f"구독을 찾을 수 없습니다: {subscription_id}")
        if not sub.auto_renew:
            raise ValueError("자동 갱신이 비활성화된 구독입니다.")

        now = datetime.now(timezone.utc)
        period_days = 365 if sub.billing_cycle == "annual" else 30
        sub.current_period_start = now.isoformat()
        sub.current_period_end = (now + timedelta(days=period_days)).isoformat()
        sub.status = SubscriptionStatus.ACTIVE
        sub.updated_at = now.isoformat()
        logger.info("구독 갱신: id=%s next_end=%s", subscription_id, sub.current_period_end)
        return sub

    # ------------------------------------------------------------------
    # 상태 전환
    # ------------------------------------------------------------------

    def transition(self, subscription_id: str, new_status: str) -> Subscription:
        """구독 상태를 전환한다."""
        sub = self._subscriptions.get(subscription_id)
        if sub is None:
            raise ValueError(f"구독을 찾을 수 없습니다: {subscription_id}")
        try:
            target = SubscriptionStatus(new_status)
        except ValueError:
            raise ValueError(f"잘못된 상태: {new_status}")
        self._transition(sub, target)
        return sub

    def _transition(self, sub: Subscription, target: SubscriptionStatus) -> None:
        """내부 상태 전환 헬퍼."""
        allowed = _VALID_TRANSITIONS.get(sub.status, [])
        if target not in allowed:
            raise ValueError(
                f"상태 전환 불가: {sub.status.value} → {target.value}"
            )
        sub.status = target
        sub.updated_at = datetime.now(timezone.utc).isoformat()
