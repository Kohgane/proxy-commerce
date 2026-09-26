"""src/media/image_pipeline.py — 이미지 처리 파이프라인 (Phase 143).

기능:
  - 워터마크 영역 자동 감지 + inpainting (OpenCV 사용 가능 시)
  - 배경 통일 (선택)
  - 채널별 비율 자동 크롭 (1:1, 3:4 등)
  - WebP 변환 + 용량 최적화

환경변수:
  IMAGE_PIPELINE_ENABLED=1    파이프라인 활성화 (기본: 1)
  IMAGE_INPAINT_ENABLED=1     워터마크 inpainting 활성화 (**기본: 0** — 아래 F43)

## F43 — 워터마크 제거는 라이브에서 한 번도 돈 적이 없다 (실측 2026-09-20)

`cv2`가 `requirements.txt`·`Dockerfile` **어디에도 없었다**. 그래서 프로덕션 이미지엔
OpenCV가 없었고, 아래 두 함수는 `ImportError`를 **debug 로그로 삼키고** 각각
`False` / 원본을 돌려줬다. 결과 dict은 `watermark_detected: False`라고 말했는데,
그건 **「없다고 확인했다」가 아니라 「재지 않았다」**였다 — 화면에서 구분이 안 됐다.

같은 유형 재발이다: `Pillow`도 requirements 미기재로 조용히 무력이었다(카나리 3차에 발견).

그래서 이 파일이 바뀐 것 둘:

1. **사유를 싣는다.** `watermark_checked` + `watermark_reason` — 「안 쟀다」와
   「재고 없었다」가 다른 값으로 나온다. 못 잰 이유는 **WARNING**으로 남긴다(debug 아님).
2. **기본값을 실제 동작에 맞춘다.** D3가 `opencv-python-headless`를 이미지에 넣으면서
   이 경로가 **처음으로 살아난다.** 검토 없이 살아나면 그건 회귀다 — 모서리 inpaint가
   상품 사진을 건드린다. 그래서 `IMAGE_INPAINT_ENABLED` 기본값을 `0`으로 내린다.
   **지금까지 실제로 벌어진 일과 똑같이 둔다.** 켜는 건 오너가 env 하나로 한다.
"""
from __future__ import annotations

import io
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_PIPELINE_ENABLED = os.getenv("IMAGE_PIPELINE_ENABLED", "1") == "1"
# F43 — 기본 off. 이 기능은 cv2 부재로 **라이브에서 돈 적이 없다**(모듈 독스트링).
#   cv2가 이미지에 들어왔다고 해서 검토 없이 켜지면 그게 회귀다. 켜는 건 명시적으로.
_INPAINT_ENABLED = os.getenv("IMAGE_INPAINT_ENABLED", "0") == "1"
# 처리본을 CDN(Cloudinary)에 업로드해 새 URL을 발급할지. 기본 on이지만 자격증명 없으면 자동 비활성.
_CDN_UPLOAD_ENABLED = os.getenv("IMAGE_CDN_UPLOAD_ENABLED", "1") == "1"

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
    processed_url: str        # 처리 완료 URL (CDN 업로드 성공 시 호스팅 URL, 아니면 원본)
    processed_bytes: Optional[bytes] = None
    width: int = 0
    height: int = 0
    format: str = "JPEG"
    watermark_detected: bool = False
    watermark_removed: bool = False
    # F43 — **잰 적이 있나.** False면 `watermark_detected`는 「없다」가 아니라 「모른다」다.
    watermark_checked: bool = False
    watermark_reason: str = ""       # 못 쟀거나 못 지운 이유(빈 문자열 = 정상)
    background_unified: bool = False
    webp_converted: bool = False
    cdn_uploaded: bool = False   # 처리본을 CDN에 업로드해 새 URL을 발급했는지
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
            "watermark_checked": self.watermark_checked,
            "watermark_reason": self.watermark_reason,
            "background_unified": self.background_unified,
            "webp_converted": self.webp_converted,
            "cdn_uploaded": self.cdn_uploaded,
            "file_size_bytes": self.file_size_bytes,
            "error": self.error,
            "success": self.success,
        }


# ---------------------------------------------------------------------------
# 워터마크 감지 (OpenCV graceful)
# ---------------------------------------------------------------------------

_CV2_WARNED = False
_PIL_WARNED = False


