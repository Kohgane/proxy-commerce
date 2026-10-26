"""순찰 122b(오너 2026-10-26 18:29) — 「고급 기능」 메뉴 게이트.

오너: "고급기능 그거 너무 난잡하고 비개발자들 입장에선 뭔소린지 싶어 그러니 그건 한정된 기능으로 숨겨라. 원하는? 혹은
결제한 사람들한테만 개방하는걸로 하고 관리자는 그냥 보이게하고."

계약: 무료 기본 숨김 · 관리자 보임 · plus/pro 보임 · 직접 켠 사람 보임 · 숨겨도 라우트 200 + 안내 한 줄 · 핵심 6개 불변 ·
연동·요금제·설정·알림은 숨겨도 남는다(처음 쓰는 사람이 연동을 못 찾으면 안 된다).
"""
from __future__ import annotations

import pytest

from src.order_webhook import app
from src.seller_console import views as V
from src.seller_console import advanced_gate as G

CORE = ("/seller/dashboard", "/seller/sourcing", "/seller/manual-collect", "/seller/collect/history", "/seller/orders", "/seller/markets", "/seller/guide/business")
BASIC_KEEP = ("/seller/markets/connect", "/seller/billing", "/seller/me", "/seller/notifications")
ADV_SAMPLE = ("/seller/listing/word-rules", "/seller/pricing/rules", "/seller/customs/pccc", "/seller/settlement")


@pytest.fixture
def auth_on(monkeypatch):
    monkeypatch.setattr(V, "_AUTH_ENABLED", True)
    monkeypatch.setattr(V, "_is_admin_user", lambda: False)
    G._TEST_PREFS = {}
    monkeypatch.setattr(G, "pref_on", lambda sid: bool(G._TEST_PREFS.get(sid)))
    monkeypatch.setattr(G, "set_pref", lambda sid, on: G._TEST_PREFS.__setitem__(sid, bool(on)) or True)
    from src.seller_console import billing_store as B
    monkeypatch.setattr(B, "get_account", lambda sid: {"plan": getattr(G, "_TEST_PLAN", "free"), "token_balance": 0})
    G._TEST_PLAN = "free"
    yield


def _client(role="seller", uid="u-free"):
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = uid
        s["user_email"] = f"{uid}@test.local"
        s["user_role"] = role
    return c


def _nav(html: str) -> str:
    return html


def test_gate_logic_pure():
    assert G.advanced_visible(is_admin=True, plan="free", pref=False) is True
    assert G.advanced_visible(is_admin=False, plan="plus", pref=False) is True
    assert G.advanced_visible(is_admin=False, plan="pro", pref=False) is True
    assert G.advanced_visible(is_admin=False, plan="free", pref=True) is True
    assert G.advanced_visible(is_admin=False, plan="free", pref=False) is False
    assert G.advanced_visible(is_admin=False, plan=None, pref=False) is False


def test_advanced_path_classifier():
    for p in ADV_SAMPLE + ("/seller/sourcing/watches", "/seller/sourcing/monitor", "/seller/cs/inbox", "/seller/analytics"):
        assert G.is_advanced_path(p), p
    for p in CORE + BASIC_KEEP + ("/seller/about", "/seller/me/notifications"):
        assert not G.is_advanced_path(p), p


def test_free_user_default_hidden_but_basics_remain(auth_on):
    c = _client()
    html = c.get("/seller/dashboard").get_data(as_text=True)
    assert 'id="advNav"' not in html                                  # 고급 접이식이 안 그려진다
    assert 'data-role="nav-advanced-off"' in html                      # 대신 「고급 기능 켜기」 입구 한 줄
    for p in CORE:
        assert f'href="{p}"' in html, p                                # 핵심 6개 불변
    for p in BASIC_KEEP:
        assert f'href="{p}"' in html, p                                # 연동·요금제·설정·알림은 남는다
    assert 'href="/seller/listing/word-rules"' not in html             # 고급 링크는 안 보인다


