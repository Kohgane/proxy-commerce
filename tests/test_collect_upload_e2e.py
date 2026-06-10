"""tests/test_collect_upload_e2e.py — 마켓 업로드 전체 경로(E2E) 검증.

`/seller/collect/upload` 라우트 → UploadDispatcher.dispatch → 실제 `_upload_shopify`
코드 경로를 타되, 라이브 연동 경계(`ShopifyAdapter`)만 목 처리하여
다음을 정직하게 검증한다.

- 라이브 성공: 응답 result에 external_product_id / external_url 포함, succeeded=1
- API 실패(토큰 만료/401 등): success=False + error_code="api_error" + 조치 hint
- 검증 실패: error_code="validation_failed"

실제 운영 시크릿이 없는 CI 환경에서도 라이브 경로의 정합성을 고정한다.
(실 시크릿 대조 검증은 운영 환경에서 /admin/diagnostics·셀러 마켓 센터로 별도 수행)
"""
from __future__ import annotations

import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("SELLER_PASSWORD", "test")
    monkeypatch.setenv("FX_DISABLE_NETWORK", "1")
    # Shopify 토큰이 있는 라이브 환경을 가정
    monkeypatch.setenv("SHOPIFY_SHOP", "demo-shop.myshopify.com")
    monkeypatch.setenv("SHOPIFY_AUTO_TOKEN", "atk_demo_token")
    import src.order_webhook as wh
    wh.app.config["TESTING"] = True
    with wh.app.test_client() as c:
        with c.session_transaction() as sess:
            sess["seller_logged_in"] = True
        yield c


def _patch_shopify_adapter(monkeypatch, *, validate_ok=True, upload_ok=True,
                           upload_msg="ok", external_id="98765",
                           storefront="https://demo-shop.myshopify.com/products/x",
                           admin="https://demo-shop.myshopify.com/admin/products/98765",
                           raise_on_upload=False):
    """라이브 ShopifyAdapter를 시뮬레이션 어댑터로 치환."""
    import src.markets.adapters.shopify as shop_mod

    class _FakeAdapter:
        def __init__(self, *a, **kw):
            pass

        def is_configured(self):
            return True

        def validate_listing(self, payload):
            return SimpleNamespace(ok=validate_ok, message="" if validate_ok else "필수값 누락")

        def upload_product(self, payload):
            if raise_on_upload:
                raise RuntimeError("network down")
            return SimpleNamespace(
                ok=upload_ok,
                message=upload_msg,
                external_id=external_id if upload_ok else "",
                raw={"admin_url": admin, "storefront_url": storefront} if upload_ok else {},
            )

    monkeypatch.setattr(shop_mod, "ShopifyAdapter", _FakeAdapter)


_PRODUCT = {
    "title": "데모 상품",
    "price": 19.9,
    "currency": "USD",
    "sku": "DEMO-001",
    "images": [],  # 빈 이미지 → prevalidate의 HEAD 체크 비대상 (업로드 경로엔 영향 없음)
}


class TestUploadLiveSuccess:
    """라이브 Shopify 업로드 성공 경로."""

    def test_upload_returns_external_id_and_url(self, client, monkeypatch):
        _patch_shopify_adapter(monkeypatch, validate_ok=True, upload_ok=True)
        resp = client.post(
            "/seller/collect/upload",
            json={"product": _PRODUCT, "markets": ["shopify"]},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        result = data["result"]
        assert result["succeeded"] == 1
        assert result["failed"] == 0
        item = result["results"][0]
        assert item["market"] == "shopify"
        assert item["success"] is True
        assert item["external_product_id"] == "98765"
        assert item["external_url"].startswith("https://demo-shop.myshopify.com/products/")


class TestUploadLiveFailure:
    """라이브 Shopify 업로드 실패 — 정직한 error_code/hint 노출."""

    def test_api_failure_surfaces_error_code_and_hint(self, client, monkeypatch):
        _patch_shopify_adapter(monkeypatch, validate_ok=True, upload_ok=False, upload_msg="401 Unauthorized")
        resp = client.post(
            "/seller/collect/upload",
            json={"product": _PRODUCT, "markets": ["shopify"]},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        result = data["result"]
        assert result["failed"] == 1
        item = result["results"][0]
        assert item["success"] is False
        assert item["error_code"] == "api_error"
        assert "SHOPIFY_AUTO_TOKEN" in (item["hint"] or "")

    def test_validation_failure_surfaces_error_code(self, client, monkeypatch):
        _patch_shopify_adapter(monkeypatch, validate_ok=False)
        resp = client.post(
            "/seller/collect/upload",
            json={"product": _PRODUCT, "markets": ["shopify"]},
        )
        data = resp.get_json()
        item = data["result"]["results"][0]
        assert item["success"] is False
        assert item["error_code"] == "validation_failed"

    def test_exception_during_upload_is_caught_honestly(self, client, monkeypatch):
        _patch_shopify_adapter(monkeypatch, raise_on_upload=True)
        resp = client.post(
            "/seller/collect/upload",
            json={"product": _PRODUCT, "markets": ["shopify"]},
        )
        # 라우트는 절대 500으로 죽지 않고 항목 단위 실패로 정직하게 보고한다
        assert resp.status_code == 200
        item = resp.get_json()["result"]["results"][0]
        assert item["success"] is False
        assert item["error_code"] == "api_error"


class TestUploadMixedMarkets:
    """Shopify 성공 + 미연동 국내마켓 큐 적재가 한 응답에 정직하게 집계된다."""

    def test_shopify_success_and_domestic_queued(self, client, monkeypatch):
        _patch_shopify_adapter(monkeypatch, validate_ok=True, upload_ok=True)
        resp = client.post(
            "/seller/collect/upload",
            json={"product": _PRODUCT, "markets": ["shopify", "coupang"]},
        )
        data = resp.get_json()
        result = data["result"]
        assert result["total"] == 2
        assert result["succeeded"] == 1
        by_market = {r["market"]: r for r in result["results"]}
        assert by_market["shopify"]["success"] is True
        # 쿠팡은 실 업로더 모듈 미연동 → 큐 적재 또는 실패로 정직 표기 (성공이 아님)
        assert by_market["coupang"]["success"] is False
