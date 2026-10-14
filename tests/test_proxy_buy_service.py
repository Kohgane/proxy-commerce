import json

import pytest

from src.proxy_buy import service

HTML = ('<script id="__NEXT_DATA__">{"g":{"goodsNm":"오버핏 후드","salePrice":75000}}</script>')


@pytest.fixture(autouse=True)
def _stub(monkeypatch):
    monkeypatch.setattr(service, "fetch_html", lambda u: HTML)
    monkeypatch.setattr(service, "current_fx", lambda: 1020.0)
    monkeypatch.setenv("PROXY_INTL_SHIP_TABLE_JSON", json.dumps({"US": [[0.5, 15], [1, 22]]}))


def test_ssrf_blocked():
    for u in ("http://169.254.169.254/", "https://evil.com/www.musinsa.com",
              "https://www.musinsa.com@evil.com/", "file:///etc/passwd", "https://musinsa.com.evil.com/x"):
        assert service.make_quote(u)["status"] == "unsupported_site"


def test_quoted():
    r = service.make_quote("https://www.musinsa.com/products/1", "US", 0.5)
    assert r["status"] == "quoted" and r["valid_hours"] == 48
    assert "service fee" not in json.dumps(r).lower()


def test_pending_without_weight_or_table(monkeypatch):
    assert service.make_quote("https://www.musinsa.com/p/1", "US", None)["status"] == "pending_shipping"
    monkeypatch.delenv("PROXY_INTL_SHIP_TABLE_JSON")
    assert service.make_quote("https://www.musinsa.com/p/1", "US", 0.5)["status"] == "pending_shipping"


def test_no_live_fx_means_manual(monkeypatch):
    monkeypatch.setattr(service, "current_fx", lambda: None)
    assert service.make_quote("https://www.musinsa.com/p/1", "US", 0.5)["status"] == "manual_review"


def test_unparseable_page_means_manual(monkeypatch):
    monkeypatch.setattr(service, "fetch_html", lambda u: "<html></html>")
    assert service.make_quote("https://www.musinsa.com/p/1", "US", 0.5)["status"] == "manual_review"


def test_route_and_rate_limit():
    from flask import Flask
    from src.proxy_buy import routes
    routes._hits.clear()
    app = Flask(__name__)
    app.register_blueprint(routes.bp)
    c = app.test_client()
    r = c.post("/proxy/quote", json={"url": "https://www.musinsa.com/p/1", "options": {"weight_kg": 0.5}})
    assert r.status_code == 200 and r.get_json()["status"] == "quoted"
    assert c.post("/proxy/quote", json={}).status_code == 400
    for _ in range(12):
        last = c.post("/proxy/quote", json={"url": "x"})
    assert last.status_code == 429
