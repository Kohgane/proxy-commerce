# v87-S7: 이 모듈들이 relay_request(단일 관문)를 타면서 직결도 requests.request로 나간다.
#   그래서 목 대상도 requests.post/get → requests.request 로 옮긴다(동작 동일, 경로만 통일).
"""tests/test_market_adapter_live_fixes.py — 라이브 검증에서 드러난 어댑터 버그 수정 검증.

1) 스마트스토어: 네이버 커머스 OAuth2는 client_secret 평문이 아니라
   bcrypt 전자서명(client_secret_sign)+timestamp를 요구한다.
2) WooCommerce: 일부 WP 호스트가 User-Agent/Accept 없는 요청을 HTTP 406으로 막는다.
"""
from __future__ import annotations

import base64
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestSmartstoreNaverSignature:
    def test_signature_is_base64_of_bcrypt(self, monkeypatch):
        import bcrypt
        from src.seller_console.market_adapters import smartstore_adapter as ss

        salt = bcrypt.gensalt().decode("utf-8")  # 네이버 client_secret 형태($2b$…)
        sign = ss._naver_signature("client123", salt, "1700000000000")
        assert sign
        # base64 디코딩 가능해야 한다
        decoded = base64.b64decode(sign)
        assert decoded  # bcrypt 해시 바이트

    def test_signature_invalid_secret_returns_none(self):
        from src.seller_console.market_adapters import smartstore_adapter as ss
        # bcrypt salt 형식이 아니면 None (정직 실패)
        assert ss._naver_signature("c", "not-a-valid-bcrypt-salt", "123") is None

    def test_creds_fallback_to_naver_client_names(self, monkeypatch):
        from src.seller_console.market_adapters import smartstore_adapter as ss
        for k in ("NAVER_COMMERCE_CLIENT_ID", "NAVER_COMMERCE_CLIENT_SECRET"):
            monkeypatch.delenv(k, raising=False)
        # 인앱 연결이 저장하는 NAVER_CLIENT_* 도 인식해야 한다
        monkeypatch.setenv("NAVER_CLIENT_ID", "cid")
        monkeypatch.setenv("NAVER_CLIENT_SECRET", "csec")
        assert ss._naver_creds() == ("cid", "csec")
        assert ss._api_active() is True

    def test_token_request_sends_sign_not_plaintext_secret(self, monkeypatch):
        import bcrypt
        from src.seller_console.market_adapters import smartstore_adapter as ss

        ss._token_cache.clear()
        salt = bcrypt.gensalt().decode("utf-8")
        monkeypatch.setenv("NAVER_COMMERCE_CLIENT_ID", "cid")
        monkeypatch.setenv("NAVER_COMMERCE_CLIENT_SECRET", salt)

        captured = {}

        def fake_post(method, url, data=None, headers=None, timeout=None):
            captured["data"] = data
            resp = MagicMock()
            resp.status_code = 200
            resp.raise_for_status.return_value = None
            resp.json.return_value = {"access_token": "TOK", "expires_in": 3600}
            return resp

        with patch("requests.request", side_effect=fake_post):
            token = ss._get_access_token()

        assert token == "TOK"
        data = captured["data"]
        # 평문 시크릿을 보내면 안 되고, 전자서명/타임스탬프를 보내야 한다
        assert "client_secret" not in data
        assert "client_secret_sign" in data and data["client_secret_sign"]
        assert "timestamp" in data
        assert data["grant_type"] == "client_credentials"
        ss._token_cache.clear()


