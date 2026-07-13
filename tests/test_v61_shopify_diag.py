"""tests/test_v61_shopify_diag.py — v61 STEP2: Shopify 진단 (실 HTTP·본문·스코프, api_error 뭉뚱그림 금지).

/admin/diagnostics Shopify 사전점검: env 존재(값 미표시)→shop.json→상태·스코프. 실패 지점 구분
(미설정/401/403 스코프). 오류 본문 마스킹 + 실제 HTTP. API 버전 표기.
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")


class _Resp:
    def __init__(self, status, payload=None, text=""):
        self.status_code = status
        self.reason = "Forbidden" if status == 403 else ("Unauthorized" if status == 401 else "OK")
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def test_error_summary_masks_and_includes_http():
    from src.markets.adapters.shopify import ShopifyAdapter
    # JSON 오류 구조 없음 → HTTP 상태 + 본문(마스킹).
    r = _Resp(403, payload=None, text='forbidden: access_token=shpat_secret1234567890 denied')
    out = ShopifyAdapter._error_summary(r)
    assert "HTTP 403" in out
    assert "shpat_secret1234567890" not in out and "shpat_****7890" in out   # 마스킹


def test_check_connection_reports_api_version_on_success():
    from src.markets.adapters import shopify as sh
    ad = sh.ShopifyAdapter()
    ok = _Resp(200, payload={"data": {"shop": {"name": "catdyy", "myshopifyDomain": "catdyy.myshopify.com",
                                               "currencyCode": "USD", "plan": {"displayName": "Basic"}}}})
    with patch.object(ad, "_missing_config_env", return_value=[]), \
         patch.object(ad, "_has_client_credentials", return_value=False), \
         patch.object(ad, "_request_with_retry", return_value=ok):
        res = ad.check_connection()
    assert res["ok"] is True and res["api_version"]                        # 버전 표기


def test_shopify_read_step_distinguishes_failures():
    from src.seller_console import market_integration_diagnostics as md
    # 미설정
    with patch("src.markets.adapters.shopify.ShopifyAdapter.check_connection",
               return_value={"ok": False, "status": "not_configured", "missing_env": ["SHOPIFY_SHOP"],
                             "message": "설정 누락"}):
        s = md._shopify_read_step()
    assert s["error_code"] == "token_missing" and "SHOPIFY_SHOP" in s["detail"]
    assert "shpat" not in s["detail"]                                       # 값 미표시(이름만)
    # 403 스코프
    with patch("src.markets.adapters.shopify.ShopifyAdapter.check_connection",
               return_value={"ok": False, "status": "api_error", "http_status": 403,
                             "reason": "access denied", "message": "권한"}):
        s = md._shopify_read_step()
    assert s["error_code"] == "scope_insufficient" and "HTTP 403" in s["detail"]
    # 401 토큰
    with patch("src.markets.adapters.shopify.ShopifyAdapter.check_connection",
               return_value={"ok": False, "status": "api_error", "http_status": 401,
                             "reason": "invalid token", "message": "인증"}):
        s = md._shopify_read_step()
    assert s["error_code"] == "token_expired" and "HTTP 401" in s["detail"]


def test_no_bare_api_error_tautology():
    # api_error 코드가 남더라도 detail에 실제 HTTP·본문 요약이 있어 '뭉뚱그림'이 아님.
    from src.seller_console import market_integration_diagnostics as md
    with patch("src.markets.adapters.shopify.ShopifyAdapter.check_connection",
               return_value={"ok": False, "status": "api_error", "http_status": 500,
                             "reason": "internal server error at shop.json", "message": "서버 오류"}):
        s = md._shopify_read_step()
    assert s["error_code"] == "api_error"
    assert "HTTP 500" in s["detail"] and "internal server error" in s["detail"]
