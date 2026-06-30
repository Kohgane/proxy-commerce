"""tests/test_v40_d_passkey.py — v40-D: 패스키(WebAuthn) 등록·인증.

구글 OAuth는 기존(src/auth/oauth_provider.py 'google'). 패스키는 신규(기기 저장 공개키).
보안: 챌린지 1회용·origin/RP 검증·자격증명 서버에만. 폴백: 미지원/미등록 → 구글·이메일.
※ webauthn 라이브러리는 collect-only(CI)에서 지연 import — 라우트 함수 내부에서만 import(미설치 안전).
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture
def client():
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    from src.order_webhook import app
    with app.test_client() as c:
        yield c


def test_passkey_routes_registered(client):
    rules = {str(r.rule) for r in client.application.url_map.iter_rules()}
    for r in ("/auth/passkey/register/options", "/auth/passkey/register/verify",
              "/auth/passkey/login/options", "/auth/passkey/login/verify",
              "/auth/passkey/list", "/auth/passkey/delete"):
        assert r in rules, f"패스키 라우트 누락: {r}"


def test_register_requires_login(client):
    r = client.post("/auth/passkey/register/options", json={})
    assert r.status_code == 401


def test_login_options_issues_challenge(client):
    r = client.post("/auth/passkey/login/options", json={})
    assert r.status_code == 200
    d = r.get_json()
    assert d["ok"] and "challenge" in d["options"]
    # 챌린지가 세션에 1회용으로 보관(서버 바인딩)
    with client.session_transaction() as s:
        assert s.get("_pk_auth_challenge")


def test_login_verify_unknown_credential_honest(client):
    # 먼저 옵션으로 챌린지 세팅
    client.post("/auth/passkey/login/options", json={})
    r = client.post("/auth/passkey/login/verify", json={"credential": {"id": "nope", "rawId": "nope"}})
    assert r.status_code == 400
    assert "등록되지 않은" in r.get_json().get("error", "")   # 정직(가짜 로그인 0)


def test_store_alias_scope_and_honest():
    import src.auth.passkey_store as ps
    ps._in_memory[:] = []
    ps.add_credential(credential_id="c1", user_id="demo@goga.kr", public_key="pk", sign_count=0, label="폰")
    # 별칭(user_id↔email) 관용 매칭 — v39 C 패턴
    assert ps.list_for_user("u1") == []
    got = ps.list_for_user("u1", user_ids={"u1", "demo@goga.kr"})
    assert len(got) == 1 and got[0]["credential_id"] == "c1"
    # 본인 것만 삭제(타 식별자 미삭제)
    assert ps.delete_credential("c1", user_ids={"other@x.kr"}) is False
    assert ps.delete_credential("c1", user_ids={"demo@goga.kr"}) is True


def test_login_page_has_passkey_button_and_js():
    tpl = Path("src/auth/templates/auth/login.html").read_text(encoding="utf-8")
    assert "패스키로 로그인" in tpl and "passkeyLoginBtn" in tpl
    assert "/seller/static/passkey.js" in tpl
    js = Path("src/seller_console/static/passkey.js").read_text(encoding="utf-8")
    assert "navigator.credentials.create" in js and "navigator.credentials.get" in js


def test_google_oauth_still_present():
    # 구글 OAuth(병행) 보존
    op = Path("src/auth/oauth_provider.py").read_text(encoding="utf-8")
    assert "'google'" in op and "accounts.google.com" in op
    login = Path("src/auth/templates/auth/login.html").read_text(encoding="utf-8")
    assert "/auth/google/start" in login
