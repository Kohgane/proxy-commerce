"""tests/test_seller_collect_views_phase128.py — Phase 128 수집기 뷰 라우트 테스트.

GET  /seller/collect           → 200
POST /seller/collect/preview   → 200 + 수집기 디스패처 연동
POST /seller/collect/save      → 200
GET  /seller/catalog           → 200
GET  /seller/orders            → 200
GET  /seller/api-status        → 200
GET  /seller/api-status/json   → 200 + JSON
"""
from __future__ import annotations

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# 픽스처
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    """셀러 콘솔이 등록된 Flask 앱 테스트 클라이언트."""
    from src.order_webhook import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# GET /seller/collect
# ---------------------------------------------------------------------------

def test_collect_page_200(client):
    """GET /seller/collect → 200."""
    resp = client.get("/seller/collect")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# POST /seller/collect/preview — Phase 128 실 수집기 연동
# ---------------------------------------------------------------------------

def test_collect_preview_uses_dispatcher(client):
    """실 수집기 dispatcher 호출 후 성공 응답 반환."""
    from src.seller_console.collectors.base import CollectorResult
    from decimal import Decimal

    mock_result = CollectorResult(
        success=True,
        url="https://www.amazon.com/dp/B09XYZ0001",
        source="amazon_og",
        title="테스트 상품",
        price=Decimal("29.99"),
        currency="USD",
        images=["https://example.com/img.jpg"],
        warnings=["PA-API 미설정"],
    )

    with patch("src.seller_console.collectors.dispatcher.collect", return_value=mock_result):
        resp = client.post(
            "/seller/collect/preview",
            data=json.dumps({"url": "https://www.amazon.com/dp/B09XYZ0001"}),
            content_type="application/json",
        )

    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["ok"] is True
    assert data["draft"]["title"] == "테스트 상품"


def test_collect_preview_registers_discovery_candidate(client):
    """수집 성공 시 Discovery 후보 자동 등록 훅 호출."""
    from src.seller_console.collectors.base import CollectorResult

    mock_result = CollectorResult(
        success=True,
        url="https://example-brand.com/item/1",
        source="generic_og",
        title="브랜드 상품",
    )
    with patch("src.seller_console.collectors.dispatcher.collect", return_value=mock_result):
        with patch("src.seller_console.views._register_discovery_candidate_from_collection") as mock_register:
            resp = client.post(
                "/seller/collect/preview",
                data=json.dumps({"url": "https://example-brand.com/item/1", "keyword": "브랜드"}),
                content_type="application/json",
            )
    assert resp.status_code == 200
    mock_register.assert_called_once()


def test_collect_preview_empty_url_returns_400(client):
    """빈 URL → 400."""
    resp = client.post(
        "/seller/collect/preview",
        data=json.dumps({"url": ""}),
        content_type="application/json",
    )
    assert resp.status_code == 400


def test_collect_preview_fallback_to_universal_scraper(client):
    """dispatcher 실패 시 범용 스크래퍼로 실 폴백 (Phase 200 — 목업 제거)."""
    from src.collectors.universal_scraper import ScrapedProduct
    from decimal import Decimal

    scraped = ScrapedProduct(
        source_url="https://example-brand.com/item/1",
        domain="example-brand.com",
        title="Fallback Product",
        description="real description",
        images=["https://example-brand.com/img.jpg"],
        price=Decimal("29.99"),
        currency="USD",
        options=[{"name": "Color", "values": ["Black", "White"]}],
        extraction_method="json-ld",
        confidence=0.8,
    )

    with patch("src.seller_console.collectors.dispatcher.collect", side_effect=Exception("dispatcher error")):
        with patch("src.collectors.universal_scraper.UniversalScraper.fetch", return_value=scraped):
            resp = client.post(
                "/seller/collect/preview",
                data=json.dumps({"url": "https://example-brand.com/item/1"}),
                content_type="application/json",
            )

    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["ok"] is True
    draft = data["draft"]
    assert draft["is_mock"] is False
    assert draft["title"] == "Fallback Product"
    assert draft["options"] == [{"name": "Color", "values": ["Black", "White"]}]


# ---------------------------------------------------------------------------
# POST /seller/collect/save
# ---------------------------------------------------------------------------

