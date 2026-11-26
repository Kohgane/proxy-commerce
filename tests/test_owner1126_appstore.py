"""오너 11-26 감독 3 — 앱스토어 심사 대비. 계약.

a 앱 안 계정 삭제: 더보기 › 계정 › 「계정 삭제」 → 두 번 확인(체크 → 「삭제」 적기) → **요청**만(줄) · 실제 삭제는 오너 탭
c 약관·개인정보·문의: 로그인 화면·더보기에서 같은 창으로(새 창 이탈 0)
d 심사 계정: 마켓 전송 입구 전부 403 + 등록기 안에서도 막힘 · 사전검증은 그대로
e 앱(UA gogabridjApp) 안: 결제·요금제 화면을 열지 않고 링크도 안 그린다 · 한도 문구가 요금제로 이끌지 않는다
"""
from __future__ import annotations

import re

import pytest

APP_UA = {"User-Agent": "Mozilla/5.0 (iPhone) AppleWebKit/605 gogabridjApp/1.2"}


@pytest.fixture
def store(monkeypatch):
    s = {}
    import src.db.image_translate_queue_pg as st
    monkeypatch.setattr(st, "state_get", lambda k: s.get(k))
    monkeypatch.setattr(st, "state_set", lambda k, v: s.__setitem__(k, v))
    return s


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    app.config["TESTING"] = True
    return app.test_client()


def _login(c, uid="u-del-1", email="del@example.com", role="seller"):
    with c.session_transaction() as s:
        s["user_id"], s["email"], s["user_role"] = uid, email, role


# ── a 계정 삭제 ─────────────────────────────────────────────────────────────

def test_more_tab_has_account_delete_and_legal_links(client):
    _login(client)
    h = client.get("/seller/m?tab=more").get_data(as_text=True)
    assert 'data-role="account-delete-link"' in h and 'href="/seller/me/delete"' in h
    legal = h[h.index('data-role="more-legal"'):][:400]
    for href in ("/privacy", "/terms", "/contact"):
        assert f'href="{href}"' in legal
    assert 'target="_blank"' not in legal


def test_delete_page_shows_scope_and_two_steps(client, store):
    _login(client)
    h = client.get("/seller/me/delete").get_data(as_text=True)
    assert "지워지는 것" in h and "남는 것" in h and "주문·정산 기록" in h and "5년" in h
    assert 'data-role="ad-step1"' in h and 'data-role="ad-step2" hidden' in h and 'data-role="ad-next" disabled' in h
    assert "del@example.com" in h


def test_request_needs_confirm_word_then_queues_and_logs_out(client, store):
    _login(client)
    r = client.post("/seller/me/delete", json={"confirm": "네"})
    assert r.status_code == 400 and not store.get("account_delete:requests")
    d = client.post("/seller/me/delete", json={"confirm": "삭제", "reason": "안 써요"}).get_json()
    assert d["ok"] and d["id"]
    rows = store["account_delete:requests"]["rows"]
    assert rows[0]["state"] == "requested" and rows[0]["user_id"] == "u-del-1" and rows[0]["reason"] == "안 써요"
    with client.session_transaction() as s:
        assert not s.get("user_id")                                   # 로그아웃
    # 같은 사람이 다시 들어오면 「요청을 받았어요」 + 거두기
    _login(client)
    h = client.get("/seller/me/delete").get_data(as_text=True)
    assert 'data-role="ad-pending"' in h and 'data-role="ad-cancel"' in h
    assert client.post("/seller/me/delete/cancel").get_json()["ok"]
    assert store["account_delete:requests"]["rows"][0]["state"] == "cancelled"


def test_request_alone_deletes_nothing(client, store, monkeypatch):
    """요청은 줄에 서는 것뿐 — 실행 함수는 오너 탭(관리자 경로)으로만 불린다."""
    from src.services import account_delete as AD
    called = []
    monkeypatch.setattr(AD, "execute", lambda *a, **k: called.append(a))
    _login(client)
    client.post("/seller/me/delete", json={"confirm": "삭제"})
    assert called == []


def test_execute_is_admin_only_and_needs_request_id(client, store):
    from src.services import account_delete as AD
    rec = AD.request("u-del-2", "d2@example.com")
    _login(client, uid="u-del-3", email="x@example.com", role="seller")
    assert client.post(f"/seller/admin/account-deletes/{rec['id']}/execute", json={"confirm": rec["id"]}).status_code == 403
    _login(client, uid="u-admin", email="admin@example.com", role="admin")
    assert client.post(f"/seller/admin/account-deletes/{rec['id']}/execute", json={"confirm": "x"}).status_code == 400
    assert AD.rows()[0]["state"] == "requested"
    h = client.get("/seller/admin/account-deletes").get_data(as_text=True)
    assert rec["id"] in h and 'data-role="ad-exec"' in h and "prompt(" not in h


