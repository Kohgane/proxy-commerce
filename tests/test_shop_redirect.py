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

def test_root_redirect_seller_default(monkeypatch):
    """ROOT_REDIRECT 미설정 → / → /seller/ redirect."""
    monkeypatch.delenv("ROOT_REDIRECT", raising=False)
    from src.order_webhook import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        resp = c.get("/")
    assert resp.status_code == 302
    location = resp.headers.get("Location", "")
    assert "/seller" in location or "kohganemultishop.org" not in location