def test_collect_save_empty_payload_400(client):
    """빈 payload → 400."""
    resp = client.post(
        "/seller/collect/save",
        data=json.dumps({}),
        content_type="application/json",
    )
    assert resp.status_code == 400


def test_collect_save_calls_adapter(client):
    """저장 요청이 올바른 HTTP 응답을 반환."""
    # payload 포함 POST → 200 (Sheets 연결 여부에 따라 saved/error) 또는 500 허용
    payload = {"title": "테스트 상품", "price": "29.99", "currency": "USD"}
    resp = client.post(
        "/seller/collect/save",
        data=json.dumps(payload),
        content_type="application/json",
    )
    # 200 (saved) 또는 500 (Sheets 연결 실패) 모두 허용
    assert resp.status_code in (200, 500)
    data = json.loads(resp.data)
    assert "ok" in data


# ---------------------------------------------------------------------------
# GET /seller/catalog
# ---------------------------------------------------------------------------

def test_catalog_page_200(client):
    """GET /seller/catalog → 200."""
    resp = client.get("/seller/catalog")
    assert resp.status_code == 200


def test_catalog_page_content(client):
    """카탈로그 페이지에 필수 요소 포함."""
    resp = client.get("/seller/catalog")
    html = resp.data.decode("utf-8")
    assert "카탈로그" in html or "catalog" in html.lower()


# ---------------------------------------------------------------------------
# GET /seller/orders
# ---------------------------------------------------------------------------

def test_orders_page_200(client):
    """GET /seller/orders → 200."""
    resp = client.get("/seller/orders")
    assert resp.status_code == 200


def test_orders_page_stub_notice(client):
    """주문 관리 페이지가 실제 주문 운영 UI로 렌더된다(스텁 아님)."""
    resp = client.get("/seller/orders")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    assert "주문 관리" in html
    assert "운송장" in html


# ---------------------------------------------------------------------------
# GET /seller/api-status
# ---------------------------------------------------------------------------

def _as_admin(client):
    # v17: api-status는 관리자 전용 — 테스트에서 관리자 세션 부여.
    with client.session_transaction() as s:
        s["user_id"] = "admin1"; s["user_email"] = "admin@x.com"; s["user_role"] = "admin"


def test_api_status_page_200(client):
    """GET /seller/api-status → 200 (관리자)."""
    _as_admin(client)
    resp = client.get("/seller/api-status")
    assert resp.status_code == 200


def test_api_status_page_shows_apis(client):
    """API 상태 페이지에 API 이름 포함 (관리자)."""
    _as_admin(client)
    resp = client.get("/seller/api-status")
    html = resp.data.decode("utf-8")
    # 최소 하나 이상의 API 이름이 표시되어야 함
    assert any(name in html for name in ["coupang_wing", "exchange_rate", "naver_commerce"])


def test_api_status_json_200(client):
    """GET /seller/api-status/json → 200 + JSON (관리자)."""
    _as_admin(client)
    resp = client.get("/seller/api-status/json")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["ok"] is True
    assert "apis" in data
    assert isinstance(data["apis"], list)


def test_api_status_json_schema(client):
    """api-status/json 응답 스키마 확인 (관리자)."""
    _as_admin(client)
    resp = client.get("/seller/api-status/json")
    data = json.loads(resp.data)
    for api in data["apis"]:
        assert "name" in api
        assert "status" in api
        assert api["status"] in ("active", "missing")
        assert "purpose" in api
        assert "env_vars" in api


# ---------------------------------------------------------------------------
# GET /health/deep — external_apis 필드 확인
# ---------------------------------------------------------------------------

def test_health_deep_has_external_apis(client):
    """/health/deep 응답에 external_apis 필드 포함 (Phase 130: dict or list)."""
    resp = client.get("/health/deep")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert "external_apis" in data
    # Phase 130: get_api_status() returns dict with 'apis' key
    assert isinstance(data["external_apis"], (list, dict))


# ---------------------------------------------------------------------------
# GET /seller/health — phase 128
# ---------------------------------------------------------------------------

def test_seller_health_phase128(client):
    """셀러 콘솔 health가 phase=128 반환."""
    resp = client.get("/seller/health")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["ok"] is True
    assert data["phase"] == 128
