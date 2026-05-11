"""tests/test_route_registration.py — 라우트 등록 회귀 방지 (Phase 144).

모든 blueprint가 등록됐는지, 핵심 라우트들이 200/302(로그인)를 반환하는지 확인.
404는 실패.
"""
from __future__ import annotations

import pytest


@pytest.fixture(scope="module")
def app():
    """Flask 앱 픽스처 (order_webhook에서 로드)."""
    import os
    os.environ.setdefault("TESTING", "1")
    os.environ.setdefault("SECRET_KEY", "test-secret")
    os.environ.setdefault("ADS_AUTO_CAMPAIGN_ENABLED", "0")
    os.environ.setdefault("KEYWORD_OPT_PROVIDER", "mock")
    import src.order_webhook as wh
    wh.app.config["TESTING"] = True
    return wh.app


@pytest.fixture(scope="module")
def client(app):
    with app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# Phase별 핵심 라우트 화이트리스트
# ---------------------------------------------------------------------------

CORE_ROUTES = [
    # Phase 136 — 가격 정책
    "/seller/pricing/rules",
    # Phase 138+ — CS 자동응답
    "/seller/cs/inbox",
    # Phase 143 — 소싱 파이프라인
    "/seller/sourcing/watches",
    "/seller/sourcing/candidates",
    # Phase 144 — 등록 이력, 이미지 큐, 광고 캠페인
    "/seller/listing/history",
    "/seller/media/queue",
    "/seller/ads/campaigns",
    # Phase 145~146
    "/seller/orders/auto",
    "/seller/returns/inbox",
    "/seller/settlement",
    # Phase 142 — 자동 리오더, 마케팅 캠페인
    "/seller/inventory/reorder",
    "/seller/marketing/campaigns",
]


class TestBlueprintRegistration:
    """Blueprint 등록 확인."""

    def test_seller_console_blueprint_registered(self, app):
        """seller_console blueprint 등록 확인."""
        registered_names = {bp.name for bp in app.blueprints.values()}
        assert "seller_console" in registered_names, (
            "seller_console blueprint이 등록되지 않았습니다"
        )

    def test_admin_panel_blueprint_registered(self, app):
        """admin_panel blueprint 등록 확인."""
        registered_names = {bp.name for bp in app.blueprints.values()}
        assert "admin_panel" in registered_names, (
            "admin_panel blueprint이 등록되지 않았습니다"
        )

    def test_auth_blueprint_registered(self, app):
        """auth blueprint 등록 확인."""
        registered_names = {bp.name for bp in app.blueprints.values()}
        assert "auth" in registered_names, (
            "auth blueprint이 등록되지 않았습니다"
        )


class TestCoreRoutesNotReturn404:
    """핵심 라우트들이 404를 반환하지 않는지 확인 (200 또는 302)."""

    @pytest.mark.parametrize("path", CORE_ROUTES)
    def test_route_not_404(self, client, path):
        """핵심 라우트 GET → 200 또는 302(로그인 리다이렉트), 404 아님."""
        resp = client.get(path)
        assert resp.status_code != 404, (
            f"라우트 {path} 가 404를 반환했습니다 — blueprint 등록 누락 가능성"
        )
        assert resp.status_code in (200, 302, 401, 403), (
            f"라우트 {path} 예상치 못한 상태 코드: {resp.status_code}"
        )


class TestPhase143RoutesFix:
    """Phase 143 → 144 hotfix: sourcing/listing/media 라우트 등록 확인."""

    def test_sourcing_watches_registered(self, app):
        view_funcs = app.view_functions
        assert "seller_console.sourcing_watches" in view_funcs, (
            "/seller/sourcing/watches 라우트 미등록"
        )

    def test_sourcing_candidates_registered(self, app):
        view_funcs = app.view_functions
        assert "seller_console.sourcing_candidates" in view_funcs, (
            "/seller/sourcing/candidates 라우트 미등록"
        )

    def test_listing_history_registered(self, app):
        view_funcs = app.view_functions
        assert "seller_console.listing_history" in view_funcs, (
            "/seller/listing/history 라우트 미등록 (Phase 144 추가 필요)"
        )

    def test_media_queue_registered(self, app):
        view_funcs = app.view_functions
        assert "seller_console.media_queue" in view_funcs, (
            "/seller/media/queue 라우트 미등록 (Phase 144 추가 필요)"
        )

    def test_ads_campaigns_registered(self, app):
        view_funcs = app.view_functions
        assert "seller_console.ads_campaigns" in view_funcs, (
            "/seller/ads/campaigns 라우트 미등록 (Phase 144 추가 필요)"
        )

    def test_sourcing_watches_returns_not_404(self, client):
        resp = client.get("/seller/sourcing/watches")
        assert resp.status_code != 404, "/seller/sourcing/watches → 404 (Phase 143 hotfix 미적용)"

    def test_listing_history_returns_not_404(self, client):
        resp = client.get("/seller/listing/history")
        assert resp.status_code != 404, "/seller/listing/history → 404"

    def test_media_queue_returns_not_404(self, client):
        resp = client.get("/seller/media/queue")
        assert resp.status_code != 404, "/seller/media/queue → 404"

    def test_ads_campaigns_returns_not_404(self, client):
        resp = client.get("/seller/ads/campaigns")
        assert resp.status_code != 404, "/seller/ads/campaigns → 404"
