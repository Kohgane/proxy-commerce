"""tests/test_verify_market_connections.py — 마켓 라이브 검증 도구 + 별칭 env 검증.

라이브 검증 스크립트가 진단/디스패처의 서로 다른 키 네임스페이스를 올바르게 잇고,
실제 업로드 경로가 쓰는 환경변수 별칭(WOO_*, NAVER_COMMERCE_*)을
prevalidate가 정확히 인정하는지 고정한다.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestPrevalidateEnvAliases:
    """실제 업로드 경로가 쓰는 환경변수 별칭을 prevalidate가 인정한다."""

    def _prevalidate(self, market):
        from src.seller_console.upload_dispatcher import UploadDispatcher
        prod = {"title": "T", "sell_price_krw": 19900, "price": 19900, "currency": "KRW"}
        return UploadDispatcher().prevalidate(prod, [market])[0]

    def test_woocommerce_accepts_woo_names(self, monkeypatch):
        for k in ("WC_URL", "WC_KEY", "WC_SECRET"):
            monkeypatch.delenv(k, raising=False)
        monkeypatch.setenv("WOO_BASE_URL", "https://x")
        monkeypatch.setenv("WOO_CK", "ck")
        monkeypatch.setenv("WOO_CS", "cs")
        r = self._prevalidate("woocommerce")
        assert r.ok is True

    def test_woocommerce_accepts_wc_names(self, monkeypatch):
        for k in ("WOO_BASE_URL", "WOO_CK", "WOO_CS"):
            monkeypatch.delenv(k, raising=False)
        monkeypatch.setenv("WC_URL", "https://x")
        monkeypatch.setenv("WC_KEY", "ck")
        monkeypatch.setenv("WC_SECRET", "cs")
        r = self._prevalidate("woocommerce")
        assert r.ok is True

    def test_woocommerce_missing_is_token_missing(self, monkeypatch):
        for k in ("WC_URL", "WC_KEY", "WC_SECRET", "WOO_BASE_URL", "WOO_CK", "WOO_CS"):
            monkeypatch.delenv(k, raising=False)
        r = self._prevalidate("woocommerce")
        assert r.ok is False
        assert r.error_code == "token_missing"

    def test_smartstore_accepts_commerce_names(self, monkeypatch):
        for k in ("NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET"):
            monkeypatch.delenv(k, raising=False)
        monkeypatch.setenv("NAVER_COMMERCE_CLIENT_ID", "id")
        monkeypatch.setenv("NAVER_COMMERCE_CLIENT_SECRET", "sec")
        monkeypatch.setenv("SMARTSTORE_APPROVED", "1")   # v61 STEP3: 게이트 통과 후 env-alias 검증
        r = self._prevalidate("smartstore")
        assert r.ok is True


class TestVerifyScript:
    """verify_market_connections 도구 동작."""

    def test_11st_maps_to_dispatcher_elevenst(self, monkeypatch):
        # 진단 키 '11st' → 디스패처 키 'elevenst'로 변환되어 unsupported_market이 아니어야 한다
        for k in ("ELEVENST_API_KEY",):
            monkeypatch.delenv(k, raising=False)
        from scripts.verify_market_connections import verify_market
        row = verify_market("11st")
        assert row["market"] == "11st"
        pv = row["prevalidation"]
        assert pv is not None
        assert pv["error_code"] != "unsupported_market"
        assert pv["error_code"] == "token_missing"

    def test_verify_market_reports_status(self, monkeypatch):
        for k in ("COUPANG_ACCESS_KEY", "COUPANG_SECRET_KEY", "COUPANG_VENDOR_ID"):
            monkeypatch.delenv(k, raising=False)
        from scripts.verify_market_connections import verify_market
        row = verify_market("coupang")
        assert row["status"] == "token_missing"
        assert row["docs_path"].endswith("COUPANG.md")

    def test_all_market_guides_verifiable(self):
        from scripts.verify_market_connections import verify_market
        from src.seller_console.market_integration_diagnostics import MARKET_GUIDES
        for market in MARKET_GUIDES:
            row = verify_market(market)
            assert row["market"] == market
            # 사전검증이 unsupported_market으로 깨지지 않아야 한다(키 매핑 정합성)
            pv = row.get("prevalidation") or {}
            assert pv.get("error_code") != "unsupported_market"
