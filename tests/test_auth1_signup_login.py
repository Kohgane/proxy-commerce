"""AUTH-1(오너 2026-09-30) — 이메일 가입이 되고, 가입 즉시 로그인되고, 실패는 원인이 보인다.

실측(실서버, 채팅): POST /auth/signup → 302 /auth/login 「가입이 완료되었습니다. 이메일 인증 후 로그인해주세요.」
→ 같은 자격으로 POST /auth/login → 「이메일 또는 비밀번호가 올바르지 않습니다」(틀린 비번과 같은 응답).

근원(코드·라이브러리 실측): 로그인 코드엔 인증 게이트가 **없었다.** 계정이 Google Sheets `users`에 있었고
gspread 6 `get_all_records`가 "1"을 숫자 1로 준다 → `active == "1"` 거짓 → **모든 시트 계정이 비활성**.

  ① 가입 → 바로 로그인 → /seller/dashboard 200 (오너 결정 ㊼: 인증 없이)
  ② 로그인 오류 셋을 가른다: 등록되지 않은 이메일 / 비밀번호가 틀립니다 / (플래그 켜진 경우만) 인증 필요
  ③ 오류는 flash가 아니라 **같은 응답**에 원인 코드와 함께
  ④ 저장 실패·저장소 다운은 가짜 「가입 완료」가 아니라 원인 코드
  ⑤ 옛 시트 계정(숫자 1)도 로그인되고, 한 번 로그인하면 PG로 옮겨 적힌다
  ⑥ next 유지(공유 시트 → 로그인 → 원래 흐름)
"""
from __future__ import annotations

import pytest


def _wipe_pg():
    """PG 레인(CI pg-suite)에선 행이 테스트 사이에 남는다 — 이 파일이 만든 것만 지운다."""
    from src.db import pg
    if not pg.pg_enabled():
        return
    pg.init_schema()
    with pg.tx() as cur:
        cur.execute("DELETE FROM password_accounts WHERE email LIKE %s", ("%@example.test",))
        cur.execute("DELETE FROM user_identities WHERE email LIKE %s", ("%@example.test",))


@pytest.fixture
def app_client(monkeypatch):
    import src.seller_console.views as V
    from src.auth import password_accounts as accounts
    from src.db import user_identities_pg as ident
    accounts.reset_for_tests()
    ident.reset_for_tests()
    _wipe_pg()
    monkeypatch.setattr(accounts, "_legacy_sheet_account", lambda email: None)
    monkeypatch.delenv("AUTH_REQUIRE_EMAIL_VERIFY", raising=False)
    old = V._AUTH_ENABLED
    V._AUTH_ENABLED = True
    from src.order_webhook import app
    try:
        yield app.test_client()
    finally:
        V._AUTH_ENABLED = old
        accounts.reset_for_tests()
        ident.reset_for_tests()
        _wipe_pg()


def _signup(c, email="new@example.test", password="pass12345", **extra):
    return c.post("/auth/signup", data={"email": email, "password": password, "name": "새셀러", **extra})


def _login(c, email="new@example.test", password="pass12345", **extra):
    return c.post("/auth/login", data={"email": email, "password": password, **extra})


def test_signup_logs_in_immediately_and_dashboard_opens(app_client):
    c = app_client
    assert c.get("/seller/dashboard").status_code == 302            # 로그인 전 = 튕김
    r = _signup(c)
    assert r.status_code == 302 and r.headers["Location"].endswith("/seller/dashboard")
    assert c.get("/seller/dashboard").status_code == 200            # 가입 즉시 로그인
    with c.session_transaction() as s:
        assert s["user_email"] == "new@example.test" and s["user_id"]


def test_login_errors_are_split_in_three(app_client, monkeypatch):
    c = app_client
    _signup(c)
    c.get("/auth/logout")
    h = _login(c, password="wrong-pass").get_data(as_text=True)
    assert "비밀번호가 틀립니다" in h and 'data-code="AUTH-LOGIN-BAD-PASSWORD"' in h
    r = _login(c, email="nobody@example.test")
    h = r.get_data(as_text=True)
    assert r.status_code == 401 and "등록되지 않은 이메일" in h and 'data-code="AUTH-LOGIN-NO-ACCOUNT"' in h
    assert "올바르지 않습니다" not in h                                  # 뭉갠 문구는 없다
    assert 'value="nobody@example.test"' in h                          # 입력한 이메일은 남긴다
    r = _login(c)
    assert r.status_code == 302 and c.get("/seller/dashboard").status_code == 200


