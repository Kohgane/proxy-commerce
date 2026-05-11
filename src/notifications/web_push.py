"""src/notifications/web_push.py — Web Push (VAPID) 알림 모듈 (Phase 147).

기능:
  - VAPID 키 생성/저장 (환경변수 기반)
  - 구독 정보 DB 저장 (push_subscriptions 테이블 추상화)
  - 푸시 전송 함수 (pywebpush 또는 stub)
  - 트리거: 신규 주문 / CS 긴급 / 배송 지연 / 광고 ROAS 급변

환경변수:
  WEB_PUSH_VAPID_PUBLIC   — VAPID 공개키 (Base64url)
  WEB_PUSH_VAPID_PRIVATE  — VAPID 비밀키 (Base64url)
  WEB_PUSH_CONTACT_EMAIL  — 관리자 연락처 이메일
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# VAPID 설정 로드
# ---------------------------------------------------------------------------

def get_vapid_public_key() -> str:
    return os.getenv("WEB_PUSH_VAPID_PUBLIC", "")


def get_vapid_private_key() -> str:
    return os.getenv("WEB_PUSH_VAPID_PRIVATE", "")


def get_vapid_contact() -> str:
    email = os.getenv("WEB_PUSH_CONTACT_EMAIL", "admin@kohganepercentiii.com")
    return f"mailto:{email}"


def vapid_configured() -> bool:
    """VAPID 키가 환경변수에 설정되어 있는지 확인."""
    return bool(get_vapid_public_key() and get_vapid_private_key())


def generate_vapid_keys() -> dict[str, str]:
    """VAPID 키쌍 생성 (py_vapid/cryptography 없으면 stub 반환).

    운영자가 생성한 뒤 환경변수에 직접 입력해야 합니다.
    """
    try:
        from py_vapid import Vapid  # type: ignore

        v = Vapid()
        v.generate_keys()
        return {
            "public": v.public_key.decode("utf-8"),
            "private": v.private_key.decode("utf-8"),
        }
    except Exception:
        # cryptography 없으면 안내 메시지 반환
        return {
            "public": "(생성 불가: py-vapid 미설치)",
            "private": "(생성 불가: py-vapid 미설치)",
            "hint": "pip install py-vapid 설치 후 재시도하거나 https://web-push-codelab.glitch.me 에서 직접 생성",
        }


# ---------------------------------------------------------------------------
# 구독 정보 저장소 (파일 기반 fallback)
# ---------------------------------------------------------------------------

_SUBSCRIPTIONS_PATH = os.getenv(
    "PUSH_SUBSCRIPTIONS_PATH", "data/push_subscriptions.jsonl"
)


@dataclass
class PushSubscription:
    """단일 Web Push 구독 정보."""

    user_id: str
    endpoint: str
    p256dh: str
    auth: str
    categories: list[str] = field(default_factory=lambda: ["order", "cs", "shipping", "ads"])
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        return asdict(self)


class PushSubscriptionStore:
    """Web Push 구독 목록 파일 기반 저장소."""

    def __init__(self, path: str = _SUBSCRIPTIONS_PATH):
        self._path = path
        os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)

    def _load(self) -> list[dict]:
        if not os.path.exists(self._path):
            return []
        items = []
        try:
            with open(self._path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            items.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
        except OSError:
            pass
        return items

    def _save_all(self, items: list[dict]) -> None:
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                for item in items:
                    f.write(json.dumps(item, ensure_ascii=False) + "\n")
        except OSError as exc:
            logger.warning("push_subscriptions 저장 실패: %s", exc)

    def subscribe(self, sub: PushSubscription) -> None:
        """구독 추가 또는 업데이트 (endpoint 기준 dedup)."""
        items = self._load()
        items = [i for i in items if i.get("endpoint") != sub.endpoint]
        items.append(sub.to_dict())
        self._save_all(items)

    def unsubscribe(self, endpoint: str) -> bool:
        """구독 삭제. 삭제 성공 시 True."""
        items = self._load()
        new_items = [i for i in items if i.get("endpoint") != endpoint]
        if len(new_items) == len(items):
            return False
        self._save_all(new_items)
        return True

    def list_all(self) -> list[PushSubscription]:
        return [
            PushSubscription(
                user_id=i.get("user_id", ""),
                endpoint=i.get("endpoint", ""),
                p256dh=i.get("p256dh", ""),
                auth=i.get("auth", ""),
                categories=i.get("categories", ["order", "cs", "shipping", "ads"]),
                created_at=i.get("created_at", ""),
            )
            for i in self._load()
        ]

    def list_for_user(self, user_id: str) -> list[PushSubscription]:
        return [s for s in self.list_all() if s.user_id == user_id]

    def count(self) -> int:
        return len(self._load())


# ---------------------------------------------------------------------------
# 푸시 전송 함수
# ---------------------------------------------------------------------------

def send_push(
    subscription: PushSubscription,
    title: str,
    body: str,
    url: str = "/seller/dashboard",
    icon: str = "/seller/static/icon-192.png",
    data: dict[str, Any] | None = None,
) -> bool:
    """단일 구독자에게 Web Push 전송.

    pywebpush 없으면 stub 모드로 로그만 기록.
    """
    payload = json.dumps({
        "title": title,
        "body": body,
        "url": url,
        "icon": icon,
        **(data or {}),
    })

    if not vapid_configured():
        logger.info("[STUB] Web Push: %s → %s (VAPID 미설정)", subscription.user_id, title)
        return True

    try:
        from pywebpush import webpush, WebPushException  # type: ignore

        webpush(
            subscription_info={
                "endpoint": subscription.endpoint,
                "keys": {
                    "p256dh": subscription.p256dh,
                    "auth": subscription.auth,
                },
            },
            data=payload,
            vapid_private_key=get_vapid_private_key(),
            vapid_claims={
                "sub": get_vapid_contact(),
            },
        )
        return True
    except Exception as exc:
        logger.warning("Web Push 전송 실패 (user=%s): %s", subscription.user_id, exc)
        return False


def broadcast_push(
    title: str,
    body: str,
    category: str = "order",
    url: str = "/seller/dashboard",
    data: dict[str, Any] | None = None,
) -> dict[str, int]:
    """카테고리 구독자 전체에게 브로드캐스트.

    Returns: {"sent": N, "failed": M}
    """
    store = PushSubscriptionStore()
    subs = [s for s in store.list_all() if category in s.categories]
    sent = failed = 0
    for sub in subs:
        ok = send_push(sub, title=title, body=body, url=url, data=data)
        if ok:
            sent += 1
        else:
            failed += 1
    return {"sent": sent, "failed": failed}


# ---------------------------------------------------------------------------
# 트리거 함수
# ---------------------------------------------------------------------------

def notify_new_order(order_id: str, amount_krw: int) -> None:
    broadcast_push(
        title="🛒 신규 주문",
        body=f"주문 #{order_id} ({amount_krw:,}원)",
        category="order",
        url="/seller/orders",
    )


def notify_cs_urgent(message_id: str, preview: str) -> None:
    broadcast_push(
        title="🚨 긴급 CS 문의",
        body=preview[:80],
        category="cs",
        url="/seller/cs/inbox",
    )


def notify_shipping_delay(order_id: str) -> None:
    broadcast_push(
        title="⚠️ 배송 지연",
        body=f"주문 #{order_id} 배송 지연 감지",
        category="shipping",
        url="/seller/shipping/tracking",
    )


def notify_roas_change(channel: str, roas: float, prev_roas: float) -> None:
    direction = "↑" if roas > prev_roas else "↓"
    broadcast_push(
        title=f"📊 ROAS 급변 ({channel})",
        body=f"{prev_roas:.2f} → {roas:.2f} {direction}",
        category="ads",
        url="/seller/ads/campaigns",
    )


# ---------------------------------------------------------------------------
# 상태 요약
# ---------------------------------------------------------------------------

def push_status() -> dict:
    """진단 카드용 Web Push 상태 요약."""
    store = PushSubscriptionStore()
    return {
        "vapid_configured": vapid_configured(),
        "subscriber_count": store.count(),
        "vapid_public_hint": (
            "..." + get_vapid_public_key()[-8:] if len(get_vapid_public_key()) >= 8 else "미설정"
        ),
    }
