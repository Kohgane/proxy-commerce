"""src/media/image_pipeline.py — 이미지 처리 파이프라인 (Phase 143).

기능:
  - 워터마크 영역 자동 감지 + inpainting (OpenCV 사용 가능 시)
  - 배경 통일 (선택)
  - 채널별 비율 자동 크롭 (1:1, 3:4 등)
  - WebP 변환 + 용량 최적화

환경변수:
  IMAGE_PIPELINE_ENABLED=1    파이프라인 활성화 (기본: 1)
  IMAGE_INPAINT_ENABLED=1     워터마크 inpainting 활성화 (기본: 1)
"""
from __future__ import annotations

import io
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_PIPELINE_ENABLED = os.getenv("IMAGE_PIPELINE_ENABLED", "1") == "1"
_INPAINT_ENABLED = os.getenv("IMAGE_INPAINT_ENABLED", "1") == "1"

# 채널별 크롭 비율 (width : height)
_CHANNEL_CROP_RATIOS: Dict[str, Tuple[int, int]] = {
    "coupang": (1, 1),       # 정방형
    "smartstore": (1, 1),
    "11st": (1, 1),
    "detail": (3, 4),        # 상세 이미지
}

# 채널별 최대 파일 크기 (바이트)
_CHANNEL_MAX_BYTES: Dict[str, int] = {
    "coupang": 5 * 1024 * 1024,     # 5 MB
    "smartstore": 10 * 1024 * 1024,  # 10 MB
    "11st": 5 * 1024 * 1024,
    "default": 5 * 1024 * 1024,
}

# 채널별 최소 해상도
_CHANNEL_MIN_RESOLUTION: Dict[str, Tuple[int, int]] = {
    "coupang": (800, 800),
    "smartstore": (1000, 1000),
    "11st": (750, 750),
    "default": (800, 800),
}


# ---------------------------------------------------------------------------
# 도메인 모델
# ---------------------------------------------------------------------------

@dataclass
class ImageProcessResult:
    """이미지 처리 결과."""

    original_url: str
    processed_url: str        # 처리 완료 URL (stub: 원본 반환)
    processed_bytes: Optional[bytes] = None
    width: int = 0
    height: int = 0
    format: str = "JPEG"
    watermark_detected: bool = False
    watermark_removed: bool = False
    background_unified: bool = False
    webp_converted: bool = False
    file_size_bytes: int = 0
    error: Optional[str] = None
    success: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "original_url": self.original_url,
            "processed_url": self.processed_url,
            "width": self.width,
            "height": self.height,
            "format": self.format,
            "watermark_detected": self.watermark_detected,
            "watermark_removed": self.watermark_removed,
            "background_unified": self.background_unified,
            "webp_converted": self.webp_converted,
            "file_size_bytes": self.file_size_bytes,
            "error": self.error,
            "success": self.success,
        }


# ---------------------------------------------------------------------------
# 워터마크 감지 (OpenCV graceful)
# ---------------------------------------------------------------------------