def test_admin_sees_advanced(auth_on, monkeypatch):
    monkeypatch.setattr(V, "_is_admin_user", lambda: True)
    html = _client(role="admin", uid="u-admin").get("/seller/dashboard").get_data(as_text=True)
    assert 'id="advNav"' in html and 'href="/seller/listing/word-rules"' in html
    assert 'data-role="nav-advanced-off"' not in html


@pytest.mark.parametrize("plan", ["plus", "pro"])
def test_paid_plan_sees_advanced(auth_on, plan):
    G._TEST_PLAN = plan
    html = _client(uid="u-paid").get("/seller/dashboard").get_data(as_text=True)
    assert 'id="advNav"' in html


def test_toggle_on_reveals_and_persists(auth_on):
    c = _client(uid="u-opt")
    r = c.post("/seller/me/advanced", json={"on": True})
    assert r.status_code == 200 and r.get_json() == {"ok": True, "on": True}
    html = c.get("/seller/dashboard").get_data(as_text=True)
    assert 'id="advNav"' in html
    r = c.post("/seller/me/advanced", json={"on": False})
    assert r.get_json()["on"] is False
    assert 'id="advNav"' not in c.get("/seller/dashboard").get_data(as_text=True)


def test_toggle_requires_login(auth_on):
    r = app.test_client().post("/seller/me/advanced", json={"on": True})
    assert r.status_code in (401, 302)


@pytest.mark.parametrize("path", ADV_SAMPLE)
def test_hidden_route_still_200_with_banner(auth_on, path):
    r = _client().get(path)
    assert r.status_code == 200, (path, r.status_code)                # 막지 않는다
    html = r.get_data(as_text=True)
    assert 'data-role="advanced-hidden-banner"' in html                # 안내 한 줄
    assert "/seller/me#advancedCard" in html


def test_core_route_has_no_banner(auth_on):
    html = _client().get("/seller/orders").get_data(as_text=True)
    assert 'data-role="advanced-hidden-banner"' not in html


def test_me_card_states(auth_on, monkeypatch):
    # me.html은 사용자 레코드가 있어야 본문을 그린다 — 시트 없는 테스트 레인은 가짜 사용자 1명
    class _U(dict):
        __getattr__ = dict.get
    from src.auth import user_store as US
    monkeypatch.setattr(US, "get_store", lambda: type("S", (), {"find_by_id": staticmethod(
        lambda uid: _U(email=f"{uid}@test.local", name="테스트", role="seller", email_verified=True, social_accounts=[],
                       created_at="2026-10-01", last_login_at="2026-10-26", avatar_url=""))})())
    html = _client(uid="u-me").get("/seller/me").get_data(as_text=True)
    assert 'id="advancedCard"' in html and 'data-role="advanced-toggle"' in html
    assert "숨겨져 있어요" in html
    for line in G.ADVANCED_SUMMARY:
        assert line in html
    G._TEST_PLAN = "pro"
    html = _client(uid="u-me2").get("/seller/me").get_data(as_text=True)
    assert "항상 열림" in html and 'data-role="advanced-toggle"' not in html


def test_dev_mode_auth_off_shows_everything(monkeypatch):
    """SELLER_CONSOLE_AUTH=0(개발·테스트)은 예전 그대로 전부 보인다 — 수백 개 내비 테스트의 전제."""
    monkeypatch.setattr(V, "_AUTH_ENABLED", False)
    html = app.test_client().get("/seller/dashboard").get_data(as_text=True)
    assert 'id="advNav"' in html


def test_no_dev_markup_in_hidden_banner():
    import re
    src = open("src/seller_console/templates/_base.html", encoding="utf-8").read()
    i = src.index('data-role="advanced-hidden-banner"')
    block = src[i:i + 600]
    assert not re.search(r"[A-Z_]{6,}", block)                         # env 이름·대문자 토큰 0
    assert "{" not in block.replace("{{", "").replace("}}", "").replace("{%", "").replace("%}", "")
