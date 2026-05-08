from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_sla_deadline_by_category(monkeypatch):
    monkeypatch.setenv("CS_SLA_REFUND_HOURS", "2")
    from src.cs_bot.sla import compute_deadline

    base = "2026-05-08T00:00:00+00:00"
    deadline = compute_deadline(base, "refund")
    assert deadline.startswith("2026-05-08T02:00:00")


def test_sla_nearing_and_overdue_classification():
    from src.cs_bot.inbox_store import CSMessage
    from src.cs_bot.sla import classify_sla

    now = datetime.now(timezone.utc)
    rows = [
        CSMessage(message_id="1", channel="telegram", direction="inbound", customer_id="u1", customer_name="A", sla_deadline=(now + timedelta(minutes=20)).isoformat()),
        CSMessage(message_id="2", channel="telegram", direction="inbound", customer_id="u2", customer_name="B", sla_deadline=(now - timedelta(minutes=5)).isoformat()),
    ]
    summary = classify_sla(rows, now=now)
    assert summary["nearing_count"] == 1
    assert summary["overdue_count"] == 1