def test_verify_flag_on_blocks_unverified_and_offers_resend(app_client, monkeypatch):
    c = app_client
    _signup(c)
    c.get("/auth/logout")
    monkeypatch.setenv("AUTH_REQUIRE_EMAIL_VERIFY", "1")
    r = _login(c)
    h = r.get_data(as_text=True)
    assert r.status_code == 403 and "이메일 인증이 필요합니다" in h and 'data-role="auth-resend"' in h
    from src.auth import password_accounts as accounts
    tok = accounts.find("new@example.test")["verify_token"]
    assert tok and "인증이 완료" in c.get("/auth/verify-email?token=" + tok).get_data(as_text=True)
    assert _login(c).status_code == 302


def test_flag_off_by_default_even_for_unverified(app_client):
    from src.auth import password_accounts as accounts
    _signup(app_client)
    assert accounts.find("new@example.test")["email_verified"] is False   # 플래그 값은 그대로
    app_client.get("/auth/logout")
    assert _login(app_client).status_code == 302                          # 로그인 조건에서만 빠졌다


def test_duplicate_and_social_only_signups_are_named(app_client):
    c = app_client
    _signup(c)
    c.get("/auth/logout")
    h = _signup(c).get_data(as_text=True)
    assert 'data-code="AUTH-SIGNUP-EXISTS"' in h and "이미 가입된 이메일" in h
    from src.db import user_identities_pg as ident
    ident.register("google", "g@example.test", "uid-google")
    h = _signup(c, email="g@example.test").get_data(as_text=True)
    assert 'data-code="AUTH-SIGNUP-SOCIAL"' in h and "구글로 가입돼 있어요" in h


def test_save_failure_is_not_a_fake_success(app_client, monkeypatch):
    from src.db import password_accounts_pg as store

    def _boom(**k):
        raise RuntimeError("connection refused postgresql://u:secret@db/x")

    monkeypatch.setattr(store, "create", _boom)
    r = _signup(app_client)
    h = r.get_data(as_text=True)
    assert r.status_code == 503 and 'data-code="AUTH-SIGNUP-SAVE"' in h and "저장하지 못했어요" in h
    assert "secret" not in h and "가입이 완료" not in h
    with app_client.session_transaction() as s:
        assert not s.get("user_id")


def test_store_down_is_not_wrong_password(app_client, monkeypatch):
    from src.db import password_accounts_pg as store
    monkeypatch.setattr(store, "get_by_email", lambda e: (_ for _ in ()).throw(OSError("timeout")))
    h = _login(app_client).get_data(as_text=True)
    assert 'data-code="AUTH-STORE-DOWN"' in h and "비밀번호가 틀립니다" not in h


def test_legacy_sheet_account_with_numeric_flags_logs_in_and_moves_to_pg(app_client, monkeypatch):
    """근원 재현: gspread가 준 행(active=1 숫자) → 옛 코드는 비활성으로 읽었다."""
    from src.auth import password_accounts as accounts
    from src.auth.models import User
    from src.auth.views import _hash_password
    row = {"user_id": "legacy-uid", "email": "old@example.test", "name": "옛셀러", "role": "seller",
           "email_verified": 0, "active": 1, "password_hash": _hash_password("oldpass123")}
    u = User.from_row(row)
    assert u.active is True and u.email_verified is False             # 숫자 1 = 활성

    class _Sheet:
        def find_by_email(self, email):
            return u if email == "old@example.test" else None

    monkeypatch.setattr(accounts, "_legacy_sheet_account",
                        lambda email: {"user_id": u.user_id, "email": u.email, "name": u.name, "role": u.role,
                                       "password_hash": u.password_hash, "email_verified": u.email_verified}
                        if _Sheet().find_by_email(email) else None)
    r = _login(app_client, email="old@example.test", password="oldpass123")
    assert r.status_code == 302
    moved = accounts.store.get_by_email("old@example.test")
    assert moved and moved["source"] == "sheets" and moved["user_id"] == "legacy-uid"


def test_next_is_kept_through_signup(app_client):
    nxt = "/seller/collect/share?text=abc"
    page = app_client.get("/auth/signup?next=" + nxt).get_data(as_text=True)
    assert 'name="next" value="/seller/collect/share?text=abc"' in page
    r = _signup(app_client, next=nxt)
    assert r.status_code == 302 and r.headers["Location"].endswith(nxt)


def test_login_link_to_signup_keeps_next(app_client):
    h = app_client.get("/auth/login?next=/seller/collect/history").get_data(as_text=True)
    assert 'href="/auth/signup?next=/seller/collect/history"' in h or \
           'href="/auth/signup?next=%2Fseller%2Fcollect%2Fhistory"' in h
