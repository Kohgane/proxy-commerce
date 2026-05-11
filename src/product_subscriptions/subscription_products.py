"""src/product_subscriptions/subscription_products.py — 정기구독 상품 관리 (Phase 148).

기능:
  - 상품에 "정기구독 가능" 플래그
  - 주기 옵션: 1주/2주/4주/8주
  - 자동 결제 (PG 연동 — 기본 mock)
  - 다음 결제 7일 전 알림 트리거
  - 일시정지/스킵/해지

환경변수:
  SUBSCRIPTION_ENABLED        — 1/0 (기본 1)
  SUBSCRIPTION_PG_PROVIDER    — mock | tosspayments | iamport (기본 mock)
  SUBSCRIPTION_RETRY_DAYS     — 결제 실패 재시도 간격(일) (기본 3)
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import List

logger = logging.getLogger(__name__)

_SUBSCRIPTIONS_PATH = os.getenv(
    "PRODUCT_SUBSCRIPTIONS_PATH", "data/product_subscriptions.jsonl"
)


class SubscriptionCycle(str, Enum):
    WEEKLY = "1w"
    BIWEEKLY = "2w"
    MONTHLY = "4w"
    BIMONTHLY = "8w"

    @property
    def days(self) -> int:
        return {"1w": 7, "2w": 14, "4w": 28, "8w": 56}[self.value]

    @property
    def label(self) -> str:
        return {"1w": "1주", "2w": "2주", "4w": "4주", "8w": "8주"}[self.value]


class SubscriptionStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    CANCELLED = "cancelled"


@dataclass
class ProductSubscription:
    subscription_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = ""
    product_id: str = ""
    product_name: str = ""
    cycle: SubscriptionCycle = SubscriptionCycle.MONTHLY
    status: SubscriptionStatus = SubscriptionStatus.ACTIVE
    quantity: int = 1
    unit_price: int = 0
    started_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    next_billing_at: str = field(
        default_factory=lambda: (
            datetime.now(timezone.utc) + timedelta(days=28)
        ).isoformat()
    )
    last_billed_at: str | None = None
    skip_count: int = 0
    payment_fail_count: int = 0
    pg_subscription_key: str = ""


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None


class ProductSubscriptionManager:
    """정기구독 상품 관리자."""

    def __init__(self, path: str = _SUBSCRIPTIONS_PATH) -> None:
        self._path = path

    @property
    def enabled(self) -> bool:
        return os.getenv("SUBSCRIPTION_ENABLED", "1") == "1"

    @property
    def pg_provider(self) -> str:
        return os.getenv("SUBSCRIPTION_PG_PROVIDER", "mock")

    @property
    def retry_days(self) -> int:
        return int(os.getenv("SUBSCRIPTION_RETRY_DAYS", "3"))

    def _load(self) -> List[ProductSubscription]:
        subs: List[ProductSubscription] = []
        try:
            with open(self._path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    d = json.loads(line)
                    d["cycle"] = SubscriptionCycle(d.get("cycle", "4w"))
                    d["status"] = SubscriptionStatus(d.get("status", "active"))
                    subs.append(ProductSubscription(**d))
        except FileNotFoundError:
            pass
        except Exception as exc:
            logger.warning("product_subscriptions 로드 실패: %s", exc)
        return subs

    def _save(self, subs: List[ProductSubscription]) -> None:
        os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
        tmp = self._path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                for sub in subs:
                    d = asdict(sub)
                    d["cycle"] = sub.cycle.value
                    d["status"] = sub.status.value
                    f.write(json.dumps(d, ensure_ascii=False) + "\n")
            os.replace(tmp, self._path)
        except Exception as exc:
            logger.warning("product_subscriptions 저장 실패: %s", exc)

    def subscribe(self, sub: ProductSubscription) -> ProductSubscription:
        subs = self._load()
        subs.append(sub)
        self._save(subs)
        logger.info("구독 생성: user=%s product=%s", sub.user_id, sub.product_id)
        return sub

    def cancel(self, subscription_id: str) -> bool:
        subs = self._load()
        for s in subs:
            if s.subscription_id == subscription_id:
                s.status = SubscriptionStatus.CANCELLED
                self._save(subs)
                return True
        return False

    def pause(self, subscription_id: str) -> bool:
        subs = self._load()
        for s in subs:
            if s.subscription_id == subscription_id and s.status == SubscriptionStatus.ACTIVE:
                s.status = SubscriptionStatus.PAUSED
                self._save(subs)
                return True
        return False

    def resume(self, subscription_id: str) -> bool:
        subs = self._load()
        for s in subs:
            if s.subscription_id == subscription_id and s.status == SubscriptionStatus.PAUSED:
                s.status = SubscriptionStatus.ACTIVE
                self._save(subs)
                return True
        return False

    def skip_next(self, subscription_id: str) -> bool:
        """다음 결제 주기 스킵."""
        subs = self._load()
        for s in subs:
            if s.subscription_id == subscription_id and s.status == SubscriptionStatus.ACTIVE:
                next_dt = _parse_dt(s.next_billing_at)
                if next_dt:
                    s.next_billing_at = (next_dt + timedelta(days=s.cycle.days)).isoformat()
                s.skip_count += 1
                self._save(subs)
                return True
        return False

    def list_for_user(self, user_id: str) -> List[ProductSubscription]:
        return [s for s in self._load() if s.user_id == user_id]

    def list_active(self) -> List[ProductSubscription]:
        return [s for s in self._load() if s.status == SubscriptionStatus.ACTIVE]

    def upcoming_billing(self, days_ahead: int = 7) -> List[ProductSubscription]:
        """향후 days_ahead일 이내 결제 예정 구독 목록."""
        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(days=days_ahead)
        result = []
        for s in self.list_active():
            dt = _parse_dt(s.next_billing_at)
            if dt and now <= dt <= cutoff:
                result.append(s)
        return result

    def process_billing_mock(self, subscription_id: str) -> dict:
        """Mock 결제 처리."""
        subs = self._load()
        for s in subs:
            if s.subscription_id == subscription_id:
                # mock: 항상 성공
                now = datetime.now(timezone.utc)
                s.last_billed_at = now.isoformat()
                s.next_billing_at = (now + timedelta(days=s.cycle.days)).isoformat()
                s.payment_fail_count = 0
                self._save(subs)
                logger.info("mock 결제 완료: %s", subscription_id)
                return {"ok": True, "provider": "mock", "subscription_id": subscription_id}
        return {"ok": False, "error": "구독을 찾을 수 없습니다."}

    def summary(self) -> dict:
        subs = self._load()
        active = [s for s in subs if s.status == SubscriptionStatus.ACTIVE]
        now = datetime.now(timezone.utc)
        week_start = now - timedelta(days=7)
        billed_this_week = []
        for s in subs:
            if s.last_billed_at:
                billed_dt = _parse_dt(s.last_billed_at)
                if billed_dt and billed_dt >= week_start:
                    billed_this_week.append(s)
        failed = [s for s in active if s.payment_fail_count > 0]
        cancelled_30d = [
            s for s in subs
            if s.status == SubscriptionStatus.CANCELLED
        ]
        return {
            "enabled": self.enabled,
            "pg_provider": self.pg_provider,
            "active_count": len(active),
            "billed_this_week": len(billed_this_week),
            "failed_count": len(failed),
            "cancelled_count": len(cancelled_30d),
            "total_count": len(subs),
        }
