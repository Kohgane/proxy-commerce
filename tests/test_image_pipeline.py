"""tests/test_image_pipeline.py — Phase 143: 이미지 파이프라인 테스트."""
from __future__ import annotations

import pytest


# ═══════════════════════════════════════════════════════════════════════════════
# ImageProcessResult
# ═══════════════════════════════════════════════════════════════════════════════

class TestImageProcessResult:
    def test_to_dict_keys(self):
        from src.media.image_pipeline import ImageProcessResult
        r = ImageProcessResult(
            original_url="https://example.com/img.jpg",
            processed_url="https://example.com/img.jpg",
        )
        d = r.to_dict()
        for key in ("original_url", "processed_url", "watermark_detected", "watermark_removed", "webp_converted", "success"):
            assert key in d

    def test_default_success_true(self):
        from src.media.image_pipeline import ImageProcessResult
        r = ImageProcessResult(original_url="u", processed_url="u")
        assert r.success is True

    def test_error_state(self):
        from src.media.image_pipeline import ImageProcessResult
        r = ImageProcessResult(original_url="u", processed_url="u", success=False, error="다운로드 실패")
        assert r.success is False
        d = r.to_dict()
        assert d["error"] == "다운로드 실패"


# ═══════════════════════════════════════════════════════════════════════════════
# process_image (network mocked)
# ═══════════════════════════════════════════════════════════════════════════════

class TestProcessImage:
    def test_pipeline_disabled_returns_original(self, monkeypatch):
        monkeypatch.setenv("IMAGE_PIPELINE_ENABLED", "0")
        import importlib
        import src.media.image_pipeline as m
        importlib.reload(m)
        result = m.process_image("https://example.com/img.jpg")
        assert result.processed_url == "https://example.com/img.jpg"
        assert result.success is True

    def test_download_failure_returns_error(self, monkeypatch):
        monkeypatch.setenv("IMAGE_PIPELINE_ENABLED", "1")
        import importlib
        import src.media.image_pipeline as m
        importlib.reload(m)
        # 존재하지 않는 URL → 다운로드 실패
        result = m.process_image("https://nonexistent-host-xyz.invalid/img.jpg")
        assert result.success is False
        assert result.error is not None

    def test_process_image_returns_result_type(self, monkeypatch):
        monkeypatch.setenv("IMAGE_PIPELINE_ENABLED", "0")
        import importlib
        import src.media.image_pipeline as m
        importlib.reload(m)
        from src.media.image_pipeline import ImageProcessResult
        result = m.process_image("https://example.com/test.jpg")
        assert isinstance(result, ImageProcessResult)


# ═══════════════════════════════════════════════════════════════════════════════
# process_image_urls
# ═══════════════════════════════════════════════════════════════════════════════

class TestProcessImageUrls:
    def test_empty_list_returns_empty(self):
        from src.media.image_pipeline import process_image_urls
        assert process_image_urls([]) == []

    def test_pipeline_disabled_returns_original_urls(self, monkeypatch):
        monkeypatch.setenv("IMAGE_PIPELINE_ENABLED", "0")
        import importlib
        import src.media.image_pipeline as m
        importlib.reload(m)
        urls = ["https://example.com/a.jpg", "https://example.com/b.jpg"]
        result = m.process_image_urls(urls)
        assert result == urls

    def test_same_count_as_input(self, monkeypatch):
        monkeypatch.setenv("IMAGE_PIPELINE_ENABLED", "0")
        import importlib
        import src.media.image_pipeline as m
        importlib.reload(m)
        urls = ["https://example.com/a.jpg", "https://example.com/b.jpg", "https://example.com/c.jpg"]
        result = m.process_image_urls(urls)
        assert len(result) == len(urls)

    def test_returns_list_of_strings(self, monkeypatch):
        monkeypatch.setenv("IMAGE_PIPELINE_ENABLED", "0")
        import importlib
        import src.media.image_pipeline as m
        importlib.reload(m)
        result = m.process_image_urls(["https://example.com/img.jpg"])
        assert all(isinstance(u, str) for u in result)


# ═══════════════════════════════════════════════════════════════════════════════
# _detect_watermark (OpenCV graceful)
# ═══════════════════════════════════════════════════════════════════════════════

class TestDetectWatermark:
    def test_invalid_bytes_returns_false(self):
        from src.media.image_pipeline import _detect_watermark
        result = _detect_watermark(b"not_an_image")
        assert result is False

    def test_empty_bytes_returns_false(self):
        from src.media.image_pipeline import _detect_watermark
        result = _detect_watermark(b"")
        assert result is False


# ═══════════════════════════════════════════════════════════════════════════════
# _inpaint_watermark (graceful)
# ═══════════════════════════════════════════════════════════════════════════════

class TestInpaintWatermark:
    def test_invalid_bytes_returns_original(self):
        from src.media.image_pipeline import _inpaint_watermark
        original = b"not_an_image"
        result = _inpaint_watermark(original)
        assert result == original


# ═══════════════════════════════════════════════════════════════════════════════
# _resize_and_crop (Pillow graceful)
# ═══════════════════════════════════════════════════════════════════════════════