def _warn_once(flag: str, message: str) -> None:
    """같은 부재를 **한 번은 WARNING으로** 알린다 — 매 장마다 울지는 않는다.

    debug로 두면 Render 로그(INFO 이상)에 안 남아 **기능이 죽어도 아무도 모른다**(F43).
    """
    if globals().get(flag):
        return
    globals()[flag] = True
    logger.warning("[이미지] %s", message)


def _load_cv2():
    """`(cv2, numpy, 사유)` — 못 불러오면 **사유가 남는다** (F43).

    예전엔 `ImportError`를 `logger.debug`로 삼켰다. Render 로그는 INFO 이상만 남으니
    **아무 데도 안 보였고**, 결과는 「워터마크 없음」이라고 말했다. 그건 거짓이 아니라
    **측정하지 않은 것**이었다. 이제 한 번은 WARNING으로 운다.
    """

    try:
        import cv2
        import numpy as np
        return cv2, np, ""
    except ImportError as exc:
        reason = f"OpenCV(cv2) 미설치 — 워터마크를 재지 못했습니다 ({exc})"
        _warn_once("_CV2_WARNED", reason)
        return None, None, reason


def _detect_watermark(image_bytes: bytes) -> tuple:
    """워터마크 감지 — `(감지됨, 사유)`.

    **사유가 비어 있을 때만 「쟀다」는 뜻이다.** 사유가 있으면 못 잰 것이고,
    그 경우 `감지됨=False`는 「없다」가 아니라 「모른다」다.
    """
    cv2, np, reason = _load_cv2()
    if reason:
        return False, reason
    try:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return False, "이미지를 디코드하지 못했습니다"
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
                return True, ""
        return False, ""          # 사유 없음 = **실제로 재고 없었다**
    except Exception as exc:
        logger.warning("[이미지] 워터마크 감지 오류: %s", exc)
        return False, f"감지 오류: {type(exc).__name__}"


def _inpaint_watermark(image_bytes: bytes) -> tuple:
    """워터마크 inpainting — `(바이트, 지웠나, 사유)`.

    실패하면 **원본을 그대로** 돌려주고 `지웠나=False`다. 못 지웠는데 지웠다고
    말하지 않는다.
    """
    cv2, np, reason = _load_cv2()
    if reason:
        return image_bytes, False, reason
    try:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return image_bytes, False, "이미지를 디코드하지 못했습니다"
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
        return buf.tobytes(), True, ""
    except Exception as exc:
        logger.warning("[이미지] inpainting 오류(원본 유지): %s", exc)
        return image_bytes, False, f"inpainting 오류: {type(exc).__name__}"


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
        # F43 동류 — Pillow도 한때 requirements 미기재로 조용히 무력이었다. 이제 운다.
        _warn_once("_PIL_WARNED", "Pillow 미설치 — 리사이즈를 건너뜁니다(원본 유지)")
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
        _warn_once("_PIL_WARNED", "Pillow 미설치 — WebP 변환을 건너뜁니다(원본 유지)")
        return image_bytes
    except Exception as exc:
        logger.debug("WebP 변환 오류: %s", exc)
        return image_bytes


# ---------------------------------------------------------------------------
# CDN 업로드 (Cloudinary graceful)
# ---------------------------------------------------------------------------

def _cloudinary_configured() -> bool:
    """Cloudinary 자격증명(cloud_name/api_key/api_secret) 모두 존재하는지."""
    return bool(
        os.getenv("CLOUDINARY_CLOUD_NAME")
        and os.getenv("CLOUDINARY_API_KEY")
        and os.getenv("CLOUDINARY_API_SECRET")
    )


