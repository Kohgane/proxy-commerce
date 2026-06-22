"""tests/test_admin_gating_v13.py — v13 P0 보안/세션 가드.

1) 모든 /admin/* 라우트는 admin 전용 — 일반 유저/미로그인은 차단.
2) 유효 세션이면 어느 보호 페이지로 가도 재로그인(로그인 리다이렉트) 0.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

ADMIN_ROUTES = [
    ("GET", "/admin/"),
    ("GET", "/admin/products"),
    ("GET", "/admin/orders"),
    ("GET", "/admin/inventory"),
    ("GET", "/admin/users"),
    ("GET", "/admin/env"),
    ("GET", "/admin/logs"),
    ("GET", "/admin/diagnostics"),
    ("GET", "/admin/cs/stats"),
    ("POST", "/admin/cs/check-sla"),
]


@pytest.fixture
def app():
    from src.order_webhook import app as a
    a.config["TESTING"] = True
    return a


def _req(client, method, path):
    return client.post(path) if method == "POST" else client.get(path)


def test_admin_routes_block_unauthenticated(app):
    with app.test_client() as c:
        for method, path in ADMIN_ROUTES:
            r = _req(c, method, path)
            assert r.status_code in (302, 403), f"미로그인이 {path}에 접근됨({r.status_code})"


def test_admin_routes_block_normal_user(app):
    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess["user_id"] = "u1"
            sess["user_role"] = "seller"
            sess["user_email"] = "seller@example.com"
        for method, path in ADMIN_ROUTES:
            r = _req(c, method, path)
            assert r.status_code in (302, 403), f"일반 유저가 {path}에 접근됨({r.status_code})"


def test_admin_routes_allow_admin(app):
    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess["user_id"] = "admin1"
            sess["user_role"] = "admin"
            sess["user_email"] = "admin@example.com"
        # 대표 GET 라우트는 admin이면 200
        for path in ["/admin/", "/admin/products", "/admin/orders", "/admin/inventory"]:
            r = c.get(path)
            assert r.status_code == 200, f"admin이 {path} 접근 실패({r.status_code})"


# ---- 재로그인 0: 유효 세션이면 보호 페이지로 가도 로그인 리다이렉트 없음 ----
PROTECTED_SELLER_ROUTES = [
    "/seller/dashboard",
    "/seller/me",
    "/seller/collect/history",
    "/seller/markets",
    "/seller/sourcing",
    "/seller/billing",
    "/seller/api/tokens",
    "/seller/about",
    "/seller/settlement",
    "/seller/guide/business",
]


def test_logged_in_user_never_asked_to_relogin(app, monkeypatch):
    # 인증 강제 ON + 유효 세션
    import src.seller_console.views as views
    monkeypatch.setattr(views, "_AUTH_ENABLED", True)
    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess["user_id"] = "u-real"
            sess["user_email"] = "real@example.com"
            sess["user_role"] = "seller"
        for path in PROTECTED_SELLER_ROUTES:
            r = c.get(path)
            # 로그인으로 튕기면 안 됨(302 → /auth 또는 셀러 인덱스 로그인)
            if r.status_code in (301, 302):
                loc = r.headers.get("Location", "")
                assert "/auth/login" not in loc and not loc.rstrip("/").endswith("/seller"), (
                    f"유효 세션인데 {path} → 로그인 리다이렉트({loc})"
                )
