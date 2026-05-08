from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _msg(category: str = "general"):
    from src.cs_bot.inbox_store import CSMessage

    return CSMessage(
        message_id="m1",
        channel="telegram",
        direction="inbound",
        customer_id="c1",
        customer_name="kim",
        category=category,
        language="ko",
    )


def test_auto_send_guard_category_threshold(monkeypatch):
    monkeypatch.setenv("CS_AUTO_SEND", "1")
    monkeypatch.setenv("CS_AUTO_SEND_CATEGORIES", "general,shipping")
    monkeypatch.setenv("CS_AUTO_SEND_CONFIDENCE_THRESHOLD", "0.85")
    from src.cs_bot.auto_send_guard import should_auto_send

    ok, reason = should_auto_send(_msg("general"), "안내드립니다.", 0.9)
    assert ok is True
    assert reason == "ok"

    ok, reason = should_auto_send(_msg("refund"), "안내드립니다.", 0.9)
    assert ok is False
    assert reason == "category_not_allowed"

    ok, reason = should_auto_send(_msg("general"), "안내드립니다.", 0.5)
    assert ok is False
    assert reason == "low_confidence"


def test_auto_send_guard_daily_limit(tmp_path, monkeypatch):
    monkeypatch.setenv("CS_AUTO_SEND", "1")
    monkeypatch.setenv("CS_AUTO_SEND_CATEGORIES", "general")
    monkeypatch.setenv("CS_AUTO_SEND_DAILY_LIMIT", "1")
    monkeypatch.setenv("CS_INBOX_FALLBACK_PATH", str(tmp_path / "inbox.jsonl"))
    from src.cs_bot.auto_send_guard import should_auto_send
    from src.cs_bot.inbox_store import CSMessage, InboxStore

    now = datetime.now(timezone.utc).isoformat()
    InboxStore(str(tmp_path / "inbox.jsonl")).upsert(
        CSMessage(
            message_id="m_old",
            channel="telegram",
            direction="inbound",
            customer_id="c1",
            customer_name="kim",
            category="general",
            status="auto_handled",
            responded_at=now,
        )
    )
    ok, reason = should_auto_send(_msg("general"), "안내드립니다.", 0.99)
    assert ok is False
    assert reason == "daily_limit_exceeded"
