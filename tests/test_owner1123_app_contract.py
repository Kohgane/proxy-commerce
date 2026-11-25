"""앱 v1.1(오너 2026-11-23) — 서버 약속 1~4 계약.

1. 소셜 로그인 앱 모드: `/auth/<p>/start?app=1` → 콜백 끝 `gogabridj://auth?code=<1회용·60초>` · `/auth/app/exchange` → 세션 → next.
2. 공유 수집 JSON: `POST /seller/collect/share` (Accept: application/json · X-KG-Source: ios-share) — 세션 또는 Bearer,
   미로그인 401 JSON, 응답 `{ok,item_id,title,thumb,path,dup}`. 수집 실패도 200 + ok:false + 사람 말 사유.
3. `POST /api/app/token` (로그인 세션) → `{"token": "kgp_…"}` — 공유 확장이 그 토큰으로 담는다.
4. `POST /api/push/apns/register` 기기 등록(여러 대) · 발송은 키 없으면 조용히 건너뜀 · 알림 문구는 결과에서만.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pytest

_SHARE_HDR = {"Accept": "application/json", "X-KG-Source": "ios-share"}
_SHARE_FORM = {"text": "【淘宝】https://e.tb.cn/h.abc?tk=x 「상품」", "url": "", "title": "", "src": "ios-share"}


@pytest.fixture
def app_client(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture
def auth_on(monkeypatch):
    from src.seller_console import views as V
    monkeypatch.setattr(V, "_AUTH_ENABLED", True)
    return V


@pytest.fixture
def fake_collect(monkeypatch):
    """수집 코어 대역 — 누구 이름으로 담겼는지 본다(판정·저장 로직은 이 계약 밖)."""
    from src.api import extension_api as E
    seen = {}

    def _core(raw, *, url, seller_id, seller_ids, final_url="", source="mobile"):
        seen.update(seller_id=seller_id, seller_ids=set(seller_ids or ()), url=url, source=source)
        return ({"ok": True, "duplicate": False, "item_id": "abc123", "title": "접이식 책상", "partial": True,
                 "message": "담았어요"}, {"ok": True})
    monkeypatch.setattr(E, "share_collect_core", _core)
    from src.seller_console import views as V
    monkeypatch.setattr(V, "_get_owned_item", lambda iid: {
        "id": iid, "title": "접이식 책상", "image_url": "https://img.alicdn.com/a.jpg",
        "extra_json": '{"images_stored": ["https://res.cloudinary.com/x/y.jpg"]}'})
    return seen


# ── 2. 공유 수집 JSON ─────────────────────────────────────────────────────────

def test_share_json_unauthenticated_is_401_json(app_client, auth_on):
    r = app_client.post("/seller/collect/share", data=_SHARE_FORM, headers=_SHARE_HDR)
    assert r.status_code == 401 and r.is_json
    d = r.get_json()
    assert d["ok"] is False and "로그인" in d["error"] and d["login"] == "/auth/login"


def test_share_html_unauthenticated_still_redirects_to_login(app_client, auth_on):
    r = app_client.post("/seller/collect/share", data=_SHARE_FORM)            # 브라우저·단축어 길은 그대로
    assert r.status_code == 302 and "/auth/login" in r.headers["Location"]


def test_share_json_with_bearer_collects_as_token_user(app_client, auth_on, fake_collect):
    from src.auth.personal_tokens import generate_token
    tok = generate_token("u-iphone", scopes=["collect.write"])["raw_token"]
    r = app_client.post("/seller/collect/share", data=_SHARE_FORM,
                        headers={**_SHARE_HDR, "Authorization": "Bearer " + tok})
    assert r.status_code == 200
    d = r.get_json()
    base = {k: d[k] for k in ("ok", "item_id", "title", "thumb", "path", "dup", "partial", "message")}
    assert base == {"ok": True, "item_id": "abc123", "title": "접이식 책상",
                    "thumb": "https://res.cloudinary.com/x/y.jpg",                 # 우리 저장본이 1순위
                    "path": "/seller/m/item/abc123", "dup": False, "partial": True, "message": "담았어요"}
    # 오너 11-25 15:56 ④: 공유 시트 문구는 서버가 담긴 그대로(사진이 있으면 「담았어요 ✓」, 소싱처 아이콘은 썸네일 없을 때만)
    assert d["headline"] == "담았어요 ✓" and d["source_icon"] == "" and d["next_label"] == ""
    assert fake_collect["seller_id"] == "u-iphone" and fake_collect["seller_ids"] == {"u-iphone"}
    assert "Set-Cookie" not in r.headers or "session=" not in r.headers.get("Set-Cookie", "")   # 토큰 길은 세션을 안 만든다


def test_share_json_bad_bearer_is_401_even_with_session(app_client, auth_on, fake_collect):
    with app_client.session_transaction() as s:
        s["user_id"] = "u-web"
    r = app_client.post("/seller/collect/share", data=_SHARE_FORM,
                        headers={**_SHARE_HDR, "Authorization": "Bearer kgp_nope"})
    assert r.status_code == 401 and r.get_json()["ok"] is False
    assert not fake_collect                                                   # 담지 않았다


def test_share_json_with_session_cookie(app_client, auth_on, fake_collect):
    with app_client.session_transaction() as s:
        s["user_id"] = "u-web"; s["user_email"] = "web@test.local"
    d = app_client.post("/seller/collect/share", data=_SHARE_FORM, headers=_SHARE_HDR).get_json()
    assert d["ok"] and d["path"] == "/seller/m/item/abc123"
    assert fake_collect["seller_id"] == "u-web"


def test_share_json_failure_is_200_with_reason(app_client, auth_on, monkeypatch):
    with app_client.session_transaction() as s:
        s["user_id"] = "u-web"
    r = app_client.post("/seller/collect/share", data={"text": "링크 없는 글", "src": "ios-share"}, headers=_SHARE_HDR)
    d = r.get_json()
    assert r.status_code == 200 and d["ok"] is False and d["error"] and d["dup"] is False


def test_share_json_duplicate_flag(app_client, auth_on, monkeypatch):
    from src.api import extension_api as E
    from src.seller_console import views as V
    monkeypatch.setattr(E, "share_collect_core", lambda raw, **k: (
        {"ok": True, "duplicate": True, "item_id": "old1", "title": "이미", "message": "이미 수집한 상품입니다."}, {"ok": True}))
    monkeypatch.setattr(V, "_get_owned_item", lambda iid: {"id": iid, "title": "이미", "image_url": ""})
    with app_client.session_transaction() as s:
        s["user_id"] = "u-web"
    d = app_client.post("/seller/collect/share", data=_SHARE_FORM, headers=_SHARE_HDR).get_json()
    assert d["ok"] and d["dup"] is True and d["path"] == "/seller/m/item/old1" and d["thumb"] == ""


def test_bearer_identity_is_request_scoped(app_client, auth_on, fake_collect):
    from src.auth.personal_tokens import generate_token
    tok = generate_token("u-iphone2", scopes=["collect.write"])["raw_token"]
    app_client.post("/seller/collect/share", data=_SHARE_FORM, headers={**_SHARE_HDR, "Authorization": "Bearer " + tok})
    r = app_client.get("/seller/collect/history")                             # 다음 요청은 토큰 신원이 없다
    assert r.status_code == 302                                               # 미로그인 처리(목록이 열리지 않는다)


# ── 3. 개인 토큰 ─────────────────────────────────────────────────────────────

def test_app_token_requires_session(app_client):
    r = app_client.post("/api/app/token", headers={"Accept": "application/json"})
    assert r.status_code == 401 and r.get_json()["ok"] is False


def test_app_token_issues_valid_collect_token(app_client):
    with app_client.session_transaction() as s:
        s["user_id"] = "u-tok"
    d = app_client.post("/api/app/token", headers={"Accept": "application/json"}).get_json()
    assert d["ok"] and d["token"].startswith("kgp_") and d["name"] == "iPhone 공유"
    from src.auth.personal_tokens import validate_token
    assert (validate_token(d["token"], ["collect.write"]) or {}).get("user_id") == "u-tok"


def test_app_endpoints_refuse_cross_site(app_client):
    with app_client.session_transaction() as s:
        s["user_id"] = "u-tok"
    for path in ("/api/app/token", "/api/push/apns/register"):
        r = app_client.post(path, json={}, headers={"Sec-Fetch-Site": "cross-site"})
        assert r.status_code == 403, path


# ── 1. 소셜 로그인 앱 모드 ───────────────────────────────────────────────────

class _Prov:
    is_configured = True

    def get_authorize_url(self, state, redirect_uri):
        return "https://accounts.example.com/o?state=" + state

    def exchange_code(self, code, redirect_uri):
        return {"access_token": "t"}

    def get_user_info(self, access_token):
        return {"provider_user_id": "g-1", "email": "app1123@example.com", "name": "앱사람", "avatar_url": ""}


def test_oauth_app_mode_returns_code_to_app_scheme(app_client, monkeypatch):
    monkeypatch.setattr("src.auth.views._get_provider", lambda p: _Prov())
    r = app_client.get("/auth/google/start?app=1&next=/seller/m")
    assert r.status_code == 302
    state = parse_qs(urlparse(r.headers["Location"]).query)["state"][0]
    r = app_client.get(f"/auth/google/callback?code=c&state={state}")
    loc = r.headers["Location"]
    assert r.status_code == 302 and loc.startswith("gogabridj://auth?")
    q = parse_qs(urlparse(loc).query)
    assert q["next"] == ["/seller/m"] and len(q["code"][0]) >= 20
    with app_client.session_transaction() as s:
        assert not s.get("user_id")                                          # 사파리 창엔 세션을 열지 않았다
    # 앱 웹뷰(쿠키 없는 새 클라이언트)가 코드를 바꾼다
    from src.order_webhook import app
    with app.test_client() as web:
        r2 = web.get(f"/auth/app/exchange?code={q['code'][0]}&next=/seller/m")
        assert r2.status_code == 302 and r2.headers["Location"].endswith("/seller/m")
        with web.session_transaction() as s:
            assert s.get("user_id") and s.get("user_email") == "app1123@example.com" and s.permanent
        r3 = web.get(f"/auth/app/exchange?code={q['code'][0]}&next=/seller/m")   # 한 번만
        assert "/auth/login" in r3.headers["Location"]


def test_oauth_without_app_flag_unchanged(app_client, monkeypatch):
    monkeypatch.setattr("src.auth.views._get_provider", lambda p: _Prov())
    r = app_client.get("/auth/google/start?next=/seller/m")
    state = parse_qs(urlparse(r.headers["Location"]).query)["state"][0]
    r = app_client.get(f"/auth/google/callback?code=c&state={state}")
    assert r.headers["Location"].endswith("/seller/m")
    with app_client.session_transaction() as s:
        assert s.get("user_id")


def test_app_code_expires_and_rejects_bad_shape(monkeypatch):
    from src.auth import app_login as AL
    from src.auth.models import User
    code = AL.issue(User(user_id="u-x", email="x@e.com", name="x"))
    AL._st().state_set(AL._PREFIX + code, {**AL._st().state_get(AL._PREFIX + code),
                                            "exp": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()})
    assert AL.take(code) == {}
    assert AL.take("../../etc") == {} and AL.take("") == {}
    good = AL.issue(User(user_id="u-y", email="y@e.com", name="y"))
    assert AL.take(good)["user_id"] == "u-y" and AL.take(good) == {}


def test_exchange_next_is_internal_only(app_client):
    r = app_client.get("/auth/app/exchange?code=x&next=https://evil.example")
    assert "/auth/login" in r.headers["Location"] and "evil" not in r.headers["Location"]


# ── 4. APNs ──────────────────────────────────────────────────────────────────

_TOK = "a1" * 32


def test_apns_register_requires_session_and_stores_devices(app_client, monkeypatch):
    monkeypatch.delenv("APNS_TOPIC", raising=False)
    assert app_client.post("/api/push/apns/register", json={"token": _TOK}).status_code == 401
    with app_client.session_transaction() as s:
        s["user_id"] = "u-push"
    d = app_client.post("/api/push/apns/register",
                        json={"token": _TOK, "env": "sandbox", "bundle": "org.kohgane.gogabridj"}).get_json()
    assert d == {"ok": True, "devices": 1}
    app_client.post("/api/push/apns/register", json={"token": "b2" * 32, "env": "production"})
    app_client.post("/api/push/apns/register", json={"token": _TOK, "env": "sandbox"})       # 같은 기기는 갱신
    from src.notifications import apns
    devs = apns.devices("u-push")
    assert [d["token"] for d in devs] == ["b2" * 32, _TOK] and devs[1]["env"] == "sandbox"
    bad = app_client.post("/api/push/apns/register", json={"token": "not hex"})
    assert bad.status_code == 400 and bad.get_json()["ok"] is False


def test_apns_register_rejects_other_bundle_when_topic_set(app_client, monkeypatch):
    monkeypatch.setenv("APNS_TOPIC", "org.kohgane.gogabridj")
    with app_client.session_transaction() as s:
        s["user_id"] = "u-push2"
    r = app_client.post("/api/push/apns/register", json={"token": _TOK, "bundle": "com.other.app"})
    assert r.status_code == 400


def test_apns_send_skips_silently_without_keys(monkeypatch):
    for k in ("APNS_KEY_P8", "APNS_KEY_ID", "APNS_TEAM_ID", "APNS_TOPIC"):
        monkeypatch.delenv(k, raising=False)
    from src.notifications import apns
    apns.register("u-nokey", _TOK)
    assert apns.send("u-nokey", "t", "b", "/seller/m") == {"sent": 0, "failed": 0, "skipped": "no_keys"}
    apns.notify("u-nokey", "t", "b")                                          # 예외·스레드 없음


def test_apns_send_signs_and_drops_dead_devices(monkeypatch):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    pem = ec.generate_private_key(ec.SECP256R1()).private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    monkeypatch.setenv("APNS_KEY_P8", pem)
    monkeypatch.setenv("APNS_KEY_ID", "KEYID12345")
    monkeypatch.setenv("APNS_TEAM_ID", "J6TH5PRA9L")
    monkeypatch.setenv("APNS_TOPIC", "org.kohgane.gogabridj")
    from src.notifications import apns
    apns._jwt_cache.update(tok="", at=0.0)
    apns.register("u-send", "c3" * 32, env="production")
    apns.register("u-send", "d4" * 32, env="sandbox")
    calls = []

    class _Resp:
        def __init__(self, code, reason=""):
            self.status_code, self._r = code, reason

        def json(self):
            return {"reason": self._r}

    class _Client:
        def __init__(self, http2=False, timeout=None):
            assert http2 is True

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, json=None, headers=None):
            calls.append((url, json, headers))
            return _Resp(200) if "c3" in url else _Resp(410, "Unregistered")

    import httpx
    monkeypatch.setattr(httpx, "Client", _Client)
    res = apns.send("u-send", "등록됐어요", "쿠팡에 올렸어요", "/seller/m/item/abc")
    assert res == {"sent": 1, "failed": 1, "skipped": ""}
    urls = [c[0] for c in calls]
    assert urls[0].startswith("https://api.push.apple.com/3/device/") and urls[1].startswith("https://api.sandbox.push.apple.com/")
    body, hdr = calls[0][1], calls[0][2]
    assert body == {"aps": {"alert": {"title": "등록됐어요", "body": "쿠팡에 올렸어요"}, "sound": "default"},
                    "path": "/seller/m/item/abc"}
    assert hdr["apns-topic"] == "org.kohgane.gogabridj" and hdr["authorization"].startswith("bearer ey")
    import jwt
    h = jwt.get_unverified_header(hdr["authorization"][7:])
    assert h["alg"] == "ES256" and h["kid"] == "KEYID12345"
    assert [d["token"] for d in apns.devices("u-send")] == ["c3" * 32]       # 지운 앱(410)은 목록에서 빠진다


def test_push_texts_come_from_results_only():
    from src.seller_console.views import push_hold_text, push_upload_text
    assert push_upload_text({"ok": True, "result": {"results": [{"market": "coupang", "success": True}]}}) == \
        ("등록됐어요", "쿠팡에 올렸어요")
    t, b = push_upload_text({"ok": True, "result": {"results": [
        {"market": "coupang", "success": True}, {"market": "smartstore", "success": False}]}})
    assert t == "일부만 등록됐어요" and "쿠팡 성공" in b and "스마트스토어 실패" in b
    assert push_upload_text({"ok": True, "result": {"results": []}}) == ("", "")
    assert push_hold_text({"coupang": {"hold": False, "ok": True}}) == ("", "")
    assert push_hold_text({"coupang": {"hold": False, "ok": False, "transport": "timeout"}}) == ("", "")   # 검증 못 함은 안 알림
    t, b = push_hold_text({"coupang": {"hold": True, "market_label": "쿠팡", "message": "배송비가 판매가의 40%를 넘어요"}})
    assert t == "사전검증에서 멈췄어요" and b == "쿠팡 — 배송비가 판매가의 40%를 넘어요"


def test_payload_path_only_inside_seller():
    from src.notifications.apns import payload
    assert "path" not in payload("a", "b", "https://evil.example")
    assert payload("a", "b", "/seller/m")["path"] == "/seller/m"


def test_bearer_identity_does_not_leak_through_outer_app_context(auth_on, fake_collect):
    """바깥 앱 컨텍스트가 살아 있어도(g가 요청을 넘어 남는 조건) 토큰 신원은 그 요청에서 끝난다."""
    from src.auth.personal_tokens import generate_token
    from src.order_webhook import app
    tok = generate_token("u-leak", scopes=["collect.write"])["raw_token"]
    app_client = app.test_client()
    with app.app_context():
        app_client.post("/seller/collect/share", data=_SHARE_FORM, headers={**_SHARE_HDR, "Authorization": "Bearer " + tok})
        assert fake_collect["seller_id"] == "u-leak"
        with app_client.session_transaction() as s:
            s["user_id"] = "u-web"
        app_client.post("/seller/collect/share", data=_SHARE_FORM, headers=_SHARE_HDR)
        assert fake_collect["seller_id"] == "u-web"
