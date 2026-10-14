import os
import pytest
from src.proxy_buy import routes

pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="needs PG")


@pytest.fixture
def client(monkeypatch):
    from src.order_webhook import app
    routes._hits.clear()
    monkeypatch.setenv("CRON_SECRET", "s3")
    return app.test_client()


def _quoted(monkeypatch):
    monkeypatch.setattr(routes, "make_quote", lambda *a, **k: {
        "ok": True, "status": "quoted", "title": "T", "price_krw": 50000, "total_usd": "60.00"})


def test_request_queues_and_gate(client, monkeypatch):
    _quoted(monkeypatch)
    r = client.post("/proxy/request", json={"url": "https://www.musinsa.com/products/1", "email": "a@b.co"})
    assert r.get_json()["status"] == "received"
    assert client.get("/proxy/admin/queue").status_code == 403
    q = client.get("/proxy/admin/queue", headers={"X-Cron-Secret": "s3"}).get_json()["queue"]
    oid = [x for x in q if x["email"] == "a@b.co"][0]["id"]
    h = {"X-Cron-Secret": "s3"}
    assert client.post(f"/proxy/admin/{oid}/decide", json={"to": "purchased"}, headers=h).status_code == 409
    assert client.post(f"/proxy/admin/{oid}/decide", json={"to": "approved"}, headers=h).get_json()["ok"]


def test_bad_email_and_unquoted_not_queued(client, monkeypatch):
    assert client.post("/proxy/request", json={"url": "x", "email": "nope"}).status_code == 400
    monkeypatch.setattr(routes, "make_quote", lambda *a, **k: {"ok": False, "status": "manual_review"})
    r = client.post("/proxy/request", json={"url": "u", "email": "a@b.co"})
    assert r.get_json()["status"] == "manual_review"
