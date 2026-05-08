from __future__ import annotations
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_cs_stats_page_200(tmp_path, monkeypatch):
    monkeypatch.setenv("CS_FAQ_FALLBACK_PATH", str(tmp_path / "cs_faq.jsonl"))
    monkeypatch.setenv("CS_INBOX_FALLBACK_PATH", str(tmp_path / "cs_inbox.jsonl"))
    from src.order_webhook import app
    app.config["TESTING"] = True
    with app.test_client() as client:
        resp = client.get("/seller/cs/stats")
        assert resp.status_code == 200


def test_admin_cs_stats_json(tmp_path, monkeypatch):
    monkeypatch.setenv("CS_FAQ_FALLBACK_PATH", str(tmp_path / "cs_faq.jsonl"))
    monkeypatch.setenv("CS_INBOX_FALLBACK_PATH", str(tmp_path / "cs_inbox.jsonl"))
    from src.order_webhook import app
    app.config["TESTING"] = True
    with app.test_client() as client:
        resp = client.get("/admin/cs/stats")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data is not None
        assert "ok" in data


def test_admin_cs_check_sla(tmp_path, monkeypatch):
    monkeypatch.setenv("CS_FAQ_FALLBACK_PATH", str(tmp_path / "cs_faq.jsonl"))
    monkeypatch.setenv("CS_INBOX_FALLBACK_PATH", str(tmp_path / "cs_inbox.jsonl"))
    from src.order_webhook import app
    app.config["TESTING"] = True
    with app.test_client() as client:
        resp = client.post("/admin/cs/check-sla")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True


def test_admin_cs_rebuild_embeddings_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("CS_FAQ_FALLBACK_PATH", str(tmp_path / "cs_faq.jsonl"))
    monkeypatch.setenv("CS_INBOX_FALLBACK_PATH", str(tmp_path / "cs_inbox.jsonl"))
    monkeypatch.setenv("CS_EMBEDDING_PROVIDER", "disabled")
    from src.order_webhook import app
    app.config["TESTING"] = True
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user_id"] = "admin"
        resp = client.post("/admin/cs/rebuild-embeddings")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["updated"] == 0


def test_admin_cs_poll_now_no_active_channels(tmp_path, monkeypatch):
    monkeypatch.setenv("CS_FAQ_FALLBACK_PATH", str(tmp_path / "cs_faq.jsonl"))
    monkeypatch.setenv("CS_INBOX_FALLBACK_PATH", str(tmp_path / "cs_inbox.jsonl"))
    monkeypatch.delenv("CS_EMAIL_IMAP_HOST", raising=False)
    monkeypatch.delenv("COUPANG_ACCESS_KEY", raising=False)
    monkeypatch.delenv("NAVER_TALKTALK_BOT_ID", raising=False)
    monkeypatch.delenv("ELEVEN_API_KEY", raising=False)
    monkeypatch.delenv("ELEVEN_OPENAPIKEY", raising=False)
    from src.order_webhook import app
    app.config["TESTING"] = True
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user_id"] = "admin"
        resp = client.post("/admin/cs/poll-now")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["result"]["total_new"] == 0
