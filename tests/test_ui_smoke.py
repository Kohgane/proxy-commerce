"""tests/test_ui_smoke.py — Phase 123 UI 스모크 테스트.

검증 항목:
  - GET /               → 200 (랜딩) 또는 302 (셀러 콘솔 등록 시)
  - GET /admin/         → 200, Bootstrap CDN 포함, raw escape 없음
  - GET /api/docs       → 200, 검색 input 포함
  - GET /존재하지않는경로 → 404, "404" 텍스트 포함
  - GET /health/deep    → 200, status / checks 필드 포함
"""
from __future__ import annotations

import json
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# 픽스처
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def client(tmp_path_factory):
    """order_webhook Flask 앱 테스트 클라이언트 (모듈 스코프)."""
    import src.order_webhook as wh
    wh.app.config["TESTING"] = True
    with wh.app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# 1. 루트 라우트
# ---------------------------------------------------------------------------

class TestRootRoute:
    """GET / 테스트."""

    def test_root_returns_200_or_302(self, client):
        """루트는 200(랜딩) 또는 302(셀러 콘솔 리다이렉트) 중 하나여야 한다."""
        resp = client.get("/")
        assert resp.status_code in (200, 302), (
            f"GET / 응답 코드: {resp.status_code}"
        )

    def test_root_200_contains_landing_content(self, client):
        """200 응답이면 랜딩 페이지 콘텐츠가 포함되어야 한다."""
        resp = client.get("/")
        if resp.status_code == 200:
            body = resp.data.decode("utf-8", errors="replace")
            # Bootstrap CDN 또는 주요 텍스트 중 하나 이상 포함
            assert any(k in body for k in ["bootstrap", "Proxy Commerce", "셀러"]), (
                "랜딩 페이지에 기대 콘텐츠 없음"
            )

    def test_root_302_redirects_to_seller(self, client):
        """302 응답이면 /seller/ 로 리다이렉트되어야 한다."""
        resp = client.get("/")
        if resp.status_code == 302:
            assert "/seller/" in resp.headers.get("Location", ""), (
                f"302 Location 헤더: {resp.headers.get('Location')}"
            )


# ---------------------------------------------------------------------------
# 2. Admin 패널
# ---------------------------------------------------------------------------

class TestAdminPanel:
    """GET /admin/ 테스트."""

    def test_admin_returns_200(self, client):
        resp = client.get("/admin/")
        assert resp.status_code == 200

    def test_admin_contains_bootstrap(self, client):
        """Bootstrap CDN 링크가 HTML에 포함되어야 한다."""
        resp = client.get("/admin/")
        body = resp.data.decode("utf-8", errors="replace")
        assert "bootstrap" in body.lower(), "Bootstrap CDN 미포함"

    def test_admin_no_raw_html_escape(self, client):
        """Jinja2 auto-escape로 인해 &lt;div 같은 raw escape 텍스트가 없어야 한다."""
        resp = client.get("/admin/")
        body = resp.data.decode("utf-8", errors="replace")
        # HTML이 escape되어 출력되면 &lt;h4 같은 패턴이 보인다
        assert "&lt;h4" not in body, "HTML이 escape되어 화면에 노출됨 (escape 버그)"
        assert "&lt;div" not in body, "HTML이 escape되어 화면에 노출됨 (escape 버그)"

    def test_admin_products_returns_200(self, client):
        resp = client.get("/admin/products")
        assert resp.status_code == 200

    def test_admin_orders_returns_200(self, client):
        resp = client.get("/admin/orders")
        assert resp.status_code == 200

    def test_admin_inventory_returns_200(self, client):
        resp = client.get("/admin/inventory")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 3. API 문서
# ---------------------------------------------------------------------------

class TestApiDocs:
    """GET /api/docs 테스트."""

    def test_api_docs_returns_200(self, client):
        resp = client.get("/api/docs")
        assert resp.status_code == 200

    def test_api_docs_contains_search_input(self, client):
        """검색 input이 있어야 한다."""
        resp = client.get("/api/docs")
        body = resp.data.decode("utf-8", errors="replace")
        assert "<input" in body, "/api/docs에 검색 input 없음"

    def test_api_docs_contains_method_badges(self, client):
        """메서드 배지(GET/POST 등)가 포함되어야 한다."""
        resp = client.get("/api/docs")
        body = resp.data.decode("utf-8", errors="replace")
        assert "badge-get" in body or "GET" in body, "메서드 배지 없음"

    def test_api_docs_contains_accordion(self, client):
        """그룹 accordion이 포함되어야 한다."""
        resp = client.get("/api/docs")
        body = resp.data.decode("utf-8", errors="replace")
        assert "accordion" in body, "accordion 그룹 구조 없음"


# ---------------------------------------------------------------------------
# 4. 404 핸들러
# ---------------------------------------------------------------------------

class TestErrorHandlers:
    """에러 핸들러 테스트."""

    def test_unknown_path_returns_404(self, client):
        resp = client.get("/이_경로는_존재하지_않는다_xyz_12345")
        assert resp.status_code == 404

    def test_404_page_contains_404_text(self, client):
        """404 에러 페이지에 '404' 텍스트가 포함되어야 한다."""
        resp = client.get("/이_경로는_존재하지_않는다_xyz_12345")
        body = resp.data.decode("utf-8", errors="replace")
        assert "404" in body, "404 에러 페이지에 '404' 텍스트 없음"


# ---------------------------------------------------------------------------
# 5. 헬스체크
# ---------------------------------------------------------------------------

class TestHealthDeep:
    """GET /health/deep 테스트."""

    def test_health_deep_returns_200(self, client):
        """degraded여도 200을 반환해야 한다 (Phase 123 변경)."""
        resp = client.get("/health/deep")
        assert resp.status_code == 200

    def test_health_deep_has_status_field(self, client):
        resp = client.get("/health/deep")
        data = resp.get_json()
        assert "status" in data, "'status' 필드 없음"
        assert data["status"] in ("ok", "degraded", "error"), (
            f"'status' 값이 예상 범위 밖: {data['status']}"
        )

    def test_health_deep_has_checks_field(self, client):
        resp = client.get("/health/deep")
        data = resp.get_json()
        assert "checks" in data, "'checks' 필드 없음"
        assert isinstance(data["checks"], list), "'checks'가 list가 아님"

    def test_health_deep_checks_have_name_and_status(self, client):
        """각 check 항목에 name, status 필드가 있어야 한다."""
        resp = client.get("/health/deep")
        data = resp.get_json()
        for check in data.get("checks", []):
            assert "name" in check, f"check에 'name' 없음: {check}"
            assert "status" in check, f"check에 'status' 없음: {check}"
            assert check["status"] in ("ok", "fail", "skip"), (
                f"check status 값이 예상 범위 밖: {check['status']}"
            )