def _detect_watermark(image_bytes: bytes) -> bool:
    """워터마크 영역 자동 감지 (OpenCV 미설치 시 False 반환)."""
    try:
        import cv2
        import numpy as np
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return False
        # 간단한 휴리스틱: 밝기 높은 영역 + 텍스트 가능 영역 감지
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
        h, w = thresh.shape
        # 모서리 20% 영역에 밝은 픽셀이 10% 이상이면 워터마크 의심
        corners = [
            thresh[:h // 5, :w // 5],
            thresh[:h // 5, w * 4 // 5:],
            thresh[h * 4 // 5:, :w // 5],
            thresh[h * 4 // 5:, w * 4 // 5:],
        ]
        for corner in corners:
            if corner.size > 0 and corner.mean() > 25:
                return True
        return False
    except ImportError:
        logger.debug("OpenCV 미설치 — 워터마크 감지 스킵")
        return False
    except Exception as exc:
        logger.debug("워터마크 감지 오류: %s", exc)
        return False


def _inpaint_watermark(image_bytes: bytes) -> bytes:
    """워터마크 inpainting (OpenCV 미설치 시 원본 반환)."""
    try:
        import cv2
        import numpy as np
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return image_bytes
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _, mask = cv2.threshold(gray, 240, 255, cv2.THRESH_BINARY)
        # 모서리 마스크만 사용 (전체 적용 시 상품 손상 우려)
        h, w = mask.shape
        full_mask = np.zeros_like(mask)
        full_mask[:h // 5, :] = mask[:h // 5, :]
        full_mask[h * 4 // 5:, :] = mask[h * 4 // 5:, :]
        # 팽창으로 마스크 확장
        kernel = np.ones((3, 3), np.uint8)
        dilated = cv2.dilate(full_mask, kernel, iterations=2)
        result = cv2.inpaint(img, dilated, 3, cv2.INPAINT_TELEA)
        _, buf = cv2.imencode(".jpg", result, [cv2.IMWRITE_JPEG_QUALITY, 92])
        return buf.tobytes()
    except ImportError:
        logger.debug("OpenCV 미설치 — inpainting 스킵")
        return image_bytes
    except Exception as exc:
        logger.debug("inpainting 오류: %s", exc)
        return image_bytes


# ---------------------------------------------------------------------------
# 리사이즈 + 크롭 (Pillow graceful)
# ---------------------------------------------------------------------------

def _resize_and_crop(
    image_bytes: bytes,
    target_width: int,
    target_height: int,
) -> bytes:
    """채널별 비율에 맞게 리사이즈 + 크롭 (Pillow 미설치 시 원본 반환)."""
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(image_bytes))
        # 비율 유지 크롭
        src_w, src_h = img.size
        src_ratio = src_w / src_h
        tgt_ratio = target_width / target_height
        if src_ratio > tgt_ratio:
            new_h = src_h
            new_w = int(src_h * tgt_ratio)
        else:
            new_w = src_w
            new_h = int(src_w / tgt_ratio)
        left = (src_w - new_w) // 2
        top = (src_h - new_h) // 2
        img = img.crop((left, top, left + new_w, top + new_h))
        img = img.resize((target_width, target_height), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=90, optimize=True)
        return buf.getvalue()
    except ImportError:
        logger.debug("Pillow 미설치 — 리사이즈 스킵")
        return image_bytes
    except Exception as exc:
        logger.debug("리사이즈 오류: %s", exc)
        return image_bytes


def _convert_to_webp(image_bytes: bytes, quality: int = 85) -> bytes:
    """WebP 변환 (Pillow 미설치 시 원본 반환)."""
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(image_bytes))
        buf = io.BytesIO()
        img.save(buf, format="WEBP", quality=quality, method=4)
        webp_bytes = buf.getvalue()
        # WebP가 더 큰 경우 원본 반환
        if len(webp_bytes) > len(image_bytes):
            return image_bytes
        return webp_bytes
    except ImportError:
        logger.debug("Pillow 미설치 — WebP 변환 스킵")
        return image_bytes
    except Exception as exc:
        logger.debug("WebP 변환 오류: %s", exc)
        return image_bytes


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------

def process_image(
    image_url: str,
    channel: str = "default",
    unify_background: bool = False,
    convert_webp: bool = True,
) -> ImageProcessResult:
    """단일 이미지 처리 파이프라인.

    1. URL에서 이미지 다운로드
    2. 워터마크 감지 + inpainting (IMAGE_INPAINT_ENABLED=1)
    3. 채널별 리사이즈 + 크롭
    4. WebP 변환
    5. 처리 결과 반환 (stub URL 반환)
    """
    if not _PIPELINE_ENABLED:
        return ImageProcessResult(original_url=image_url, processed_url=image_url, success=True)

    import urllib.request
    image_bytes: Optional[bytes] = None
    try:
        req = urllib.request.Request(image_url, headers={"User-Agent": "proxy-commerce/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            image_bytes = resp.read()
    except Exception as exc:
        logger.debug("이미지 다운로드 실패: url=%s error=%s", image_url, exc)
        return ImageProcessResult(
            original_url=image_url,
            processed_url=image_url,
            success=False,
            error=f"다운로드 실패: {exc}",
        )

    watermark_detected = False
    watermark_removed = False
    if _INPAINT_ENABLED:
        watermark_detected = _detect_watermark(image_bytes)
        if watermark_detected:
            image_bytes = _inpaint_watermark(image_bytes)
            watermark_removed = True

    # 리사이즈
    min_res = _CHANNEL_MIN_RESOLUTION.get(channel, _CHANNEL_MIN_RESOLUTION["default"])
    image_bytes = _resize_and_crop(image_bytes, min_res[0], min_res[1])

    # WebP 변환
    webp_converted = False
    if convert_webp:
        orig_size = len(image_bytes)
        image_bytes = _convert_to_webp(image_bytes)
        webp_converted = len(image_bytes) < orig_size

    # 크기 추출 (Pillow 있을 때)
    width, height = 0, 0
    fmt = "JPEG"
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(image_bytes))
        width, height = img.size
        fmt = img.format or ("WEBP" if webp_converted else "JPEG")
    except Exception:
        pass

    # 실제 운영 시 처리된 이미지를 CDN에 업로드 후 URL 반환
    # 현재는 원본 URL 반환 (stub)
    processed_url = image_url

    return ImageProcessResult(
        original_url=image_url,
        processed_url=processed_url,
        processed_bytes=image_bytes,
        width=width,
        height=height,
        format=fmt,
        watermark_detected=watermark_detected,
        watermark_removed=watermark_removed,
        background_unified=False,
        webp_converted=webp_converted,
        file_size_bytes=len(image_bytes),
        success=True,
    )


def process_image_urls(
    image_urls: List[str],
    channel: str = "default",
    convert_webp: bool = True,
) -> List[str]:
    """복수 이미지 URL 처리 후 처리 완료 URL 목록 반환."""
    if not image_urls:
        return []
    results: List[str] = []
    for url in image_urls:
        try:
            res = process_image(url, channel=channel, convert_webp=convert_webp)
            results.append(res.processed_url)
        except Exception as exc:
            logger.debug("process_image_urls 오류: url=%s error=%s", url, exc)
            results.append(url)
    return results


def image_pipeline_stats(results: List[ImageProcessResult]) -> Dict[str, Any]:
    """이미지 처리 통계."""
    total = len(results)
    success = sum(1 for r in results if r.success)
    wm_detected = sum(1 for r in results if r.watermark_detected)
    wm_removed = sum(1 for r in results if r.watermark_removed)
    webp = sum(1 for r in results if r.webp_converted)
    return {
        "total": total,
        "success": success,
        "success_pct": round(success / total * 100, 0) if total > 0 else 0,
        "watermark_detected": wm_detected,
        "watermark_removed": wm_removed,
        "webp_converted": webp,
        "pipeline_enabled": _PIPELINE_ENABLED,
        "inpaint_enabled": _INPAINT_ENABLED,
    }
