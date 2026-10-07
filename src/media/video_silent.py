"""M5 후속(오너 2026-10-07) — 상품 동영상: **무음** mp4로 만들어 Cloudinary에 올린다. 오디오 불필요(오너 지시), 영상만.

입력: 온바운드 `item.video.url`(공급자 보관본 `provider_detail.video_url`).
출력: 최대 30초 · 세로 720 이하 · 20MB 이하 · 오디오 스트림 0개.

⚠️ 지뢰 「Render 512MB ffmpeg OOM」: libx264 **재인코딩이 메모리 피크의 원인**이었다. 그래서
   원본이 이미 h264이고 720 이하면 **재인코딩하지 않는다**(`-c:v copy -an`). 넘을 때만
   `-preset ultrafast -crf 28 -threads 1`로 줄인다. 요청 경로에서는 돌리지 않는다(보강 뒤 백그라운드).

마켓 전송(공식 근거만):
- 네이버 커머스API — 상품 동영상 업로드 필드 없음. commerce-api-naver/commerce-api 토론 #78 운영진 답변:
  「현재로서는 가까운 장래에 동영상 업로드 기능을 커머스API에서 제공할 계획이 없습니다」 → 전송 안 함.
- 쿠팡 OpenAPI — 이 환경에서 공식 문서(developers.coupangcorp.com)에 닿지 못해 필드 존재를 확인 못 함 → 전송 안 함.
  미지원 마켓에 첫 프레임을 상세 이미지로 끼워 넣지 않는다(거짓 대표 금지).
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

MAX_SEC = 30
MAX_HEIGHT = 720
MAX_BYTES = 20 * 1024 * 1024
DOWNLOAD_MAX_BYTES = int(os.getenv("VIDEO_DOWNLOAD_MAX_MB", "80") or 80) * 1024 * 1024
DOWNLOAD_TIMEOUT_SEC = 30
FFMPEG_TIMEOUT_SEC = 120

#: 마켓별 동영상 전송 — 공식 근거가 있을 때만 True. 근거 문장은 화면 표기에 그대로.
MARKET_VIDEO = {
    "coupang": (False, "쿠팡: 동영상 미지원 — 공식 문서로 상품 동영상 필드를 확인하지 못해 보내지 않아요"),
    "smartstore": (False, "스마트스토어: 동영상 미지원 — 커머스API에 상품 동영상 업로드 필드가 없어요(네이버 답변)"),
    "elevenst": (False, "11번가: 동영상 미지원 — 확인 전이라 보내지 않아요"),
    "shopify": (False, "Shopify: 동영상 미지원 — 아직 연결하지 않았어요"),
    "woocommerce": (False, "WC: 동영상 미지원 — 아직 연결하지 않았어요"),
}


def ffmpeg_exe() -> Optional[str]:
    """PATH의 ffmpeg, 없으면 `imageio-ffmpeg` 정적 바이너리(requirements — Docker 이미지에도 같이 들어간다)."""
    p = shutil.which("ffmpeg")
    if p:
        return p
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:                                            # noqa: BLE001
        return None


_DUR = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
_VID = re.compile(r"Stream #\S+.*?Video:\s*(\w+).*?(\d{2,5})x(\d{2,5})")


def probe(path: str) -> Dict[str, Any]:
    """`ffmpeg -i` 출력에서 길이·코덱·크기·오디오 유무(ffprobe 없이 — 정적 바이너리 하나로)."""
    exe = ffmpeg_exe()
    if not exe:
        return {"ok": False, "why": "ffmpeg 없음"}
    r = subprocess.run([exe, "-hide_banner", "-i", path], capture_output=True, text=True, timeout=30)
    err = r.stderr or ""
    out: Dict[str, Any] = {"ok": True, "audio": bool(re.search(r"Stream #\S+.*?Audio:", err))}
    m = _DUR.search(err)
    out["duration"] = (int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))) if m else None
    v = _VID.search(err)
    if not v:
        return {"ok": False, "why": "영상 스트림이 없어요", **out}
    out.update(codec=v.group(1), width=int(v.group(2)), height=int(v.group(3)))
    return out


def _run(args: list) -> Optional[str]:
    r = subprocess.run(args, capture_output=True, text=True, timeout=FFMPEG_TIMEOUT_SEC, close_fds=True)
    return None if r.returncode == 0 else (r.stderr or "")[-300:]


def make_silent(src: str, dst: str) -> Dict[str, Any]:
    """무음 mp4 — 가능하면 스트림 복사(재인코딩 0), 아니면 ultrafast 1스레드. `{ok, mode, bytes, ...probe}`."""
    exe = ffmpeg_exe()
    if not exe:
        return {"ok": False, "why": "ffmpeg 없음(서버에 설치 필요)"}
    p = probe(src)
    if not p.get("ok"):
        return {"ok": False, "why": p.get("why") or "영상을 읽지 못했어요"}
    base = [exe, "-hide_banner", "-loglevel", "error", "-y", "-i", src, "-t", str(MAX_SEC), "-an", "-sn", "-dn",
            "-map", "0:v:0", "-movflags", "+faststart"]
    mode = "copy"
    if p.get("codec") == "h264" and int(p.get("height") or 0) <= MAX_HEIGHT:
        err = _run(base + ["-c:v", "copy", dst])
    else:
        err = "재인코딩 필요"
    if err or not os.path.exists(dst) or os.path.getsize(dst) > MAX_BYTES:
        mode = "encode"
        err = _run(base + ["-vf", f"scale=-2:'min({MAX_HEIGHT},ih)'", "-c:v", "libx264", "-preset", "ultrafast",
                           "-crf", "28", "-threads", "1", "-pix_fmt", "yuv420p", dst])
    if not err and os.path.exists(dst) and os.path.getsize(dst) > MAX_BYTES:
        mode = "encode-small"
        err = _run(base + ["-vf", "scale=-2:'min(480,ih)'", "-c:v", "libx264", "-preset", "ultrafast",
                           "-crf", "32", "-threads", "1", "-pix_fmt", "yuv420p", dst])
    if err:
        return {"ok": False, "why": f"ffmpeg 실패: {err.strip()[-160:]}"}
    size = os.path.getsize(dst)
    if size > MAX_BYTES:
        return {"ok": False, "why": f"20MB 넘음({size // 1024 // 1024}MB) — 올리지 않아요"}
    q = probe(dst)
    return {"ok": True, "mode": mode, "bytes": size, "audio": q.get("audio"), "duration": q.get("duration"),
            "width": q.get("width"), "height": q.get("height"), "codec": q.get("codec")}


def _download(url: str, dst: str) -> Optional[str]:
    import requests
    try:
        with requests.get(url, stream=True, timeout=DOWNLOAD_TIMEOUT_SEC,
                          headers={"User-Agent": "gogabridj/1.0", "Referer": "https://item.taobao.com/"}) as r:
            if r.status_code != 200:
                return f"HTTP {r.status_code}"
            n = 0
            with open(dst, "wb") as f:
                for chunk in r.iter_content(256 * 1024):
                    n += len(chunk)
                    if n > DOWNLOAD_MAX_BYTES:
                        return f"원본이 {DOWNLOAD_MAX_BYTES // 1024 // 1024}MB를 넘어요"
                    f.write(chunk)
        return None
    except Exception as exc:                                     # noqa: BLE001
        return f"{type(exc).__name__}: {str(exc)[:120]}"


def thumb_url(video_url: str) -> str:
    """Cloudinary 동영상 주소 → 첫 프레임 jpg(카드 썸네일). Cloudinary가 아니면 빈 값."""
    if "/video/upload/" not in str(video_url or ""):
        return ""
    u = video_url.replace("/video/upload/", "/video/upload/so_0/")
    return re.sub(r"\.(mp4|mov|webm)(\?.*)?$", ".jpg", u)


def process(source_url: str, *, label: str = "") -> Dict[str, Any]:
    """원본 주소 → 무음 mp4 → Cloudinary. 결과 기록 한 덩어리(실패도 사유와 함께)."""
    now = datetime.now(timezone.utc).isoformat()
    rec: Dict[str, Any] = {"source_url": source_url, "at": now}
    if not source_url:
        return dict(rec, state="none", why="원본 동영상 없음")
    with tempfile.TemporaryDirectory(prefix="kgp-video-") as tmp:
        src, dst = os.path.join(tmp, "src.mp4"), os.path.join(tmp, "silent.mp4")
        err = _download(source_url, src)
        if err:
            return dict(rec, state="failed", why=f"원본을 받지 못했어요 — {err}")
        made = make_silent(src, dst)
        if not made.get("ok"):
            return dict(rec, state="failed", why=made.get("why") or "변환 실패")
        with open(dst, "rb") as f:
            raw = f.read()
    from src.media.image_pipeline import upload_bytes
    up = upload_bytes(raw, resource_type="video", folder="videos", public_id=label or "")
    if not up.get("ok"):
        return dict(rec, state="failed", why=f"Cloudinary 업로드 실패 — {up.get('error') or '사유 원문 없음'}",
                    **{k: made.get(k) for k in ("mode", "bytes", "duration", "width", "height")})
    url = up["secure_url"]
    return dict(rec, state="done", url=url, thumb=thumb_url(url), audio=bool(made.get("audio")),
                **{k: made.get(k) for k in ("mode", "bytes", "duration", "width", "height")})


def market_lines(markets) -> list:
    """카드 표기 — 마켓마다 동영상을 보내나(근거 문장 그대로)."""
    out = []
    for m in markets or []:
        base = str(m).split(":")[0]
        ok, line = MARKET_VIDEO.get(base, (False, f"{base}: 동영상 미지원 — 확인 전이라 보내지 않아요"))
        if line not in out:
            out.append(line)
    return out
