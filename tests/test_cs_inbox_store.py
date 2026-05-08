from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_inbox_upsert_and_get(tmp_path):
    from src.cs_bot.inbox_store import CSMessage, InboxStore

    store = InboxStore(str(tmp_path / "cs_inbox.jsonl"))
    msg = CSMessage(
        message_id="msg_1",
        channel="telegram",
        direction="inbound",
        customer_id="u1",
        customer_name="홍길동",
        body="환불 가능한가요",
    )
    store.upsert(msg)
    got = store.get("msg_1")
    assert got is not None
    assert got.body == "환불 가능한가요"


def test_inbox_stats_24h(tmp_path):
    from src.cs_bot.inbox_store import CSMessage, InboxStore

    now = datetime.now(timezone.utc)
    store = InboxStore(str(tmp_path / "cs_inbox.jsonl"))
    store.upsert(
        CSMessage(
            message_id="m1",
            channel="telegram",
            direction="inbound",
            customer_id="1",
            customer_name="A",
            body="배송",
            received_at=(now - timedelta(hours=1)).isoformat(),
            responded_at=now.isoformat(),
            status="resolved",
        )
    )
    store.upsert(
        CSMessage(
            message_id="m2",
            channel="telegram",
            direction="inbound",
            customer_id="2",
            customer_name="B",
            body="환불",
            priority=2,
            received_at=(now - timedelta(hours=2)).isoformat(),
            status="open",
        )
    )
    stats = store.stats_24h()
    assert stats["new_24h"] == 2
    assert stats["unanswered"] == 1
    assert stats["urgent_unanswered"] == 1
