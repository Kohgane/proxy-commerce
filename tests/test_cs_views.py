from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_cs_pages_200(tmp_path, monkeypatch):
    monkeypatch.setenv("CS_FAQ_FALLBACK_PATH", str(tmp_path / "cs_faq.jsonl"))
    monkeypatch.setenv("CS_INBOX_FALLBACK_PATH", str(tmp_path / "cs_inbox.jsonl"))
    from src.order_webhook import app

    app.config["TESTING"] = True
    with app.test_client() as client:
        assert client.get("/seller/cs/inbox").status_code == 200
        assert client.get("/seller/cs/faq").status_code == 200


def test_cs_role_check_forbidden_guest(tmp_path, monkeypatch):
    monkeypatch.setenv("CS_FAQ_FALLBACK_PATH", str(tmp_path / "cs_faq.jsonl"))
    monkeypatch.setenv("CS_INBOX_FALLBACK_PATH", str(tmp_path / "cs_inbox.jsonl"))
    from src.order_webhook import app

    app.config["TESTING"] = True
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user_role"] = "guest"
        assert client.get("/seller/cs/inbox").status_code == 403
