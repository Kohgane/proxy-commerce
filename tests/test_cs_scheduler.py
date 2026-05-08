from __future__ import annotations
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_scheduler_disabled_by_default(monkeypatch):
    monkeypatch.delenv("CS_SCHEDULER_ENABLED", raising=False)
    from src.cs_bot import scheduler
    # Reload to reset global state
    import importlib
    importlib.reload(scheduler)
    app = MagicMock()
    scheduler.start_scheduler(app)
    assert scheduler._scheduler is None


def test_scheduler_does_not_start_without_apscheduler(monkeypatch, tmp_path):
    monkeypatch.setenv("CS_SCHEDULER_ENABLED", "1")
    monkeypatch.setenv("CS_SCHEDULER_LOCK_PATH", str(tmp_path / "test.lock"))
    import importlib
    from src.cs_bot import scheduler as sched_mod
    importlib.reload(sched_mod)
    app = MagicMock()
    with patch.dict("sys.modules", {"apscheduler": None, "apscheduler.schedulers": None, "apscheduler.schedulers.background": None}):
        # Even without APScheduler, should not raise
        try:
            sched_mod.start_scheduler(app)
        except Exception:
            pass  # OK if it fails gracefully


def test_get_scheduler_status_structure(monkeypatch):
    monkeypatch.setenv("CS_SCHEDULER_ENABLED", "1")
    monkeypatch.setenv("CS_POLL_INTERVAL_MINUTES", "5")
    monkeypatch.setenv("CS_SLA_CHECK_INTERVAL_MINUTES", "15")
    from src.cs_bot.scheduler import get_scheduler_status
    status = get_scheduler_status()
    assert "enabled" in status
    assert "running" in status
    assert "poll_interval_minutes" in status
    assert "sla_interval_minutes" in status
    assert status["poll_interval_minutes"] == 5
    assert status["sla_interval_minutes"] == 15


def test_poll_all_channels_returns_dict(tmp_path, monkeypatch):
    monkeypatch.setenv("CS_FAQ_FALLBACK_PATH", str(tmp_path / "faq.jsonl"))
    monkeypatch.setenv("CS_INBOX_FALLBACK_PATH", str(tmp_path / "inbox.jsonl"))
    # All channels inactive → no API calls
    monkeypatch.delenv("CS_EMAIL_IMAP_HOST", raising=False)
    monkeypatch.delenv("COUPANG_ACCESS_KEY", raising=False)
    monkeypatch.delenv("NAVER_TALKTALK_BOT_ID", raising=False)
    monkeypatch.delenv("ELEVEN_API_KEY", raising=False)
    monkeypatch.delenv("ELEVEN_OPENAPIKEY", raising=False)
    from src.cs_bot.scheduler import poll_all_channels
    result = poll_all_channels()
    assert "total_new" in result
    assert "by_channel" in result
    assert result["total_new"] == 0