class TestResizeAndCrop:
    def test_invalid_bytes_returns_original(self):
        from src.media.image_pipeline import _resize_and_crop
        original = b"not_an_image"
        result = _resize_and_crop(original, 800, 800)
        assert result == original

    def test_pillow_resize(self):
        """실제 이미지 데이터로 리사이즈 테스트 (Pillow 설치 시)."""
        try:
            from PIL import Image
            import io
            img = Image.new("RGB", (1000, 1200), color=(128, 64, 32))
            buf = io.BytesIO()
            img.save(buf, format="JPEG")
            image_bytes = buf.getvalue()

            from src.media.image_pipeline import _resize_and_crop
            result = _resize_and_crop(image_bytes, 800, 800)
            # 결과가 이미지인지 확인
            result_img = Image.open(io.BytesIO(result))
            assert result_img.size == (800, 800)
        except ImportError:
            pytest.skip("Pillow not installed")


# ═══════════════════════════════════════════════════════════════════════════════
# _convert_to_webp (Pillow graceful)
# ═══════════════════════════════════════════════════════════════════════════════

class TestConvertToWebp:
    def test_invalid_bytes_returns_original(self):
        from src.media.image_pipeline import _convert_to_webp
        original = b"not_an_image"
        result = _convert_to_webp(original)
        assert result == original

    def test_pillow_webp_conversion(self):
        try:
            from PIL import Image
            import io
            img = Image.new("RGB", (100, 100), color=(0, 128, 255))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=95)
            jpeg_bytes = buf.getvalue()

            from src.media.image_pipeline import _convert_to_webp
            result = _convert_to_webp(jpeg_bytes)
            # 결과가 유효한 이미지인지 확인
            result_img = Image.open(io.BytesIO(result))
            assert result_img.format in ("WEBP", "JPEG")  # WebP > JPEG 시 원본 반환
        except ImportError:
            pytest.skip("Pillow not installed")


# ═══════════════════════════════════════════════════════════════════════════════
# image_pipeline_stats
# ═══════════════════════════════════════════════════════════════════════════════

class TestImagePipelineStats:
    def _make_result(self, **kwargs):
        from src.media.image_pipeline import ImageProcessResult
        defaults = dict(original_url="u", processed_url="u")
        defaults.update(kwargs)
        return ImageProcessResult(**defaults)

    def test_empty_list(self):
        from src.media.image_pipeline import image_pipeline_stats
        stats = image_pipeline_stats([])
        assert stats["total"] == 0
        assert stats["success_pct"] == 0

    def test_all_success(self):
        from src.media.image_pipeline import image_pipeline_stats
        results = [self._make_result(success=True) for _ in range(5)]
        stats = image_pipeline_stats(results)
        assert stats["total"] == 5
        assert stats["success"] == 5
        assert stats["success_pct"] == 100

    def test_partial_success(self):
        from src.media.image_pipeline import image_pipeline_stats
        results = [
            self._make_result(success=True),
            self._make_result(success=True),
            self._make_result(success=False),
        ]
        stats = image_pipeline_stats(results)
        assert stats["success"] == 2
        assert stats["total"] == 3

    def test_watermark_counts(self):
        from src.media.image_pipeline import image_pipeline_stats
        results = [
            self._make_result(watermark_detected=True, watermark_removed=True),
            self._make_result(watermark_detected=True, watermark_removed=False),
            self._make_result(watermark_detected=False),
        ]
        stats = image_pipeline_stats(results)
        assert stats["watermark_detected"] == 2
        assert stats["watermark_removed"] == 1

    def test_webp_count(self):
        from src.media.image_pipeline import image_pipeline_stats
        results = [
            self._make_result(webp_converted=True),
            self._make_result(webp_converted=True),
            self._make_result(webp_converted=False),
        ]
        stats = image_pipeline_stats(results)
        assert stats["webp_converted"] == 2

    def test_pipeline_enabled_flag_in_stats(self, monkeypatch):
        monkeypatch.setenv("IMAGE_PIPELINE_ENABLED", "0")
        import importlib
        import src.media.image_pipeline as m
        importlib.reload(m)
        stats = m.image_pipeline_stats([])
        assert stats["pipeline_enabled"] is False

    def test_inpaint_flag_in_stats(self, monkeypatch):
        monkeypatch.setenv("IMAGE_INPAINT_ENABLED", "0")
        import importlib
        import src.media.image_pipeline as m
        importlib.reload(m)
        stats = m.image_pipeline_stats([])
        assert stats["inpaint_enabled"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 채널별 설정 상수
# ═══════════════════════════════════════════════════════════════════════════════

class TestChannelConfig:
    def test_channel_crop_ratios(self):
        from src.media.image_pipeline import _CHANNEL_CROP_RATIOS
        assert "coupang" in _CHANNEL_CROP_RATIOS
        assert "smartstore" in _CHANNEL_CROP_RATIOS
        w, h = _CHANNEL_CROP_RATIOS["coupang"]
        assert w == 1 and h == 1  # 정방형

    def test_channel_min_resolution(self):
        from src.media.image_pipeline import _CHANNEL_MIN_RESOLUTION
        assert _CHANNEL_MIN_RESOLUTION["coupang"] == (800, 800)
        assert _CHANNEL_MIN_RESOLUTION["smartstore"] == (1000, 1000)
