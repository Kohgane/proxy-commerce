"""Y15-B(오너 2026-10-22) — 가입 유입 기록: 첫 방문 referrer·랜딩·utm(세션) → 가입 때 ip·ua와 함께 저장 + 텔레그램 「유입:」 줄."""
import uuid

import pytest


@pytest.fixture
def env(monkeypatch):
    import src.auth.views as AV
    import src.auth.user_store as us
    import src.seller_console.views as V
    from src.auth import account_label as al, password_accounts as accounts
    from src.db import user_identities_pg as ident
    accounts.reset_for_tests()
    ident.reset_for_tests()
    al.reset_cache()
    monkeypatch.setattr(accounts, "_legacy_sheet_account", lambda email: None)
    monkeypatch.delenv("AUTH_REQUIRE_EMAIL_VERIFY", raising=False)

    class _NoSheet:                                              # 시트 사용자 저장소는 닿지 않는 상태(소셜 신규 가입 갈래)
        def find_by_id(self, uid): return None
        def find_by_email(self, email): return None
        def find_by_provider(self, p, pid): return None
        def create(self, user): return user
        def update(self, user): return None
        def update_last_login(self, uid): return None
        def link_social(self, uid, data): return None
    monkeypatch.setattr(us, "get_store", lambda: _NoSheet(), raising=False)
    sent = []
    import src.notifications.telegram as tg
    monkeypatch.setattr(tg, "send_telegram", lambda text, **kw: sent.append(text))
    monkeypatch.setattr(AV, "_async_notify", lambda fn, *a, **kw: fn(*a, **kw))
    old = V._AUTH_ENABLED
    V._AUTH_ENABLED = True
    from src.order_webhook import app
    try:
        yield app.test_client(), sent
    finally:
        V._AUTH_ENABLED = old
        accounts.reset_for_tests()
        ident.reset_for_tests()
        al.reset_cache()


def _origin(uid):
    from src.auth import signup_origin
    return signup_origin.get(uid)


def test_email_signup_keeps_first_visit_referrer_and_utm(env):
    c, sent = env
    c.get("/?utm_source=insta&utm_campaign=fall", headers={"Referer": "https://www.instagram.com/p/abc"})
    c.get("/auth/signup", headers={"Referer": "http://localhost/"})        # 가입 화면 referrer는 우리 사이트 — 덮지 않는다
    r = c.post("/auth/signup", data={"email": f"origin-{uuid.uuid4().hex[:8]}@example.test", "password": "pass12345", "name": "새셀러"},
               headers={"X-Forwarded-For": "203.0.113.7, 10.0.0.1", "User-Agent": "Mozilla/5.0 (iPhone)"})
    assert r.status_code == 302
    with c.session_transaction() as s:
        uid = s["user_id"]
    o = _origin(uid)
    assert o["referrer"] == "https://www.instagram.com/p/abc" and o["landing_path"] == "/"
    assert (o["utm_source"], o["utm_campaign"]) == ("insta", "fall")
    assert o["ip"] == "203.0.113.7" and o["ua"].startswith("Mozilla/5.0") and o["at"] and o["first_at"]
    msg = [t for t in sent if "신규 셀러 가입" in t][-1]
    assert "\n유입: instagram.com\n" in msg                       # 국가는 모르면 뺀다
    assert msg.endswith("권한: seller · 공유 판정: 아니오")         # Y15 P0-4


def test_social_signup_records_origin_and_says_direct(env, monkeypatch):
    import src.auth.views as AV
    c, sent = env

    class _P:
        is_configured = True

        def exchange_code(self, code, redirect_uri): return {"access_token": "t"}
        def get_user_info(self, token):
            return {"provider_user_id": "g-998877", "email": f"origin-{uuid.uuid4().hex[:8]}@example.test", "name": "구글셀러"}
    monkeypatch.setattr(AV, "_get_provider", lambda p: _P())
    c.get("/auth/login")                                         # referrer 없이 바로 들어온 첫 방문
    with c.session_transaction() as s:
        s["oauth_state_google"] = "st"
    r = c.get("/auth/google/callback?state=st&code=c1", headers={"X-Forwarded-For": "198.51.100.2",
                                                                  "CF-IPCountry": "KR"})
    assert r.status_code == 302
    with c.session_transaction() as s:
        uid = s["user_id"]
    o = _origin(uid)
    assert o["referrer"] == "" and o["landing_path"] == "/auth/login" and o["ip"] == "198.51.100.2"
    msg = [t for t in sent if "신규 셀러 가입" in t][-1]
    assert "경로: 구글 로그인" in msg and "\n유입: 직접 · KR\n" in msg
    assert msg.endswith("공유 판정: 아니오")                        # Y15 P0-4


def test_first_visit_is_not_overwritten_and_skips_static(env):
    from src.auth import signup_origin as so
    c, _ = env
    c.get("/static/app.css", headers={"Referer": "https://ads.example.com/"})
    c.get("/landing-x?utm_source=a", headers={"Referer": "https://blog.naver.com/x"})
    c.get("/", headers={"Referer": "https://google.com/"})
    with c.session_transaction() as s:
        first = s[so.SESSION_KEY]
    assert first["referrer"] == "https://blog.naver.com/x" and first["utm"] == {"utm_source": "a"}
    assert so.telegram_line({"referrer": "https://m.blog.naver.com/a"}) == "유입: m.blog.naver.com"
