"""tests/test_channel_sync_uploaders.py — 국내 마켓 실채널 업로더 브리지 검증.

UploadDispatcher의 product_data를 src.uploaders.*Uploader 형식으로 변환하고
자격증명/실패/성공 경로를 정직하게 처리하는지 목(mock) API로 고정한다.

실 API 호출은 자격증명이 있을 때만 발생하므로, 여기서는 업로더 클래스를 목 처리하여
필드/가격 매핑과 디스패처 통합의 정합성만 검증한다(라이브 검증은 운영 환경에서 수행).
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ─── to_collected 매핑 ────────────────────────────────────────────────────────

class TestToCollectedMapping:
    """디스패처 product_data → uploaders collected 변환."""

    def test_krw_sell_price_priority(self):
        from src.channel_sync._channel_bridge import to_collected
        # sell_price_krw가 최우선
        c = to_collected({"title": "T", "sell_price_krw": 19900, "price_krw": 9000})
        assert c["sell_price_krw"] == 19900
        assert c["price_krw"] == 9000

    def test_falls_back_to_recommended_then_price_krw(self):
        from src.channel_sync._channel_bridge import to_collected
        c = to_collected({"title": "T", "recommended_price": 15000})
        assert c["sell_price_krw"] == 15000

    def test_krw_currency_price_used_when_no_explicit_krw(self):
        from src.channel_sync._channel_bridge import to_collected
        c = to_collected({"title": "T", "price": 12000, "currency": "KRW"})
        assert c["sell_price_krw"] == 12000

    def test_non_krw_price_not_used_as_krw(self):
        from src.channel_sync._channel_bridge import to_collected
        # USD 19.9는 원화 판매가로 쓰이면 안 됨 → 0
        c = to_collected({"title": "T", "price": 19.9, "currency": "USD"})
        assert c["sell_price_krw"] == 0

    def test_title_and_category_fallbacks(self):
        from src.channel_sync._channel_bridge import to_collected
        c = to_collected({"title": "기본제목", "sell_price_krw": 1000})
        assert c["title_ko"] == "기본제목"
        assert c["title_original"] == "기본제목"
        assert c["category_code"] == "GEN"

    def test_keywords_become_tags(self):
        from src.channel_sync._channel_bridge import to_collected
        c = to_collected({"title": "T", "sell_price_krw": 1000, "keywords": ["a", "b"]})
        assert c["tags"] == ["a", "b"]


# ─── run_upload 공통 경로 ─────────────────────────────────────────────────────

class _FakeUploader:
    def __init__(self, resp):
        self._resp = resp
        self.prepared = None

    def prepare_product(self, collected):
        self.prepared = collected
        return {"_prepared": True, **collected}

    def upload_product(self, prepared):
        return self._resp


class TestRunUpload:
    """run_upload 자격증명/실패/성공 처리."""

    def test_missing_credentials_raises(self, monkeypatch):
        from src.channel_sync._channel_bridge import run_upload, ChannelCredentialsMissing
        monkeypatch.delenv("FOO_KEY", raising=False)
        with pytest.raises(ChannelCredentialsMissing):
            run_upload(_FakeUploader({"success": True}), {"sell_price_krw": 1000},
                       required_envs=["FOO_KEY"], market_label="테스트")

    def test_zero_krw_price_raises_upload_error(self, monkeypatch):
        from src.channel_sync._channel_bridge import run_upload, ChannelUploadError
        with pytest.raises(ChannelUploadError):
            run_upload(_FakeUploader({"success": True}), {"title": "T", "price": 19.9, "currency": "USD"},
                       required_envs=[], market_label="테스트")

    def test_api_failure_raises_upload_error(self):
        from src.channel_sync._channel_bridge import run_upload, ChannelUploadError
        with pytest.raises(ChannelUploadError):
            run_upload(_FakeUploader({"success": False, "error": "401"}), {"sell_price_krw": 1000},
                       required_envs=[], market_label="테스트")

    def test_success_returns_product_id_and_url(self):
        from src.channel_sync._channel_bridge import run_upload
        out = run_upload(
            _FakeUploader({"success": True, "product_id": "P123", "url": "https://x/p/123"}),
            {"sell_price_krw": 1000},
            required_envs=[], market_label="테스트",
        )
        assert out == {"product_id": "P123", "url": "https://x/p/123"}


# ─── 마켓별 브리지 (목 업로더) ────────────────────────────────────────────────

class TestCoupangBridge:
    def test_upload_success(self, monkeypatch):
        import src.uploaders.coupang_uploader as cu
        monkeypatch.setenv("COUPANG_ACCESS_KEY", "a")
        monkeypatch.setenv("COUPANG_SECRET_KEY", "b")
        monkeypatch.setenv("COUPANG_VENDOR_ID", "c")

        class _FakeCoupang:
            def prepare_product(self, collected):
                return collected

            def upload_product(self, prepared):
                return {"success": True, "product_id": "CP1", "url": "https://coupang/CP1"}

        monkeypatch.setattr(cu, "CoupangUploader", _FakeCoupang)
        from src.channel_sync import coupang_uploader
        out = coupang_uploader.upload({"title": "T", "sell_price_krw": 19900})
        assert out["product_id"] == "CP1"

    def test_missing_creds_raises(self, monkeypatch):
        for k in ("COUPANG_ACCESS_KEY", "COUPANG_SECRET_KEY", "COUPANG_VENDOR_ID"):
            monkeypatch.delenv(k, raising=False)
        from src.channel_sync import coupang_uploader
        from src.channel_sync._channel_bridge import ChannelCredentialsMissing
        with pytest.raises(ChannelCredentialsMissing):
            coupang_uploader.upload({"title": "T", "sell_price_krw": 19900})


class TestSmartstoreBridge:
    def test_upload_success(self, monkeypatch):
        import src.uploaders.naver_uploader as nu
        monkeypatch.setenv("NAVER_CLIENT_ID", "a")
        monkeypatch.setenv("NAVER_CLIENT_SECRET", "b")

        class _FakeNaver:
            def prepare_product(self, collected):
                return collected

            def upload_product(self, prepared):
                return {"success": True, "product_id": "NS1", "url": "https://smartstore/NS1"}

        monkeypatch.setattr(nu, "NaverSmartStoreUploader", _FakeNaver)
        from src.channel_sync import smartstore_uploader
        out = smartstore_uploader.upload({"title": "T", "sell_price_krw": 25000})
        assert out["product_id"] == "NS1"


class TestElevenstBridge:
    def test_upload_success(self, monkeypatch):
        import src.uploaders.elevenst_uploader as eu
        monkeypatch.setenv("ELEVENST_API_KEY", "k")

        class _FakeEleven:
            def prepare_product(self, collected):
                return collected

            def upload_product(self, prepared):
                return {"success": True, "product_id": "E1", "url": "https://11st/E1"}

        monkeypatch.setattr(eu, "ElevenStUploader", _FakeEleven)
        from src.channel_sync import elevenst_uploader
        out = elevenst_uploader.upload({"title": "T", "sell_price_krw": 12000})
        assert out["product_id"] == "E1"

    def test_missing_creds_raises(self, monkeypatch):
        monkeypatch.delenv("ELEVENST_API_KEY", raising=False)
        from src.channel_sync import elevenst_uploader
        from src.channel_sync._channel_bridge import ChannelCredentialsMissing
        with pytest.raises(ChannelCredentialsMissing):
            elevenst_uploader.upload({"title": "T", "sell_price_krw": 12000})


# ─── 디스패처 통합 ────────────────────────────────────────────────────────────

class TestDispatcherIntegration:
    """디스패처 _upload_coupang/_upload_smartstore가 브리지 결과를 정직하게 표면화."""

    def test_coupang_success_sets_external_fields(self, monkeypatch):
        import src.uploaders.coupang_uploader as cu
        monkeypatch.setenv("COUPANG_ACCESS_KEY", "a")
        monkeypatch.setenv("COUPANG_SECRET_KEY", "b")
        monkeypatch.setenv("COUPANG_VENDOR_ID", "c")

        class _FakeCoupang:
            def prepare_product(self, collected):
                return collected

            def upload_product(self, prepared):
                return {"success": True, "product_id": "CP9", "url": "https://coupang/CP9"}

        monkeypatch.setattr(cu, "CoupangUploader", _FakeCoupang)
        from src.seller_console.upload_dispatcher import UploadDispatcher
        result = UploadDispatcher()._upload_coupang({"title": "T", "sell_price_krw": 19900})
        assert result.success is True
        assert result.external_product_id == "CP9"
        assert result.external_url == "https://coupang/CP9"

    def test_coupang_missing_creds_is_token_missing(self, monkeypatch):
        for k in ("COUPANG_ACCESS_KEY", "COUPANG_SECRET_KEY", "COUPANG_VENDOR_ID"):
            monkeypatch.delenv(k, raising=False)
        from src.seller_console.upload_dispatcher import UploadDispatcher
        result = UploadDispatcher()._upload_coupang({"title": "T", "sell_price_krw": 19900})
        assert result.success is False
        assert result.error_code == "token_missing"
        assert result.hint

    def test_coupang_api_failure_is_api_error(self, monkeypatch):
        import src.uploaders.coupang_uploader as cu
        monkeypatch.setenv("COUPANG_ACCESS_KEY", "a")
        monkeypatch.setenv("COUPANG_SECRET_KEY", "b")
        monkeypatch.setenv("COUPANG_VENDOR_ID", "c")

        class _FakeCoupang:
            def prepare_product(self, collected):
                return collected

            def upload_product(self, prepared):
                return {"success": False, "error": "401 Unauthorized"}

        monkeypatch.setattr(cu, "CoupangUploader", _FakeCoupang)
        from src.seller_console.upload_dispatcher import UploadDispatcher
        result = UploadDispatcher()._upload_coupang({"title": "T", "sell_price_krw": 19900})
        assert result.success is False
        assert result.error_code == "api_error"

    def test_elevenst_success_sets_external_fields(self, monkeypatch):
        import src.uploaders.elevenst_uploader as eu
        monkeypatch.setenv("ELEVENST_API_KEY", "k")

        class _FakeEleven:
            def prepare_product(self, collected):
                return collected

            def upload_product(self, prepared):
                return {"success": True, "product_id": "E9", "url": "https://11st/E9"}

        monkeypatch.setattr(eu, "ElevenStUploader", _FakeEleven)
        from src.seller_console.upload_dispatcher import UploadDispatcher
        result = UploadDispatcher()._upload_elevenst({"title": "T", "sell_price_krw": 12000})
        assert result.success is True
        assert result.external_product_id == "E9"

    def test_elevenst_missing_creds_is_token_missing(self, monkeypatch):
        monkeypatch.delenv("ELEVENST_API_KEY", raising=False)
        from src.seller_console.upload_dispatcher import UploadDispatcher
        result = UploadDispatcher()._upload_elevenst({"title": "T", "sell_price_krw": 12000})
        assert result.success is False
        assert result.error_code == "token_missing"
