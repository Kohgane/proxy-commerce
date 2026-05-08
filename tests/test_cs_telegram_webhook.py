from __future__ import annotations

import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_telegram_webhook_secret_validation(tmp_path, monkeypatch):
    monkeypatch.setenv("CS_INBOX_FALLBACK_PATH", str(tmp_path / "cs_inbox.jsonl"))
    monkeypatch.setenv("CS_FAQ_FALLBACK_PATH", str(tmp_path / "cs_faq.jsonl"))
    monkeypatch.setenv("CS_TELEGRAM_WEBHOOK_SECRET", "secret123")
    from src.order_webhook import app

    app.config["TESTING"] = True
    payload = {"message": {"message_id": 1, "text": "환불 문의", "chat": {"id": 101}, "from": {"first_name": "김"}}}
    with app.test_client() as client:
        bad = client.post("/webhooks/telegram/cs", json=payload)
        assert bad.status_code == 403

        with patch("src.cs_bot.inbound_telegram.send_telegram", return_value=True):
            ok = client.post("/webhooks/telegram/cs", json=payload, headers={"X-Telegram-Bot-Api-Secret-Token": "secret123"})
        assert ok.status_code == 200
        assert ok.get_json()["ok"] is True


def test_telegram_webhook_saves_message(tmp_path, monkeypatch):
    monkeypatch.setenv("CS_INBOX_FALLBACK_PATH", str(tmp_path / "cs_inbox.jsonl"))
    monkeypatch.setenv("CS_FAQ_FALLBACK_PATH", str(tmp_path / "cs_faq.jsonl"))
    monkeypatch.delenv("CS_TELEGRAM_WEBHOOK_SECRET", raising=False)
    from src.order_webhook import app
    from src.cs_bot.inbox_store import InboxStore

    app.config["TESTING"] = True
    payload = {"message": {"message_id": 10, "text": "배송 언제", "chat": {"id": 1001}, "from": {"first_name": "이"}}}
    with patch("src.cs_bot.inbound_telegram.send_telegram", return_value=True):
        with app.test_client() as client:
            resp = client.post("/webhooks/telegram/cs", json=payload)
            assert resp.status_code == 200
    assert InboxStore(str(tmp_path / "cs_inbox.jsonl")).get("tg_10") is not None
