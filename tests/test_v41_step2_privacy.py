"""tests/test_v41_step2_privacy.py — v41 STEP 2 프라이버시 가드.

A. 미로그인 차단(서버측):
   - _AUTH_ENABLED=True + 미인증 세션 → 개인 페이지 302→auth.login 또는 401
B. 공개 라우트 보존:
   - _AUTH_ENABLED=True + 미인증 세션 → 공개 라우트는 여전히 200
C. 재로그인 금지 회귀:
   - 유효 세션이면 개인 페이지 200(로그인으로 안 튕김)
D. user 스코프: tokens가 "dev" fallback 없이 로그인 user_id로만
E. auth off 회귀: SELLER_CONSOLE_AUTH=0(기본 테스트 환경)에서 200 유지
"""
from __future__ import annotations

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# 개인 페이지 목록 (auth 게이트 새로 추가한 라우트)
# ---------------------------------------------------------------------------
PRIVATE_PAGE_ROUTES = [
    "/seller/settlement",
    "/seller/settlement/export.csv",
    "/seller/settlement/export.xlsx",
    "/seller/me",
    "/seller/me/tokens",
]

# JSON/API 라우트 — 401 반환해야 함
PRIVATE_API_ROUTES = [
    ("POST", "/seller/orders/sync"),
    ("POST", "/seller/orders/coupang/ORDER-001/status"),
    ("GET", "/seller/orders/coupang/ORDER-001"),
    ("POST", "/seller/orders/coupang/ORDER-001/tracking"),
    ("POST", "/seller/orders/bulk/tracking"),
    ("POST", "/seller/orders/bulk/status"),
    ("GET", "/seller/orders/export.csv"),
    ("POST", "/seller/me/tokens/generate"),
    ("POST", "/seller/me/tokens/revoke"),
]

# 절대로 깨지면 안 되는 공개 라우트
PUBLIC_ROUTES = [
    "/",
    "/seller/about",
    "/seller/start",
    "/seller/health",
    "/seller/bookmarklet",
]

# 재로그인 없어야 할 보호 라우트 (유효 세션이면 200)
PROTECTED_WITH_SESSION = [
    "/seller/me",
    "/seller/me/tokens",
    "/seller/settlement",
    "/seller/dashboard",
]


@pytest.fixture
def app():
    from src.order_webhook import app as a
    a.config["TESTING"] = True
    return a


# ===========================================================================
# A. 미로그인 차단
# ===========================================================================

class TestUnauthBlocked:
    """_AUTH_ENABLED=True일 때 미인증 세션은 개인 페이지에 접근 불가."""

    def test_private_pages_redirect_unauth(self, app, monkeypatch):
        import src.seller_console.views as views
        monkeypatch.setattr(views, "_AUTH_ENABLED", True)
        with app.test_client() as c:
            for path in PRIVATE_PAGE_ROUTES:
                r = c.get(path)
                assert r.status_code in (302, 401), (
                    f"미로그인이 {path}에 접근됨 (status={r.status_code}) — 서버 차단 필요"
                )
                if r.status_code == 302:
                    loc = r.headers.get("Location", "")
                    assert "/auth/login" in loc, (
                        f"리다이렉트 목적지가 auth.login 아님: {loc}"
                    )

    def test_private_api_routes_return_401_unauth(self, app, monkeypatch):
        import src.seller_console.views as views
        monkeypatch.setattr(views, "_AUTH_ENABLED", True)
        with app.test_client() as c:
            for method, path in PRIVATE_API_ROUTES:
                if method == "POST":
                    r = c.post(path, json={})
                else:
                    r = c.get(path)
                assert r.status_code in (302, 401), (
                    f"미로그인이 {path}에 접근됨 (status={r.status_code}) — 401 또는 302 필요"
                )

    def test_collect_receiver_never_302(self, app, monkeypatch):
        """receiver는 미로그인이어도 절대 302로 안 튕김 (in-page showLogin)."""
        import src.seller_console.views as views
        monkeypatch.setattr(views, "_AUTH_ENABLED", True)
        with app.test_client() as c:
            r = c.get("/seller/collect/receiver")
            assert r.status_code != 302, (
                "/seller/collect/receiver 가 302 로그인 리다이렉트 — 이 라우트는 항상 200"
            )


# ===========================================================================
# B. 공개 라우트 보존
# ===========================================================================

