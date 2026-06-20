"""tests/test_shop_redirect.py — /shop → kohganemultishop.org redirect 테스트 (Phase 132).

ENABLE_INTERNAL_SHOP=0(기본) 시 /shop, /shop/ → 302 → kohganemultishop.org
ENABLE_INTERNAL_SHOP=1 시 내부 블루프린트 활성 (본 테스트에서는 등록 여부만 검증)
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("ENABLE_INTERNAL_SHOP", raising=False)
    # WooCommerce 키 미설정 (헬스체크 영향 없도록)
    for k in ("WC_KEY", "WC_SECRET", "WC_URL", "WOO_CK", "WOO_CS", "WOO_BASE_URL"):
        monkeypatch.delenv(k, raising=False)
    from src.order_webhook import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# /shop redirect (기본 모드 — ENABLE_INTERNAL_SHOP 미설정)
# ---------------------------------------------------------------------------

def test_shop_redirects_to_external(client):
    """/shop → 302 → kohganemultishop.org."""
    resp = client.get("/shop")
    assert resp.status_code == 302
    location = resp.headers.get("Location", "")
    assert location == "https://kohganemultishop.org"


def test_shop_slash_redirects_to_external(client):
    """/shop/ → 302 → kohganemultishop.org."""
    resp = client.get("/shop/")
    assert resp.status_code == 302
    location = resp.headers.get("Location", "")
    assert location == "https://kohganemultishop.org"


def test_shop_redirect_target_url(client):
    """redirect 대상이 정확히 https://kohganemultishop.org."""
    resp = client.get("/shop")
    location = resp.headers.get("Location", "")
    assert location == "https://kohganemultishop.org"


# ---------------------------------------------------------------------------
# ROOT_REDIRECT=shop_external
# ---------------------------------------------------------------------------

def test_root_redirect_shop_external(monkeypatch):
    """ROOT_REDIRECT=shop_external → / → 302 → kohganemultishop.org."""
    monkeypatch.setenv("ROOT_REDIRECT", "shop_external")
    from src.order_webhook import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        resp = c.get("/")
    assert resp.status_code == 302
    location = resp.headers.get("Location", "")
    assert location == "https://kohganemultishop.org"


def test_root_redirect_shop_legacy(monkeypatch):
    """ROOT_REDIRECT=shop (레거시) → / → 302 → kohganemultishop.org."""
    monkeypatch.setenv("ROOT_REDIRECT", "shop")
    from src.order_webhook import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        resp = c.get("/")
    assert resp.status_code == 302
    location = resp.headers.get("Location", "")
    assert location == "https://kohganemultishop.org"


# ---------------------------------------------------------------------------
# ROOT_REDIRECT=seller (기본)
# ---------------------------------------------------------------------------

def test_root_redirect_seller_default_logged_in(monkeypatch):
    """ROOT_REDIRECT 미설정 + 로그인 → / → /seller/ redirect."""
    monkeypatch.delenv("ROOT_REDIRECT", raising=False)
    from src.order_webhook import app
    app.config["TESTING"] = True
    app.secret_key = "test-root-redirect"
    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess["user_id"] = "u-1"
        resp = c.get("/")
    assert resp.status_code == 302
    location = resp.headers.get("Location", "")
    assert "/seller" in location or "kohganemultishop.org" not in location


def test_root_seller_default_anonymous_serves_landing_with_privacy(monkeypatch):
    """ROOT_REDIRECT 미설정 + 미로그인 → / → 랜딩(개인정보처리방침 링크 노출).

    루트가 곧장 302로 튕기면 구글 OAuth 브랜딩 검증이 '홈페이지에 개인정보처리방침
    링크 없음'으로 실패하므로, 미로그인 방문자에게는 랜딩을 직접 렌더한다.
    """
    monkeypatch.delenv("ROOT_REDIRECT", raising=False)
    from src.order_webhook import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        resp = c.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'href="/privacy"' in html
    assert 'href="/seller/"' in html