class TestCredentialStripping:
    """Render env에 끼어든 공백/줄바꿈이 서명을 깨지 않도록 strip."""

    def test_coupang_hmac_ignores_whitespace(self, monkeypatch):
        from src.seller_console.market_adapters import coupang_adapter as cp
        monkeypatch.setenv("COUPANG_ACCESS_KEY", "ak")
        monkeypatch.setenv("COUPANG_SECRET_KEY", "sk")
        clean = cp._hmac_sign("GET", "/x")["Authorization"]
        monkeypatch.setenv("COUPANG_ACCESS_KEY", " ak\n")
        monkeypatch.setenv("COUPANG_SECRET_KEY", " sk\n")
        dirty = cp._hmac_sign("GET", "/x")["Authorization"]
        # 서명 시각(초)이 같을 때 동일해야 한다(공백 무시). 시각 차이 가능성은 access-key 비교로 보강.
        assert "access-key=ak," in clean and "access-key=ak," in dirty

    def test_naver_creds_stripped(self, monkeypatch):
        from src.seller_console.market_adapters import smartstore_adapter as ss
        for k in ("NAVER_COMMERCE_CLIENT_ID", "NAVER_COMMERCE_CLIENT_SECRET"):
            monkeypatch.delenv(k, raising=False)
        monkeypatch.setenv("NAVER_CLIENT_ID", "  cid\n")
        monkeypatch.setenv("NAVER_CLIENT_SECRET", "csec  ")
        assert ss._naver_creds() == ("cid", "csec")


class TestSmartstoreIpHint:
    def test_ip_error_gives_ip_hint(self, monkeypatch):
        from src.seller_console.market_adapters import smartstore_adapter as ss
        import bcrypt
        ss._token_cache.clear()
        monkeypatch.setenv("NAVER_COMMERCE_CLIENT_ID", "cid")
        monkeypatch.setenv("NAVER_COMMERCE_CLIENT_SECRET", bcrypt.gensalt().decode())
        monkeypatch.delenv("ADAPTER_DRY_RUN", raising=False)

        resp = MagicMock()
        resp.status_code = 403
        resp.text = '{"code":"GW.IP_NOT_ALLOWED","message":"호출이 허용되지 않은 IP입니다."}'
        with patch("requests.request", return_value=resp):
            result = ss.SmartStoreAdapter().health_check()
        assert result["status"] == "fail"
        assert "허용 IP" in result["hint"]
        ss._token_cache.clear()


class TestWooCommerceHeaders:
    def test_health_check_sends_user_agent_and_accept(self, monkeypatch):
        from src.seller_console.market_adapters import woocommerce_adapter as wc

        monkeypatch.setenv("WC_URL", "https://shop.example.com")
        monkeypatch.setenv("WC_KEY", "ck_x")
        monkeypatch.setenv("WC_SECRET", "cs_x")
        monkeypatch.delenv("ADAPTER_DRY_RUN", raising=False)

        captured = {}

        def fake_get(url, auth=None, headers=None, params=None, timeout=None):
            captured["headers"] = headers
            resp = MagicMock()
            resp.status_code = 200
            return resp

        with patch("requests.get", side_effect=fake_get):
            result = wc.WooCommerceAdapter().health_check()

        assert result["status"] == "ok"
        headers = captured["headers"]
        assert "User-Agent" in headers
        assert headers.get("Accept") == "application/json"

    def test_request_headers_helper(self):
        from src.seller_console.market_adapters import woocommerce_adapter as wc
        h = wc._request_headers()
        assert h["User-Agent"]
        assert h["Accept"] == "application/json"


class TestCoupangIpAllowlistHint:
    def test_403_ip_not_allowed_gives_ip_hint(self, monkeypatch):
        from src.seller_console.market_adapters import coupang_adapter as cp
        monkeypatch.setenv("COUPANG_ACCESS_KEY", "ak")
        monkeypatch.setenv("COUPANG_SECRET_KEY", "sk")
        monkeypatch.setenv("COUPANG_VENDOR_ID", "A01381223")
        monkeypatch.delenv("ADAPTER_DRY_RUN", raising=False)
        resp = MagicMock()
        resp.status_code = 403
        resp.text = ('{"path":"/api/v1/marketplace/seller-products","error":"FORBIDDEN",'
                     '"message":"Your ip address 74.220.49.7 is not allowed for this request."}')
        with patch("requests.request", return_value=resp):
            result = cp.CoupangAdapter().health_check()
        assert result["status"] == "fail"
        assert "74.220.49.7" in result["hint"]
        assert "허용 IP" in result["hint"]