def test_execute_removes_collected_tokens_and_keys(store):
    from src.auth import personal_tokens as pt
    from src.seller_console import collect_history_store as S
    from src.services import account_delete as AD
    uid = "u-del-exec"
    iid = S.append(source="share", url="https://www.amazon.com/dp/B0C38WV1F6", title="x", price="1", currency="USD",
                   image="", seller_id=uid, extra={})
    tok = pt.generate_token(uid, scopes=["collect.write"])
    rec = AD.request(uid, "")
    out = AD.execute(rec["id"], by="owner")
    assert out["state"] in ("done", "partial") and "collected" in out["steps"] and "tokens" in out["steps"]
    assert S.get(iid, seller_id=uid) is None
    assert all(t.get("revoked") for t in pt.list_tokens(uid))
    assert AD.execute(rec["id"], by="owner")["ok"] is False                 # 두 번 실행 안 됨
    assert tok


# ── e 앱 안 결제·요금제 ─────────────────────────────────────────────────────

@pytest.mark.parametrize("path", ["/seller/billing", "/pricing"])
def test_app_does_not_open_billing(client, path):
    _login(client)
    r = client.get(path, headers=APP_UA)
    h = r.get_data(as_text=True)
    assert r.status_code == 200 and 'data-role="app-hidden"' in h and "/seller/billing" not in h.split('data-role="app-hidden"')[1][:600]
    assert 'data-role="app-hidden"' not in client.get(path).get_data(as_text=True)          # 웹은 그대로


def test_app_pages_draw_no_billing_links(client):
    _login(client)
    for path in ("/seller/me", "/seller/m?tab=more"):
        app_h = client.get(path, headers=APP_UA).get_data(as_text=True)
        assert 'data-role="billing-link"' not in app_h and not re.search(r'href="/seller/billing"', app_h), path
    assert 'data-role="billing-link"' in client.get("/seller/me").get_data(as_text=True)


def test_limit_message_in_app_does_not_upsell(client):
    from src.seller_console import usage_meter as U
    with client.application.test_request_context("/seller/m", headers=APP_UA):
        m = U.message("collect", "free", 30)
    assert "올리" not in m and "Plus" not in m and "다음 달 1일" in m
    with client.application.test_request_context("/seller/m"):
        assert "Plus로 올리거나" in U.message("collect", "free", 30)


# ── d 심사 계정 ─────────────────────────────────────────────────────────────

def test_review_account_cannot_send_to_markets(client, monkeypatch):
    monkeypatch.setenv("REVIEW_ACCOUNT_EMAILS", "review@gogabridj.test")
    _login(client, uid="u-review", email="Review@gogabridj.test")
    for path in ("/seller/collect/upload", "/seller/collect/bulk-upload", "/seller/collect/abc/take-down",
                 "/seller/collect/abc/naver-resend-photos", "/seller/sourcing/candidates/c1/publish"):
        r = client.post(path, json={})
        assert r.status_code == 403 and r.get_json()["review_account"], path
    # 등록기 안에서도(다른 입구로 와도) 막힌다
    from src.seller_console.upload_dispatcher import UploadDispatcher
    with client.application.test_request_context("/x"):
        from flask import session
        session["user_id"], session["email"] = "u-review", "review@gogabridj.test"
        res = UploadDispatcher().dispatch({"title": "t", "price": 1}, ["coupang", "smartstore"])
    assert res.failed == 2 and res.succeeded == 0 and all("심사용" in x.message for x in res.results)


def test_normal_account_is_not_blocked(client, monkeypatch):
    monkeypatch.setenv("REVIEW_ACCOUNT_EMAILS", "review@gogabridj.test")
    _login(client, uid="u-real", email="real@example.com")
    r = client.post("/seller/collect/abc/take-down", json={})
    assert r.status_code != 403 or not (r.get_json() or {}).get("review_account")


# ── c 로그인 화면 ───────────────────────────────────────────────────────────

def test_login_has_legal_and_contact_links_same_window(client):
    h = client.get("/auth/login").get_data(as_text=True)
    for href in ("/privacy", "/terms", "/contact"):
        m = re.search(r'<a href="' + re.escape(href) + r'"[^>]*>', h)
        assert m and "_blank" not in m.group(0), href
