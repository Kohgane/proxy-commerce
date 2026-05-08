from __future__ import annotations
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_cs_mobile_page_200(tmp_path, monkeypatch):
    monkeypatch.setenv("CS_FAQ_FALLBACK_PATH", str(tmp_path / "cs_faq.jsonl"))
    monkeypatch.setenv("CS_INBOX_FALLBACK_PATH", str(tmp_path / "cs_inbox.jsonl"))
    from src.order_webhook import app
    app.config["TESTING"] = True
    with app.test_client() as client:
        resp = client.get("/seller/cs/mobile")
        assert resp.status_code == 200


def test_cs_mobile_manifest_200(tmp_path, monkeypatch):
    monkeypatch.setenv("CS_FAQ_FALLBACK_PATH", str(tmp_path / "cs_faq.jsonl"))
    monkeypatch.setenv("CS_INBOX_FALLBACK_PATH", str(tmp_path / "cs_inbox.jsonl"))
    from src.order_webhook import app
    app.config["TESTING"] = True
    with app.test_client() as client:
        # Blueprint url_prefix + static_url_path = /seller/seller/static/
        resp = client.get("/seller/seller/static/manifest.json")
        assert resp.status_code == 200


def test_cs_mobile_sw_200(tmp_path, monkeypatch):
    monkeypatch.setenv("CS_FAQ_FALLBACK_PATH", str(tmp_path / "cs_faq.jsonl"))
    monkeypatch.setenv("CS_INBOX_FALLBACK_PATH", str(tmp_path / "cs_inbox.jsonl"))
    from src.order_webhook import app
    app.config["TESTING"] = True
    with app.test_client() as client:
        resp = client.get("/seller/seller/static/sw.js")
        assert resp.status_code == 200


def test_cs_mobile_forbidden_guest(tmp_path, monkeypatch):
    monkeypatch.setenv("CS_FAQ_FALLBACK_PATH", str(tmp_path / "cs_faq.jsonl"))
    monkeypatch.setenv("CS_INBOX_FALLBACK_PATH", str(tmp_path / "cs_inbox.jsonl"))
    from src.order_webhook import app
    app.config["TESTING"] = True
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user_role"] = "guest"
        resp = client.get("/seller/cs/mobile")
        assert resp.status_code == 403
