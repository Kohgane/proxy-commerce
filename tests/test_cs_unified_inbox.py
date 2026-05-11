from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.cs.unified_inbox import UnifiedInbox, UnifiedMessage


def test_unified_inbox_priority_and_filter():
    inbox = UnifiedInbox()
    inbox.push(UnifiedMessage(message_id="m1", channel="email", body="환불 요청", status="open"))
    inbox.push(UnifiedMessage(message_id="m2", channel="kakao", body="배송 문의", status="resolved"))

    high = inbox.list_messages(priority="high")
    assert len(high) == 1
    assert high[0]["message_id"] == "m1"


def test_unified_inbox_sla_summary():
    inbox = UnifiedInbox()
    old = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    inbox.push(UnifiedMessage(message_id="m3", channel="market", body="문의", status="open", received_at=old))
    summary = inbox.summary_24h()
    assert summary["unanswered"] == 1
    assert summary["sla_violations"] == 1
