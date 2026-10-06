"""Z6(2026-10-06) — 오너 서버 자격(전역 환경변수)은 공유 사용자(관리자·`FAMILY_EMAILS`)만 쓴다.

L1(#837) 이후 누구나 가입한다. 예전 `seller_market_env`/`_market_ok`는 「셀러 저장값이 없으면 전역
환경변수」였다 → 갓 가입한 남이 `{"markets": ["shopify"]}`로 **오너 상점에 등록**했고, 연결 뱃지도
오너 키로 「연결됨」이었다. #839는 계정 코드(`coupang:woojoo` 등)만 막았고 무접두 코드는 열려 있었다.
"""
from __future__ import annotations

import os
import threading

import pytest

OWNER_SHOP = "owner-shop.myshopify.com"
OWNER_WC = "https://owner-wc.example"
OWNER_ENV = {
    "SHOPIFY_SHOP": OWNER_SHOP, "SHOPIFY_CLIENT_ID": "owner-cid", "SHOPIFY_CLIENT_SECRET": "shpss_owner",
    "SHOPIFY_AUTO_TOKEN": "shpat_owner",
    "WC_URL": OWNER_WC, "WC_KEY": "ck_owner", "WC_SECRET": "cs_owner",
    "COUPANG_ACCESS_KEY": "owner-ak", "COUPANG_SECRET_KEY": "owner-sk", "COUPANG_VENDOR_ID": "A00OWNER",
    "COUPANG_RETURN_ADDRESS": "오너 반품지 주소", "COUPANG_GOGANE_ACCESS_KEY": "owner-gogane-ak",
    "ELEVENST_API_KEY": "owner-11st", "NAVER_CLIENT_ID": "owner-naver", "NAVER_CLIENT_SECRET": "owner-naver-sec",
}
PLAIN = ["shopify", "woocommerce", "coupang", "elevenst", "smartstore"]


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("MARKET_CRED_DIR", str(tmp_path))
    monkeypatch.setenv("SECRET_KEY", "z6-secret")
    monkeypatch.delenv("MARKET_CRED_ENC_KEY", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("ADMIN_EMAILS", raising=False)
    monkeypatch.setenv("FAMILY_EMAILS", "mom@example.com")
    for k, v in OWNER_ENV.items():
        monkeypatch.setenv(k, v)
    from src.seller_console import market_credentials as mc
    monkeypatch.setattr(mc, "_DATA_DIR", str(tmp_path))
    import src.seller_console.views as V
    monkeypatch.setattr(V, "_outbound_images", lambda pd, iid: (pd, [], None))


def _client(kind):
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        if kind == "stranger":
            s.update(user_id="stranger-z6", user_email="stranger@example.com", user_role="seller")
        elif kind == "family":
            s.update(user_id="mom-z6", user_email="mom@example.com", user_role="seller")
        elif kind == "admin":
            s.update(user_id="owner-z6", user_email="owner@example.com", user_role="admin")
        elif kind == "own-keys":
            s.update(user_id="own-z6", user_email="own@example.com", user_role="seller")
    return c


def _ctx(kind):
    """그 사람 세션을 가진 요청 컨텍스트 — 판정기를 직접 부를 때."""
    from flask import session
    from src.order_webhook import app
    ids = {"stranger": ("stranger-z6", "stranger@example.com", "seller"),
           "family": ("mom-z6", "mom@example.com", "seller"),
           "admin": ("owner-z6", "owner@example.com", "admin")}[kind]
    ctx = app.test_request_context("/seller/markets")
    ctx.push()
    session.update(user_id=ids[0], user_email=ids[1], user_role=ids[2])
    return ctx


class _Recorder:
    """`dispatch`/`prevalidate` 안에서 업로더가 보는 환경변수를 기록하는 가짜 디스패처."""

    def __init__(self):
        self.seen = {}

    def _snap(self):
        self.seen = {k: os.getenv(k) for k in OWNER_ENV}
        self.seen["__copy__"] = {k: v for k, v in os.environ.copy().items() if k in OWNER_ENV}

    def dispatch(self, pd, markets):
        self._snap()

        class _R:
            def to_dict(self_inner):
                return {"results": []}
        return _R()

    def prevalidate(self, pd, markets):
        self._snap()
        return []


# ── 판정기(S1 단일) ───────────────────────────────────────────────────────────────────────────

def test_stranger_without_keys_is_not_connected_and_sees_no_owner_values():
    from src.seller_console import market_credentials as mc
    ctx = _ctx("stranger")
    try:
        assert mc.env_fallback_allowed() is False
        assert mc.connected_markets("stranger-z6", PLAIN) == {m: False for m in PLAIN}
        assert not any(mc.is_connected("stranger-z6", m) for m in PLAIN)
        for st in mc.all_status("stranger-z6"):
            assert st["connected"] is False
            for f in st["fields"]:
                assert not f["has_value"] and not f["from_global"] and f["display"] == "", (st["market"], f)
                assert "owner" not in str(f["display"]) and OWNER_SHOP not in str(f["display"])
                assert f["suggest"] == ""                       # 오너 Wing ID 제안도 남에겐 없음
    finally:
        ctx.pop()


@pytest.mark.parametrize("kind", ["family", "admin"])
def test_family_and_admin_keep_env_fallback(kind):
    from src.seller_console import market_credentials as mc
    ctx = _ctx(kind)
    try:
        assert mc.env_fallback_allowed() is True
        assert all(mc.connected_markets("x-" + kind, PLAIN).values())
        assert mc.is_connected("x-" + kind, "shopify") is True
        shop = next(f for f in mc.status("x-" + kind, "shopify")["fields"] if f["env"] == "SHOPIFY_SHOP")
        assert shop["from_global"] and shop["display"] == OWNER_SHOP
    finally:
        ctx.pop()


def test_outside_request_and_sessionless_request_keep_env_fallback():
    """크론·부팅·스크립트(요청 밖)와 로그인 신원 없는 서버 내부 요청은 오너 서버 자신이다."""
    from src.order_webhook import app
    from src.seller_console import market_credentials as mc
    assert mc.env_fallback_allowed() is True and mc.is_connected("default", "shopify") is True
    with app.test_request_context("/cron/x"):
        assert mc.env_fallback_allowed() is True


def test_family_is_detected_by_real_login_session_key():
    """로그인 코드는 `user_email`을 넣는다(#839는 `email`만 읽어 운영의 가족이 공유로 안 잡혔다)."""
    from src.seller_console import market_pick as mp
    ctx = _ctx("family")
    try:
        assert mp.session_email() == "mom@example.com" and mp.session_is_shared() is True
    finally:
        ctx.pop()


# ── 업로드·사전검증 경로 ──────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("path", ["/seller/collect/upload", "/seller/collect/prevalidate"])
def test_stranger_upload_and_prevalidate_never_see_owner_env(monkeypatch, path):
    import src.seller_console.views as V
    rec = _Recorder()
    monkeypatch.setattr(V, "_get_upload_dispatcher", lambda: rec)
    r = _client("stranger").post(path, json={"product": {"title": "x", "price": "1000"}, "markets": PLAIN})
    assert r.status_code == 200, r.get_json()
    assert all(v is None for k, v in rec.seen.items() if k != "__copy__"), rec.seen
    assert rec.seen["__copy__"] == {}                          # 하위 프로세스 env 사본에도 없음
    # 요청이 끝나면 오너 전역 값은 그대로(전역을 지우지 않는다)
    assert os.environ["SHOPIFY_CLIENT_SECRET"] == "shpss_owner"


@pytest.mark.parametrize("kind", ["family", "admin"])
def test_family_and_admin_upload_still_use_owner_env(monkeypatch, kind):
    import src.seller_console.views as V
    rec = _Recorder()
    monkeypatch.setattr(V, "_get_upload_dispatcher", lambda: rec)
    r = _client(kind).post("/seller/collect/upload", json={"product": {"title": "x", "price": "1000"},
                                                          "markets": ["shopify", "coupang"]})
    assert r.status_code == 200, r.get_json()
    assert rec.seen["SHOPIFY_SHOP"] == OWNER_SHOP and rec.seen["COUPANG_ACCESS_KEY"] == "owner-ak"


def test_seller_with_own_keys_uses_only_own_keys(monkeypatch):
    import src.seller_console.views as V
    from src.seller_console import market_credentials as mc
    mc.save("own-z6", "shopify", {"SHOPIFY_SHOP": "own.myshopify.com", "SHOPIFY_CLIENT_ID": "own-cid",
                                  "SHOPIFY_CLIENT_SECRET": "shpss_own"})
    rec = _Recorder()
    monkeypatch.setattr(V, "_get_upload_dispatcher", lambda: rec)
    r = _client("own-keys").post("/seller/collect/upload", json={"product": {"title": "x", "price": "1000"},
                                                                "markets": ["shopify"]})
    assert r.status_code == 200, r.get_json()
    assert rec.seen["SHOPIFY_SHOP"] == "own.myshopify.com" and rec.seen["SHOPIFY_CLIENT_SECRET"] == "shpss_own"
    assert rec.seen["SHOPIFY_AUTO_TOKEN"] is None              # 안 넣은 칸이 오너 값으로 채워지지 않는다
    assert rec.seen["WC_URL"] is None and rec.seen["COUPANG_GOGANE_ACCESS_KEY"] is None
    from src.order_webhook import app
    from flask import session
    with app.test_request_context("/seller/markets"):
        session.update(user_id="own-z6", user_email="own@example.com", user_role="seller")
        assert mc.connected_markets("own-z6", PLAIN) == {"shopify": True, "woocommerce": False, "coupang": False,
                                                         "elevenst": False, "smartstore": False}


def test_stranger_real_dispatch_fails_honestly_and_never_calls_owner_hosts(monkeypatch):
    """실제 디스패처로: 오너 상점 호스트로 나가는 요청 0, 무접두 마켓 전부 성공 아님(가짜 성공 0)."""
    import requests
    calls = []

    def _no_net(self, method, url, *a, **k):
        calls.append(str(url))
        raise requests.ConnectionError("network blocked in test")
    monkeypatch.setattr(requests.sessions.Session, "request", _no_net)
    c = _client("stranger")
    body = {"product": {"title": "Test lamp", "price": "1000", "currency": "KRW", "sell_price_krw": 20000,
                        "images": ["https://img.alicdn.com/a.jpg"], "description": "lamp"},
            "markets": ["shopify", "woocommerce", "coupang"]}
    r = c.post("/seller/collect/upload", json=body)
    d = r.get_json()
    assert r.status_code in (200, 500), d
    if r.status_code == 200:
        res = d["result"]["results"]
        assert res and not any(x.get("success") for x in res), res
    assert not any(OWNER_SHOP in u or "owner-wc.example" in u for u in calls), calls
    pv = c.post("/seller/collect/prevalidate", json=body).get_json()
    shop = next(x for x in pv["results"] if x["market"] == "shopify")
    assert shop["ok"] is False and shop["error_code"] == "token_missing", shop


def test_stranger_connection_test_does_not_borrow_owner_keys(monkeypatch):
    """연결 테스트(입력 중 값 extra)도 같은 격리 — 칸 일부만 넣고 나머지를 오너 키로 메워 「성공」 금지."""
    from src.seller_console import market_credentials as mc
    seen = {}
    ctx = _ctx("stranger")
    try:
        with mc.seller_market_env("stranger-z6", "shopify", extra={"SHOPIFY_SHOP": "mine.myshopify.com"}):
            seen = {k: os.getenv(k) for k in ("SHOPIFY_SHOP", "SHOPIFY_CLIENT_SECRET")}
    finally:
        ctx.pop()
    assert seen == {"SHOPIFY_SHOP": "mine.myshopify.com", "SHOPIFY_CLIENT_SECRET": None}


def test_isolation_is_per_context_not_global():
    """격리 중에도 다른 스레드(오너의 동시 요청·크론)는 오너 키를 그대로 본다. 격리 안 쓰기는 겹에만."""
    from src.seller_console import market_credentials as mc
    other = {}
    with mc.isolated_market_env({"SHOPIFY_SHOP": "mine.myshopify.com"}):
        t = threading.Thread(target=lambda: other.update(v=os.getenv("SHOPIFY_CLIENT_SECRET")))
        t.start()
        t.join()
        os.environ["SHOPIFY_ACCESS_TOKEN"] = "stranger-token"      # 업로더가 토큰을 env에 써도
        assert os.getenv("SHOPIFY_ACCESS_TOKEN") == "stranger-token"
        assert "SHOPIFY_CLIENT_SECRET" not in os.environ and os.getenv("PATH")
    assert other["v"] == "shpss_owner"
    assert os.getenv("SHOPIFY_ACCESS_TOKEN") is None                 # 전역으로 새지 않음
    assert os.environ["SHOPIFY_CLIENT_SECRET"] == "shpss_owner"


# ── AI 상품등록 멀티 발행(스레드 풀) ─────────────────────────────────────────────────────────

def test_ai_publish_requires_login_and_isolates_worker_threads(monkeypatch):
    import src.seller_console.upload_dispatcher as UD
    seen = []

    class _D:
        def dispatch(self, pd, markets):
            seen.append({k: os.getenv(k) for k in ("SHOPIFY_SHOP", "WC_URL", "COUPANG_ACCESS_KEY")})

            class _Res:
                results = []
            return _Res()
    monkeypatch.setattr(UD, "UploadDispatcher", _D)
    from src.order_webhook import app
    anon = app.test_client().post("/api/ai-listing/publish", json={"markets": ["shopify"]})
    assert anon.status_code in (401, 403)
    r = _client("stranger").post("/api/ai-listing/publish", json={"markets": ["shopify", "woocommerce", "coupang"],
                                                                  "analysis": {"title": "x"}})
    if r.status_code == 403:                                          # AI_LISTING_ENABLED=0 환경
        pytest.skip("AI listing disabled")
    assert r.status_code == 200, r.get_json()
    assert len(seen) == 3 and all(v is None for s in seen for v in s.values()), seen
    seen.clear()
    r = _client("admin").post("/api/ai-listing/publish", json={"markets": ["shopify"], "analysis": {"title": "x"}})
    assert r.status_code == 200 and seen and seen[0]["SHOPIFY_SHOP"] == OWNER_SHOP
