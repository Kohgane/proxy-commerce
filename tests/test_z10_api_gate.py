"""Z10(오너 2026-10-07): `/api/` 단일 관문 — email_marketing·returns 등 무인증 API 닫기.

Z8 범위 밖 발견(볼트 Z8 줄)을 전수로: 키 없이 응답하던 /api 블루프린트 약 85개. 관문 하나로 막고,
자기 인증이 있거나 공개가 맞는 3개(확장·헬스·문서)만 연다.
"""
from __future__ import annotations

import re

import pytest


@pytest.fixture
def closed(monkeypatch):
    monkeypatch.delenv("DASHBOARD_API_OPEN", raising=False)
    monkeypatch.delenv("DASHBOARD_API_KEY", raising=False)
    monkeypatch.setenv("FAMILY_EMAILS", "mom@example.com")
    from src.order_webhook import app
    return app


def _client(app, **sess):
    c = app.test_client()
    if sess:
        with c.session_transaction() as s:
            s.update(sess)
    return c


def test_named_endpoints_closed_without_key(closed):
    c = _client(closed)
    for url in ("/api/v1/email-campaigns/", "/api/v1/returns/", "/api/v1/cs/tickets", "/api/v1/users/"):
        r = c.get(url)
        assert r.status_code == 503, url
        assert "DASHBOARD_API_KEY" in r.get_json()["message"]
    # 상태를 바꾸는 POST도(예: 아무나 IP 차단) 뷰에 닿기 전에 막힌다
    r = c.post("/api/v1/security/ip-filter/block", json={"ip": "1.2.3.4"})
    assert r.status_code == 503


def test_key_wrong_is_401_and_right_key_passes(closed, monkeypatch):
    monkeypatch.setenv("DASHBOARD_API_KEY", "k-test")
    c = _client(closed)
    assert c.get("/api/v1/email-campaigns/").status_code == 401
    assert c.get("/api/v1/email-campaigns/", headers={"X-API-Key": "nope"}).status_code == 401
    assert c.get("/api/v1/email-campaigns/", headers={"X-API-Key": "k-test"}).status_code == 200


def test_shared_session_passes_public_signup_does_not(closed, monkeypatch):
    monkeypatch.setenv("DASHBOARD_API_KEY", "k-test")
    owner = _client(closed, user_id="o1", user_email="owner@example.com", user_role="admin")
    assert owner.get("/api/v1/email-campaigns/").status_code == 200
    family = _client(closed, user_id="m1", user_email="mom@example.com")
    assert family.get("/api/v1/returns/").status_code == 200
    stranger = _client(closed, user_id="s1", user_email="someone@example.com")
    assert stranger.get("/api/v1/returns/").status_code == 401


def test_open_blueprints_stay_open(closed):
    c = _client(closed)
    assert c.get("/api/v1/health").status_code == 200
    assert c.get("/api/docs/").status_code in (200, 308)
    r = c.get("/api/v1/collect/me")                      # 확장: 자기 토큰 검사(관문 503 아님)
    assert r.status_code == 401
    assert c.options("/api/v1/email-campaigns/").status_code != 503   # CORS 사전요청은 관문 밖


def test_every_api_get_rule_is_closed_except_open_set(closed):
    """전수: /api/ 아래 GET 규칙은 열린 3개 블루프린트 말고 전부 503(새 블루프린트가 열린 채 들어오는 걸 막는 래칫)."""
    from src.api.api_gate import OPEN_BLUEPRINTS
    c = _client(closed)
    leaks = []
    seen = 0
    for rule in closed.url_map.iter_rules():
        if not rule.rule.startswith("/api/") or "GET" not in rule.methods:
            continue
        bp = rule.endpoint.split(".")[0] if "." in rule.endpoint else ""
        if bp in OPEN_BLUEPRINTS:
            continue
        seen += 1
        code = c.get(re.sub(r"<[^>]*>", "x", rule.rule)).status_code
        if code != 503:
            leaks.append((rule.rule, code))
    assert seen > 300 and leaks == []


def test_open_set_is_exactly_three():
    from src.api.api_gate import OPEN_BLUEPRINTS
    assert OPEN_BLUEPRINTS == {"extension_api", "monitoring", "api_docs"}


def test_500_page_no_raw_api_link():
    import pathlib
    html = pathlib.Path("src/templates/errors/500.html").read_text(encoding="utf-8")
    assert "/api/v1/cs/tickets" not in html and "/seller/guide/business" in html
