from __future__ import annotations

import os
from datetime import datetime, timezone

from src.cs_bot.inbox_store import CSMessage, InboxStore


def should_auto_send(msg: CSMessage, suggested: str, confidence: float) -> tuple[bool, str]:
    """(can_send, reason) 반환. False면 reason에 사유."""
    if os.getenv("CS_AUTO_SEND", "0") != "1":
        return False, "auto_send_disabled"

    allowed = [x.strip() for x in os.getenv("CS_AUTO_SEND_CATEGORIES", "general,shipping").split(",") if x.strip()]
    if (msg.category or "general") not in set(allowed):
        return False, "category_not_allowed"

    try:
        threshold = float(os.getenv("CS_AUTO_SEND_CONFIDENCE_THRESHOLD", "0.85"))
    except Exception:
        return False, "invalid_confidence_threshold"
    if float(confidence) < threshold:
        return False, "low_confidence"

    if not (suggested or "").strip():
        return False, "empty_reply"
    if "{{" in suggested and "}}" in suggested:
        return False, "template_unresolved"

    try:
        limit = int(os.getenv("CS_AUTO_SEND_DAILY_LIMIT", "20"))
    except Exception:
        return False, "invalid_daily_limit"
    if _today_auto_sent_count() >= limit:
        return False, "daily_limit_exceeded"

    return True, "ok"


def _today_auto_sent_count() -> int:
    now = datetime.now(timezone.utc).date()
    rows = InboxStore().list_messages(limit=5000)
    count = 0
    for row in rows:
        if row.status != "auto_handled":
            continue
        if not row.responded_at:
            continue
        try:
            dt = datetime.fromisoformat(str(row.responded_at).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt.astimezone(timezone.utc).date() == now:
                count += 1
        except Exception:
            continue
    return count
