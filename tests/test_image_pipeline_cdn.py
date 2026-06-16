"""tests/test_image_pipeline_cdn.py — Phase 207: 이미지 파이프라인 CDN 업로드 실구현.

처리된 이미지 바이트를 Cloudinary에 업로드해 새 URL을 발급(stub 제거).
미설정/dry-run/실패 시 정직하게 원본 URL 유지(cdn_uploaded=False).
"""
from __future__ import annotations

import importlib
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

CDN_ENV = {
    "CLOUDINARY_CLOUD_NAME": "testcloud",
    "CLOUDINARY_API_KEY": "key123",
    "CLOUDINARY_API_SECRET": "secret456",
}


def _reload(monkeypatch, **env):
    # 다른 테스트가 남긴 전역 상태로부터 격리 (순서 비의존).
    monkeypatch.delenv("ADAPTER_DRY_RUN", raising=False)
    monkeypatch.delenv("IMAGE_CDN_UPLOAD_ENABLED", raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import src.media.image_pipeline as m
    importlib.reload(m)
    return m


# ---------------------------------------------------------------------------
# _cloudinary_configured
# ---------------------------------------------------------------------------

class TestCloudinaryConfigured:
    def test_configured_true(self, monkeypatch):
        m = _reload(monkeypatch, **CDN_ENV)
        assert m._cloudinary_configured() is True

    def test_configured_false_when_missing(self, monkeypatch):
        for k in CDN_ENV:
            monkeypatch.delenv(k, raising=False)
        import src.media.image_pipeline as m
        importlib.reload(m)
        assert m._cloudinary_configured() is False


# ---------------------------------------------------------------------------
# _upload_to_cdn
# ---------------------------------------------------------------------------

class TestUploadToCdn:
    def test_returns_none_when_not_configured(self, monkeypatch):
        for k in CDN_ENV:
            monkeypatch.delenv(k, raising=False)
        import src.media.image_pipeline as m
        importlib.reload(m)
        assert m._upload_to_cdn(b"abc") is None

    def test_returns_none_when_empty_bytes(self, monkeypatch):
        m = _reload(monkeypatch, **CDN_ENV)
        assert m._upload_to_cdn(b"") is None

    def test_returns_none_on_dry_run(self, monkeypatch):
        m = _reload(monkeypatch, ADAPTER_DRY_RUN="1", **CDN_ENV)
        assert m._upload_to_cdn(b"abc") is None
        monkeypatch.delenv("ADAPTER_DRY_RUN", raising=False)

    def test_returns_none_when_disabled(self, monkeypatch):
        m = _reload(monkeypatch, IMAGE_CDN_UPLOAD_ENABLED="0", **CDN_ENV)
        assert m._upload_to_cdn(b"abc") is None

    def test_uploads_and_returns_secure_url(self, monkeypatch):
        m = _reload(monkeypatch, **CDN_ENV)
        fake_uploader = MagicMock()
        fake_uploader.upload.return_value = {"secure_url": "https://res.cloudinary.com/testcloud/image/upload/x.webp"}
        fake_cloudinary = SimpleNamespace(config=MagicMock(), uploader=fake_uploader)
        monkeypatch.setitem(sys.modules, "cloudinary", fake_cloudinary)
        monkeypatch.setitem(sys.modules, "cloudinary.uploader", fake_uploader)

        url = m._upload_to_cdn(b"imagebytes", prefer_webp=True)
        assert url == "https://res.cloudinary.com/testcloud/image/upload/x.webp"
        # webp 선호 시 format 옵션 전달
        _, kwargs = fake_uploader.upload.call_args
        assert kwargs.get("format") == "webp"
        assert kwargs.get("resource_type") == "image"

    def test_upload_exception_returns_none(self, monkeypatch):
        m = _reload(monkeypatch, **CDN_ENV)
        fake_uploader = MagicMock()
        fake_uploader.upload.side_effect = RuntimeError("boom")
        fake_cloudinary = SimpleNamespace(config=MagicMock(), uploader=fake_uploader)
        monkeypatch.setitem(sys.modules, "cloudinary", fake_cloudinary)
        monkeypatch.setitem(sys.modules, "cloudinary.uploader", fake_uploader)
        assert m._upload_to_cdn(b"imagebytes") is None


# ---------------------------------------------------------------------------
# process_image 통합 — 미설정 시 정직하게 원본 유지
# ---------------------------------------------------------------------------

class TestProcessImageCdnHonesty:
    def test_not_configured_keeps_original_url(self, monkeypatch):
        for k in CDN_ENV:
            monkeypatch.delenv(k, raising=False)
        monkeypatch.setenv("IMAGE_PIPELINE_ENABLED", "0")  # 다운로드 없이 빠른 경로
        import src.media.image_pipeline as m
        importlib.reload(m)
        res = m.process_image("https://example.com/img.jpg")
        assert res.processed_url == "https://example.com/img.jpg"
        assert res.cdn_uploaded is False

    def test_result_dict_has_cdn_uploaded(self, monkeypatch):
        m = _reload(monkeypatch, IMAGE_PIPELINE_ENABLED="0")
        res = m.process_image("https://example.com/img.jpg")
        assert "cdn_uploaded" in res.to_dict()


# ---------------------------------------------------------------------------
# stats — cdn 필드
# ---------------------------------------------------------------------------

class TestStatsCdn:
    def test_stats_include_cdn_fields(self, monkeypatch):
        m = _reload(monkeypatch, **CDN_ENV)
        from src.media.image_pipeline import ImageProcessResult
        results = [
            ImageProcessResult(original_url="a", processed_url="cdn-a", cdn_uploaded=True, success=True),
            ImageProcessResult(original_url="b", processed_url="b", cdn_uploaded=False, success=True),
        ]
        stats = m.image_pipeline_stats(results)
        assert stats["cdn_uploaded"] == 1
        assert stats["cdn_configured"] is True
