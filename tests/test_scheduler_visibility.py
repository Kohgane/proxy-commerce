from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_scheduler_status_exposes_jobs(monkeypatch, tmp_path):
    from flask import Flask
    import importlib
    from src.cs_bot import scheduler as sched_mod

    monkeypatch.setenv("CS_SCHEDULER_ENABLED", "1")
    monkeypatch.setenv("CS_SCHEDULER_LOCK_PATH", str(tmp_path / "sched.lock"))
    monkeypatch.setenv("SCHEDULER_LEADER_TTL_SECONDS", "90")
    monkeypatch.setenv("SCHEDULER_HEARTBEAT_SECONDS", "30")
    monkeypatch.setenv("PRICING_MONITOR_ENABLED", "0")
    importlib.reload(sched_mod)

    app = Flask(__name__)
    sched_mod.start_scheduler(app)
    status = sched_mod.get_scheduler_status()
    assert "jobs" in status
    ids = {j.get("id") for j in status.get("jobs", [])}
    assert {"cs_poll", "cs_sla", "pricing_monitor", "fx_alert"}.issubset(ids)
    assert "scheduler_heartbeat" not in ids