def upload_bytes(image_bytes: bytes, *, prefer_webp: bool = False,
                 eager: Optional[list] = None, folder: str = "",
                 resource_type: str = "image", public_id: str = "",
                 context: Optional[Dict[str, str]] = None,
                 label: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """바이트 → Cloudinary. **결과를 dict 그대로** 돌려준다 (F31).

    ## 왜 dict인가

    실측(오너 2026-09-16, 진단 화면): 저장된 장 5(96~126KB) · Cloudinary env 3개 있음 ·
    DB 연결됨. 그런데 백필 사유가 **「업로드가 주소를 돌려주지 않았습니다」 ×5**였다.

    옛 `_upload_to_cdn`은 반환이 `Optional[str]`이라 **여섯 가지 실패를 전부 `None` 하나로**
    뭉갰다 — 토글 꺼짐 · 자격 미설정 · dry-run · SDK 미설치 · SDK 예외 · 응답에 URL 없음.
    호출부는 「주소가 없다」만 알 뿐 **왜인지는 알 길이 없었다**(사유는 로그 안에서 끝났다).

    > **반환 타입이 좁으면 사유가 죽는다.** `str | None`은 「됐다/안 됐다」만 담는다 —
    > 안 된 이유를 담을 칸이 없으니, 그 이유는 어디에도 안 남는다.

    돌려주는 것:
      `ok` · `secure_url` · `public_id` · `bytes` · `error`(사유) · `keys`(응답 키 목록)

    `keys`는 **다음 판의 답**이다. 응답은 왔는데 우리가 아는 키가 없으면,
    무슨 키가 왔는지를 그대로 실어야 이름을 고칠 수 있다(발명 금지).

    `eager`(D3-5): 업로드와 **같은 호출에서** 파생본을 만든다(동기 — `eager_async` 안 씀).
    결과는 `eager`로 그대로 싣는다. 생성형 효과(`gen_remove`)는 **fetch 이미지에 못 쓰므로**
    업로드가 먼저 있어야 하고, 그 업로드가 이 함수다 — 업로드 경로를 두 벌 두지 않는다.
    """
    from src.utils.redact import scrub_infra
    out: Dict[str, Any] = {"ok": False, "secure_url": "", "public_id": "",
                           "bytes": 0, "error": "", "keys": [], "eager": []}
    if not image_bytes:
        out["error"] = "올릴 바이트가 없습니다"
        return out
    # 토글·자격·dry-run을 **각각 다른 문장**으로 — 셋 다 「주소 없음」이던 것이 F31의 병이다.
    if not _CDN_UPLOAD_ENABLED:
        out["error"] = "IMAGE_CDN_UPLOAD_ENABLED=0 — 업로드가 꺼져 있습니다"
        return out
    if not _cloudinary_configured():
        missing = [n for n in ("CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY",
                               "CLOUDINARY_API_SECRET") if not os.getenv(n)]
        out["error"] = "Cloudinary 자격 미설정: " + ", ".join(missing)
        return out
    if os.getenv("ADAPTER_DRY_RUN", "0") == "1":
        out["error"] = "ADAPTER_DRY_RUN=1 — 실제 업로드를 막았습니다"
        return out
    try:
        import cloudinary
        import cloudinary.uploader
    except Exception as exc:
        # 예전엔 `logger.debug` 한 줄이라 **아무 데도 안 보였다**. 이제 사유가 화면까지 간다.
        out["error"] = f"cloudinary 라이브러리 없음: {type(exc).__name__}"
        return out
    try:
        cloudinary.config(
            cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
            api_key=os.getenv("CLOUDINARY_API_KEY"),
            api_secret=os.getenv("CLOUDINARY_API_SECRET"),
            secure=True,
        )
        # 0-b(오너 2026-09-26): 이름표는 **한 곳**(`image_label`)에서 — 벤치·셀러가 같은 규칙.
        if label:
            from src.media.image_label import upload_opts
            _lo = upload_opts(label)
            folder = folder or _lo["folder"]
            public_id = public_id or _lo["public_id"]
            context = context or _lo["context"]
        base = os.getenv("CLOUDINARY_FOLDER", "proxy-commerce")
        # F48-b — 인보이스 같은 **서류**는 상품 이미지와 다른 폴더(섞이지 않게)·PDF 허용(auto).
        opts: Dict[str, Any] = {"folder": f"{base}/{folder}" if folder else base,
                                "resource_type": resource_type or "image"}
        if prefer_webp:
            opts["format"] = "webp"
        # D3-6 ⓪ — 벤치 산출물은 **주소만 보고** 어느 열인지 알아야 채점이 된다.
        #   public_id에 실행·장·파이프라인을 싣고, 같은 값을 context에도 둔다(콘솔 검색용).
        if public_id:
            opts["public_id"] = public_id
        if context:
            opts["context"] = {str(k): str(v) for k, v in context.items()}
        if eager:
            opts["eager"] = eager
        result = cloudinary.uploader.upload(io.BytesIO(image_bytes), **opts) or {}
    except Exception as exc:
        # SDK 예외 문장을 **그대로**(좌표·긴 토큰만 지운다). `Invalid api_key` 같은 말이
        #   여기 있어야 다음 수리가 추측 없이 시작된다.
        out["error"] = scrub_infra(f"{type(exc).__name__}: {exc}")
        logger.warning("CDN 업로드 실패: %s", out["error"])
        return out

    out["keys"] = sorted(str(k) for k in (result.keys() if hasattr(result, "keys") else []))
    out["eager"] = list(result.get("eager") or []) if hasattr(result, "get") else []
    url = result.get("secure_url") or result.get("url")
    if not url:
        # **다음엔 키 이름이 답이다.** 무엇이 왔는지를 그대로 싣는다.
        out["error"] = ("업로드 응답에 주소가 없습니다 — 응답 키 목록: "
                        + (", ".join(out["keys"]) if out["keys"] else "(비어 있음)"))
        return out
    out.update({"ok": True, "secure_url": str(url),
                "public_id": str(result.get("public_id") or ""),
                "bytes": int(result.get("bytes") or len(image_bytes))})
    return out


def _upload_to_cdn(image_bytes: bytes, *, prefer_webp: bool = False,
                   label: Optional[Dict[str, str]] = None) -> Optional[str]:
    """처리된 이미지 바이트를 Cloudinary에 올리고 보안 URL을 반환(없으면 None).

    **얇은 껍데기다** — 진짜 일은 `upload_bytes`가 한다(두 벌 금지). 사유가 필요한 호출부는
    `upload_bytes`를 직접 부른다. 여기는 사유를 담을 칸이 없는 옛 계약이라 그대로 둔다.
    """
    res = upload_bytes(image_bytes, prefer_webp=prefer_webp, label=label)
    return res["secure_url"] if res["ok"] else None


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------

def process_image(
    image_url: str,
    channel: str = "default",
    unify_background: bool = False,
    convert_webp: bool = True,
    label: Optional[Dict[str, str]] = None,
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

    # F43 — 「껐다」·「못 쟀다」·「재고 없었다」가 **서로 다른 값**으로 나간다.
    watermark_detected = False
    watermark_removed = False
    watermark_checked = False
    watermark_reason = ""
    if not _INPAINT_ENABLED:
        watermark_reason = "워터마크 제거가 꺼져 있습니다 (IMAGE_INPAINT_ENABLED)"
    else:
        watermark_detected, watermark_reason = _detect_watermark(image_bytes)
        watermark_checked = not watermark_reason
        if watermark_detected:
            image_bytes, watermark_removed, why = _inpaint_watermark(image_bytes)
            if why:
                watermark_reason = why

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

    # 처리본을 CDN(Cloudinary)에 업로드해 새 URL 발급. 미설정/실패 시 원본 URL 유지(정직).
    cdn_url = _upload_to_cdn(image_bytes, prefer_webp=webp_converted, label=label)
    processed_url = cdn_url or image_url
    cdn_uploaded = bool(cdn_url)

    return ImageProcessResult(
        original_url=image_url,
        processed_url=processed_url,
        processed_bytes=image_bytes,
        width=width,
        height=height,
        format=fmt,
        watermark_detected=watermark_detected,
        watermark_removed=watermark_removed,
        watermark_checked=watermark_checked,
        watermark_reason=watermark_reason,
        background_unified=False,
        webp_converted=webp_converted,
        cdn_uploaded=cdn_uploaded,
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
    # F43 — **분모는 잰 것만.** 「0건 검출」은 0/0일 때 아무 뜻도 없다.
    wm_checked = sum(1 for r in results if r.watermark_checked)
    webp = sum(1 for r in results if r.webp_converted)
    cdn_uploaded = sum(1 for r in results if r.cdn_uploaded)
    return {
        "total": total,
        "success": success,
        "success_pct": round(success / total * 100, 0) if total > 0 else 0,
        "watermark_detected": wm_detected,
        "watermark_removed": wm_removed,
        "watermark_checked": wm_checked,
        "webp_converted": webp,
        "cdn_uploaded": cdn_uploaded,
        "pipeline_enabled": _PIPELINE_ENABLED,
        "inpaint_enabled": _INPAINT_ENABLED,
        "cdn_configured": _cloudinary_configured(),
    }
