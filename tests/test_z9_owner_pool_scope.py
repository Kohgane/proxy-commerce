"""Z9(2026-10-07) — 오너 풀 화면(CS 인박스·메시징·B2B 도매·정기구독)은 공유 사용자만.

#841 「같은 유형인데 뺀 것」: `_cs_role_allowed`가 role `seller`면 통과해 모든 가입자가 오너 구매자 문의(연락처 포함)를
보고 오너 채널로 답장할 수 있었다. `/seller/messaging/log`·`/messaging/test`·`/wholesale/*`·`/subscriptions`는
`_check_auth`조차 없었다.

판정은 Z7 주문 범위와 같다(`orders.scope.current_viewer`): 공유 사용자(관리자 · `FAMILY_EMAILS`)는 통과,
그 밖의 로그인 신원은 403, 로그인 신원 없음(크론·인증 꺼진 개발)은 서버 자신이라 통과.
"""
from __future__ import annotations

import pytest

PAGES = ["/seller/cs/inbox", "/seller/cs/faq", "/seller/cs/quality", "/seller/cs/sla", "/seller/cs/mobile",
         "/seller/cs/stats", "/seller/messaging", "/seller/wholesale/tiers", "/seller/wholesale/applications",
         "/seller/subscriptions"]
JSON_GET = ["/seller/messaging/log"]
POSTS = ["/seller/cs/inbox/respond", "/seller/messaging/test",
         "/seller/wholesale/applications/app-x/approve", "/seller/wholesale/applications/app-x/reject"]
NAV = ['href="/seller/cs/inbox"', 'href="/seller/messaging"', 'href="/seller/cs/messaging"',
       'href="/seller/wholesale/applications"', 'href="/seller/subscriptions"']


@pytest.fixture(autouse=True)
def _family(monkeypatch):
    monkeypatch.setenv("FAMILY_EMAILS", "mom@example.com")
    monkeypatch.delenv("ADMIN_EMAILS", raising=False)


def _client(**sess):
    from src.order_webhook import app
    c = app.test_client()
    if sess:
        with c.session_transaction() as s:
            s.update(sess)
    return c


STRANGER = {"user_id": "stranger-z9", "user_email": "stranger@example.com", "user_role": "seller"}
FAMILY = {"user_id": "mom-z9", "user_email": "mom@example.com", "user_role": "seller"}
ADMIN = {"user_id": "owner-z9", "user_email": "owner@example.com", "user_role": "admin"}


@pytest.mark.parametrize("path", PAGES + JSON_GET)
def test_stranger_gets_403(path):
    r = _client(**STRANGER).get(path)
    assert r.status_code == 403, (path, r.status_code)
    h = r.get_data(as_text=True)
    assert "Forbidden" not in h and "read-protected" not in h               # 영문 서버 기본 문구 노출 0
    if path in PAGES:
        assert 'data-role="forbidden"' in h and "관리자·가족" in h


@pytest.mark.parametrize("path", POSTS)
def test_stranger_posts_403_and_nothing_runs(path, monkeypatch):
    from src.messaging import router as R
    from src.wholesale import application_manager as W
    monkeypatch.setattr(R.MessageRouter, "test_send", lambda *a, **k: pytest.fail("오너 채널로 발송됨"), raising=False)
    monkeypatch.setattr(W.WholesaleApplicationManager, "approve", lambda *a, **k: pytest.fail("승인됨"))
    monkeypatch.setattr(W.WholesaleApplicationManager, "reject", lambda *a, **k: pytest.fail("거절됨"))
    r = _client(**STRANGER).post(path, json={"channel": "telegram", "message_id": "m1", "text": "x"})
    assert r.status_code == 403, (path, r.status_code)


@pytest.mark.parametrize("who", [FAMILY, ADMIN, {}], ids=["family", "admin", "no-identity"])
@pytest.mark.parametrize("path", PAGES + JSON_GET)
def test_shared_and_server_still_open(path, who):
    r = _client(**who).get(path)
    assert r.status_code == 200, (path, who, r.status_code)


def test_family_email_case_and_legacy_email_key(monkeypatch):
    assert _client(user_id="mom2", user_email="Mom@Example.com").get("/seller/cs/inbox").status_code == 200
    assert _client(user_id="mom3", email="mom@example.com").get("/seller/cs/inbox").status_code == 200


def test_nav_hides_owner_pool_links_for_stranger():
    h = _client(**STRANGER).get("/seller/me").get_data(as_text=True)
    assert not [n for n in NAV if n in h]
    h = _client(**FAMILY).get("/seller/me").get_data(as_text=True)
    assert 'href="/seller/cs/inbox"' in h and 'href="/seller/wholesale/applications"' in h and 'href="/seller/subscriptions"' in h
    h = _client(**STRANGER).get("/seller/me").get_data(as_text=True)
    assert 'href="/seller/me/subscriptions"' in h                     # 「내 구독」은 본인 것 — 그대로


def test_judge_failure_closes(monkeypatch):
    """범위 판정이 깨지면 닫는다(신원은 있는데 범위를 모르면 오너 풀을 내주지 않는다)."""
    from src.seller_console.orders import scope
    monkeypatch.setattr(scope, "current_viewer", lambda: (_ for _ in ()).throw(RuntimeError("x")))
    assert _client(**FAMILY).get("/seller/cs/inbox").status_code == 403