class TestPublicRoutesPreserved:
    """_AUTH_ENABLED=True라도 공개 라우트는 미로그인에서 200."""

    def test_public_routes_still_200_when_auth_on(self, app, monkeypatch):
        import src.seller_console.views as views
        monkeypatch.setattr(views, "_AUTH_ENABLED", True)
        with app.test_client() as c:
            for path in PUBLIC_ROUTES:
                r = c.get(path)
                assert r.status_code == 200, (
                    f"공개 라우트 {path}가 auth on일 때 {r.status_code} 반환 — 미로그인 200 유지 필요"
                )


# ===========================================================================
# C. 재로그인 금지 회귀
# ===========================================================================

class TestNoReloginRegression:
    """유효 세션이면 개인 페이지에 가도 로그인으로 튕기지 않음."""

    def test_logged_in_user_not_redirected_to_login(self, app, monkeypatch):
        import src.seller_console.views as views
        monkeypatch.setattr(views, "_AUTH_ENABLED", True)
        with app.test_client() as c:
            with c.session_transaction() as sess:
                sess["user_id"] = "test-user-1"
                sess["user_email"] = "test@example.com"
                sess["user_role"] = "seller"
            for path in PROTECTED_WITH_SESSION:
                r = c.get(path)
                if r.status_code in (301, 302):
                    loc = r.headers.get("Location", "")
                    assert "/auth/login" not in loc, (
                        f"유효 세션인데 {path} → 로그인 리다이렉트({loc})"
                    )


# ===========================================================================
# D. user 스코프: tokens "dev" fallback 없음
# ===========================================================================

class TestTokensNoDevFallback:
    """personal_tokens 라우트가 "dev" fallback 없이 로그인 user_id로만 동작."""

    def test_tokens_page_blocked_when_unauth(self, app, monkeypatch):
        import src.seller_console.views as views
        monkeypatch.setattr(views, "_AUTH_ENABLED", True)
        with app.test_client() as c:
            r = c.get("/seller/me/tokens")
            assert r.status_code in (302, 401), (
                "미로그인이 /me/tokens에 접근됨 — dev fallback 노출 위험"
            )

    def test_tokens_generate_blocked_when_unauth(self, app, monkeypatch):
        import src.seller_console.views as views
        monkeypatch.setattr(views, "_AUTH_ENABLED", True)
        with app.test_client() as c:
            r = c.post("/seller/me/tokens/generate", json={"scopes": ["collect.write"]})
            assert r.status_code == 401, (
                f"미로그인이 /me/tokens/generate에 접근됨({r.status_code})"
            )
            data = r.get_json() or {}
            assert data.get("ok") is False

    def test_tokens_revoke_blocked_when_unauth(self, app, monkeypatch):
        import src.seller_console.views as views
        monkeypatch.setattr(views, "_AUTH_ENABLED", True)
        with app.test_client() as c:
            r = c.post("/seller/me/tokens/revoke", json={"token_hash": "abc"})
            assert r.status_code == 401, (
                f"미로그인이 /me/tokens/revoke에 접근됨({r.status_code})"
            )


# ===========================================================================
# E. auth off 회귀: 기존 테스트 환경 (SELLER_CONSOLE_AUTH=0) 에서 200 유지
# ===========================================================================

class TestAuthOffRegression:
    """SELLER_CONSOLE_AUTH=0 (default test env)일 때는 auth off → 모든 /seller/* 200."""

    def test_private_pages_accessible_when_auth_off(self, app):
        # conftest.py 는 SELLER_CONSOLE_AUTH=0을 강제함 → _AUTH_ENABLED=False
        import src.seller_console.views as views
        assert not views._AUTH_ENABLED, "테스트 환경에서 _AUTH_ENABLED=True이면 기존 테스트 일괄 깨짐"
        with app.test_client() as c:
            for path in PRIVATE_PAGE_ROUTES:
                r = c.get(path)
                # auth off이면 어떤 개인 페이지도 로그인 리다이렉트 0
                if r.status_code in (301, 302):
                    loc = r.headers.get("Location", "")
                    assert "/auth/login" not in loc, (
                        f"auth off인데 {path} → 로그인 리다이렉트({loc})"
                    )

    def test_api_routes_accessible_when_auth_off(self, app):
        import src.seller_console.views as views
        assert not views._AUTH_ENABLED
        with app.test_client() as c:
            # auth off이면 401 없어야 함
            r = c.post("/seller/me/tokens/generate", json={"scopes": ["collect.write"]})
            assert r.status_code != 401, (
                f"auth off인데 /me/tokens/generate → 401"
            )
