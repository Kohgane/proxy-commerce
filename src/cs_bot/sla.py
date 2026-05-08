from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from src.cs_bot.inbox_store import CSMessage, InboxStore

logger = logging.getLogger(__name__)


@dataclass
class SLAPolicy:
    refund_hours: int = int(os.getenv("CS_SLA_REFUND_HOURS", "2"))
    shipping_hours: int = int(os.getenv("CS_SLA_SHIPPING_HOURS", "12"))
    size_hours: int = int(os.getenv("CS_SLA_SIZE_HOURS", "24"))
    stock_hours: int = int(os.getenv("CS_SLA_SIZE_HOURS", "24"))
    general_hours: int = int(os.getenv("CS_SLA_GENERAL_HOURS", "48"))

    def hours_for_category(self, category: str) -> int:
        mapping = {
            "refund": self.refund_hours,
            "shipping": self.shipping_hours,
            "size": self.size_hours,
            "stock": self.stock_hours,
            "general": self.general_hours,
        }
        return int(mapping.get(category or "general", self.general_hours))


def compute_deadline(received_at: str, category: str, policy: SLAPolicy | None = None) -> str:
    policy = policy or SLAPolicy()
    base = _parse_dt(received_at) or datetime.now(timezone.utc)
    deadline = base + timedelta(hours=policy.hours_for_category(category))
    return deadline.isoformat()


def classify_sla(messages: list[CSMessage], now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    soon_threshold = now + timedelta(hours=1)
    nearing: list[CSMessage] = []
    overdue: list[CSMessage] = []

    for msg in messages:
        if msg.status in {"resolved", "auto_handled"}:
            continue
        deadline = _parse_dt(msg.sla_deadline)
        if deadline is None:
            continue
        if deadline < now:
            overdue.append(msg)
        elif deadline <= soon_threshold:
            nearing.append(msg)

    return {
        "nearing": nearing,
        "overdue": overdue,
        "nearing_count": len(nearing),
        "overdue_count": len(overdue),
    }


def check_and_notify_sla(store: InboxStore | None = None) -> dict:
    store = store or InboxStore()
    rows = store.list_messages(limit=5000)
    summary = classify_sla(rows)

    if summary["nearing_count"] or summary["overdue_count"]:
        try:
            from src.notifications.telegram import send_telegram

            send_telegram(
                "⏱ CS SLA 점검\n"
                f"- 임박: {summary['nearing_count']}건\n"
                f"- 초과: {summary['overdue_count']}건",
                urgency="warning" if summary["overdue_count"] == 0 else "critical",
            )
        except Exception as exc:
            logger.warning("SLA 알림 실패: %s", exc)
    return summary


def _parse_dt(raw: str) -> datetime | None:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None
