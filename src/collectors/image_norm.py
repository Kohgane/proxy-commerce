"""src/collectors/image_norm.py — 마켓 등록용 이미지 URL 정규화 + 실치수 게이트.

**반려 1호(2026-08-25, Fellow Stagg B0GS4698H2)의 근원 수리.** 쿠팡 원문:
  "대표이미지는 최대 10M, 최소 500*500, 최대 5000*5000. 기타이미지(DETAIL) 동일."

실측 근원: 사이즈 토큰 치환 규칙이 **확장(JS)에만 있고 서버에 없었다**. 서버 수집 경로로 온
`._AC_US40_`(40px) 썸네일 URL이 그대로 등록에 나가 규격 미달로 반려됐다.

정본(오너 지시 — gg_rereg/wj_rereg 계보): 아마존 이미지 URL의 사이즈 토큰을 **`_SS1600_`으로 치환**해
원본 대형본을 확보한다(제거가 아니라 치환). amazon.de도 같은 CDN 규칙. 치환 불가 형식이면 원본 유지.
"""
from __future__ import annotations

import logging
import re
from typing import NamedTuple

logger = logging.getLogger(__name__)

# 쿠팡 이미지 규격(반려 원문) — 다른 마켓도 대체로 같은 범위라 공용 기본값으로 둔다.
MIN_PX = 500
MAX_PX = 5000
MAX_BYTES = 10 * 1024 * 1024

# 아마존 CDN 사이즈 토큰: `.<something>._AC_US40_.jpg` 처럼 확장자 앞에 붙는 수식자.
#   예) 71abc._AC_US40_.jpg · 71abc._SL160_.jpg · 71abc._AC_SX466_SY466_.jpg
_AMZ_SIZE_TOKEN_RE = re.compile(r"\._[A-Za-z0-9,_-]+_\.(jpg|jpeg|png|gif|webp)$", re.I)
_AMZ_BARE_RE = re.compile(r"\.(jpg|jpeg|png|gif|webp)$", re.I)
_AMZ_HOST_RE = re.compile(r"(m\.media-amazon\.com|images-[a-z]+\.ssl-images-amazon\.com|"
                          r"images-na\.ssl-images-amazon\.com|\bamazon\.[a-z.]+)", re.I)

TARGET_TOKEN = "_SS1600_"          # 정본 대형본 토큰(오너 지시)


def normalize_image_url(url: str) -> str:
    """이미지 URL → 대형본 URL. 아마존이면 사이즈 토큰을 `_SS1600_`으로 치환.

    - 토큰이 있으면 치환(`._AC_US40_.jpg` → `._SS1600_.jpg`).
    - 토큰이 없으면 확장자 앞에 삽입(`71abc.jpg` → `71abc._SS1600_.jpg`).
    - 아마존이 아니거나 형식을 못 알아보면 **원본 그대로**(발명 0 — 남의 CDN 규칙을 추측하지 않는다).
    쿼리스트링은 여기서 제거한다(쿠팡이 거부 — 정본).
    """
    u = str(url or "").strip()
    if not u:
        return ""
    u = u.split("?")[0]                       # 정본: 쿼리스트링 제거
    if not _AMZ_HOST_RE.search(u):
        return u                              # 아마존 외 CDN은 규칙 미상 → 원본 유지
    if _AMZ_SIZE_TOKEN_RE.search(u):
        return _AMZ_SIZE_TOKEN_RE.sub(f".{TARGET_TOKEN}.\\1", u)
    if _AMZ_BARE_RE.search(u):
        return _AMZ_BARE_RE.sub(f".{TARGET_TOKEN}.\\1", u)
    return u


def normalize_image_urls(urls) -> list:
    """URL 목록 정규화 + 중복 제거(순서 보존). 빈 값은 버린다."""
    out, seen = [], set()
    for u in (urls or []):
        n = normalize_image_url(u)
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def probe_image_size(url: str, *, fetch_fn=None, timeout: float = 6.0):
    """이미지 실치수 (w, h) 측정. 실패하면 None(미상 — '작다'로 단정하지 않는다).

    fetch_fn(url)→bytes 를 주입하면 그것을 쓴다(오프라인 계약 검증). 미주입이면 requests로
    앞부분만 받아 PIL로 헤더를 읽는다. Pillow 미설치/네트워크 차단이면 None(정직).
    """
    try:
        from io import BytesIO
        from PIL import Image                      # 지연 import(CI collect-only 안전 — v39 A 선례)
    except Exception:
        return None
    data = None
    if fetch_fn:
        try:
            data = fetch_fn(url)
        except Exception as exc:
            logger.debug("이미지 fetch 실패(주입): %s", exc)
            return None
    else:
        try:
            import requests
            resp = requests.get(url, timeout=timeout, stream=True,
                                headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code != 200:
                return None
            data = resp.raw.read(262144, decode_content=True)   # 헤더만 — 전체 다운로드 안 함
        except Exception as exc:
            logger.debug("이미지 조회 실패: %s", exc)
            return None
    if not data:
        return None
    try:
        with Image.open(BytesIO(data)) as im:
            return (int(im.width), int(im.height))
    except Exception:
        return None                                # 부분 데이터로 못 읽음 = 미상


_FETCH_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
             '(KHTML, like Gecko) Chrome/124.0 Safari/537.36')
_EXT_BY_CT = {'image/jpeg': 'jpg', 'image/jpg': 'jpg', 'image/png': 'png',
              'image/webp': 'webp', 'image/gif': 'gif', 'image/bmp': 'bmp',
              'image/x-ms-bmp': 'bmp'}
FETCH_MIN_BYTES = 1024          # 정본(naver_img): 1KB 미만은 썸네일 쓰레기 → 스킵

# 형식 판별은 **매직 바이트 우선**(Content-Type은 CDN이 틀리게 줄 수 있다), 못 읽으면 CT 폴백.
_MAGIC = (
    (b"\xff\xd8\xff", "jpg"),
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"GIF87a", "gif"),
    (b"GIF89a", "gif"),
    (b"BM", "bmp"),
)
CONVERT_TARGET_EXT = "jpg"       # 미허용 형식의 변환 목적지(네이버 허용 집합의 공통분모)
_JPEG_QUALITY = 92

# ext → part MIME. `_EXT_BY_CT`의 역방향이며 **정규 MIME 1개**만 둔다(image/jpg 같은 별칭은 수신용).
_CT_BY_EXT = {'jpg': 'image/jpeg', 'png': 'image/png', 'gif': 'image/gif',
              'bmp': 'image/bmp', 'webp': 'image/webp'}


class FetchedImage(NamedTuple):
    """이미지 1장의 **3종 세트** — bytes · content_type · ext.

    카나리 5차 근원: 바이트만 변환하고 **멀티파트 메타(filename·part Content-Type)는 따로**
    계산하면 둘이 어긋난다(이중화). 이 세 값은 `_make_part`에서 **한 번에** 만들어지고,
    `filename`도 여기서 파생된다 — 조립부가 확장자를 다시 추론할 여지를 없앤다.
    """
    data: bytes
    content_type: str
    ext: str

    @property
    def filename(self) -> str:
        return f"img.{self.ext}"


def _make_part(data: bytes, ext: str):
    """(bytes, ext) → `FetchedImage`. **바이트와 메타가 어긋나면 None**(정직).

    메타를 만들기 전에 매직 바이트로 되읽어 `ext`와 대조한다 — 확장자만 갈아끼운 위장이
    이 함수를 통과할 수 없다. 미등록 ext(= MIME 미상)도 None.
    """
    ext = str(ext or "").lower().lstrip(".")
    ct = _CT_BY_EXT.get(ext)
    if not ct:
        logger.warning("이미지 확장자 %s의 MIME 미상 — 스킵", ext or "미상")
        return None
    actual = detect_image_format(data)
    if actual and actual != ext:
        logger.warning("이미지 메타 불일치(선언 %s vs 실제 %s) — 스킵", ext, actual)
        return None
    return FetchedImage(bytes(data), ct, ext)


def detect_image_format(body: bytes) -> str:
    """이미지 바이트 → 확장자(jpg/png/gif/bmp/webp). 못 알아보면 빈 문자열."""
    b = bytes(body or b"")
    if len(b) >= 12 and b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        return "webp"
    for sig, ext in _MAGIC:
        if b.startswith(sig):
            return ext
    return ""


def convert_image_bytes(body: bytes, *, target: str = CONVERT_TARGET_EXT):
    """이미지 바이트 → 목적 형식으로 **실제 바이트 변환**. 실패하면 None.

    파일명만 바꾸는 위장이 아니다 — Pillow로 디코드해 다시 인코딩한다. 알파 채널(webp/png)은
    JPEG가 못 담으므로 **흰 배경에 플래튼**한다(오너 지시). Pillow 미설치·디코드 실패는 None(정직).
    """
    try:
        from io import BytesIO
        from PIL import Image                      # 지연 import(CI collect-only 안전 — v39 A 선례)
    except Exception as exc:
        logger.warning("Pillow 미가용 — 이미지 변환 불가: %s", exc)
        return None
    tgt = (target or CONVERT_TARGET_EXT).lower()
    fmt = {"jpg": "JPEG", "jpeg": "JPEG", "png": "PNG"}.get(tgt)
    if not fmt:
        return None
    # Z10(오너 2026-10-10 22:29~22:35 KST OOM): 변환은 **원본 해상도 디코드**다 — 타오바오 상세 webp(790×15000 등)는
    #   RGBA 디코드만 수십 MB, 흰 배경 플래튼(RGB 한 벌 더)까지 두 배. 예전엔 4장이 동시에 이걸 했다(+261MB · 512MB 초과).
    #   ① 프로세스당 **한 번에 한 장**(`_CONVERT_LOCK`) ② 픽셀 상한(`IMAGE_CONVERT_MAX_PIXELS`, 기본 1,200만)을 넘으면
    #   디코드 직후 `thumbnail`로 줄여서 플래튼(두 번째 벌은 줄인 크기) — JPEG 원본이면 `draft`로 디코드부터 줄인다
    #   ③ 중간 버퍼는 바로 놓는다.
    max_px = _convert_max_pixels()
    with _CONVERT_LOCK:
        im = rgba = flat = None
        try:
            im = Image.open(BytesIO(body or b""))
            w, h = im.size
            if max_px and w * h > max_px:
                scale = (max_px / float(w * h)) ** 0.5
                tw, th = max(1, int(w * scale)), max(1, int(h * scale))
                if im.format == "JPEG":
                    im.draft("RGB", (tw, th))                   # JPEG은 디코드 단계에서 1/2·1/4·1/8로
                im.load()
                im.thumbnail((tw, th))
            else:
                im.load()
            if fmt == "JPEG":
                if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
                    rgba = im if im.mode == "RGBA" else im.convert("RGBA")
                    im = None
                    flat = Image.new("RGB", rgba.size, (255, 255, 255))
                    flat.paste(rgba, mask=rgba.getchannel("A"))       # 알파 → 흰 배경 플래튼
                    rgba.close()
                    rgba = None
                    im, flat = flat, None
                elif im.mode != "RGB":
                    rgb = im.convert("RGB")
                    im.close()
                    im = rgb
            out = BytesIO()
            im.save(out, format=fmt, quality=_JPEG_QUALITY)
            return out.getvalue()
        except Exception as exc:
            logger.warning("이미지 변환 실패(%s): %s", tgt, exc)
            return None
        finally:
            for x in (im, rgba, flat):
                try:
                    if x is not None:
                        x.close()
                except Exception:                                # noqa: BLE001
                    pass


import threading as _threading

#: Z10 — 원본 해상도 디코드는 프로세스당 한 장씩(동시 4장이 512MB를 넘겼다).
_CONVERT_LOCK = _threading.Lock()


def _convert_max_pixels() -> int:
    """변환 픽셀 상한(가로×세로) — `IMAGE_CONVERT_MAX_PIXELS`(기본 12,000,000 ≈ 790×15,000). 0이면 줄이지 않는다."""
    import os
    try:
        return int(os.getenv("IMAGE_CONVERT_MAX_PIXELS", "12000000") or 0)
    except (TypeError, ValueError):
        return 12_000_000


def _skip(on_skip, url: str, reason: str):
    """스킵 사유를 호출부에 넘긴다(조용한 스킵 금지). 항상 None을 반환 — `return _skip(...)` 용."""
    logger.info("이미지 스킵 [%s]: %s", reason, url)
    if on_skip:
        try:
            on_skip(url, reason)
        except Exception:                       # 사유 수집이 본 흐름을 깨뜨리지 않는다
            logger.debug("on_skip 콜백 실패", exc_info=True)
    return None


def fetch_image_bytes(url: str, *, min_bytes: int = FETCH_MIN_BYTES, timeout: float = 20.0,
                      allowed_formats=None, on_skip=None):
    """외부 이미지 URL → `FetchedImage`(bytes·content_type·ext). 실패/규격미달이면 None.

    **소스 CDN에서 받는 다운로드**라 마켓 아웃바운드가 아니다 — 릴레이를 타지 않는다
    (아마존은 우리 IP를 막지 않고, 릴레이 허용 호스트도 아니다). 마켓 API 호출은 반드시
    `market_relay`를 타야 하므로(v87-S7), 이 함수를 업로더 모듈 밖에 둬서 그 관문 규율을 지킨다.

    UA 헤더 필수(아마존 CDN이 기본 UA를 막는다·정본). 확장자는 매직 바이트 우선·Content-Type 폴백.
    SSL 검증은 정상 유지(정본의 CERT_NONE은 구환경 땜빵이라 승계하지 않는다).

    `allowed_formats`: 마켓이 받는 형식 집합(예: 네이버 `{"jpg","png","gif","bmp"}`). 지정하면
    그 밖의 형식(amazon.de WebP 등)을 **JPEG로 실변환**해서 돌려준다. **기본값 None = 무변환**
    — 쿠팡·WooCommerce는 webp가 무해하므로 전역 강제하지 않는다(마켓별 어댑터 이미지 축).

    `on_skip(url, reason)`: **스킵 사유 콜백**(조용한 스킵 금지 — 카나리 6차 지시 3항).
    빠진 이미지가 1KB 미만인지·다운로드 실패인지·변환 실패인지 호출부가 그대로 표기한다.
    """
    u = normalize_image_url(url)
    if not u:
        return _skip(on_skip, str(url or ''), 'URL 없음')
    try:
        import requests
        resp = requests.get(u, timeout=timeout, headers={"User-Agent": _FETCH_UA})
        resp.raise_for_status()
    except Exception as exc:
        return _skip(on_skip, u, f'다운로드 실패({type(exc).__name__}): {str(exc)[:120]}')
    body = resp.content or b""
    if len(body) < int(min_bytes):
        return _skip(on_skip, u, f'{len(body)}바이트 — {int(min_bytes)}바이트 미만')
    ct = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
    ext = detect_image_format(body) or _EXT_BY_CT.get(ct) or ""
    if not ext:
        return _skip(on_skip, u, f'형식 미상(Content-Type {ct or "없음"})')
    if allowed_formats:
        allow = {str(a).lower().lstrip(".") for a in allowed_formats}
        if "jpg" in allow:
            allow.add("jpeg")
        if ext not in allow:
            converted = convert_image_bytes(body, target=CONVERT_TARGET_EXT)
            if converted is None:
                return _skip(on_skip, u, f'미허용 형식 {ext} → {CONVERT_TARGET_EXT} 변환 실패')
            # 변환 결과로 **메타를 다시 만든다** — 바이트만 바꾸고 원본 메타를 쓰면 어긋난다(카나리 5차 근원).
            part = _make_part(converted, CONVERT_TARGET_EXT)
            if part is None:
                return _skip(on_skip, u, f'변환 결과 메타 불일치({CONVERT_TARGET_EXT})')
            logger.info("이미지 형식 변환 %s → %s (%s, %dB): %s",
                        ext, part.ext, part.content_type, len(part.data), u)
            return part
    if allowed_formats and len(body) > _shrink_bytes():
        # Z10(오너 2026-10-10 BLACKHOLES +261MB): 타오바오 원본(크기 꼬리 없는 4,000px+ JPEG·PNG)은 장당 수 MB다 —
        #   네이버 업로드 한 번에 그 바이트가 받은 목록·multipart·릴레이 base64·JSON 문자열로 7~8벌 동시에 뜬다.
        #   픽셀 상한(`IMAGE_UPLOAD_MAX_PIXELS`, 기본 800만 ≈ 2,828px 정사각)을 넘는 큰 장은 받은 자리에서 줄여 다시 담는다
        #   (JPEG은 `draft`로 디코드부터 작게 · 한 번에 한 장). 줄이지 못하면 원본 그대로(막지 않음).
        small = shrink_image_bytes(body, max_pixels=_upload_max_pixels(), max_width=_upload_max_width())
        if small is not None and len(small) < len(body):
            part = _make_part(small, CONVERT_TARGET_EXT)
            if part is not None:
                logger.info("이미지 줄임 %s %dB → %s %dB: %s", ext, len(body), part.ext, len(part.data), u)
                return part
    part = _make_part(body, ext)
    if part is None:
        return _skip(on_skip, u, f'메타 생성 실패(선언 {ext} vs 실제 {detect_image_format(body) or "미상"})')
    return part


def _shrink_bytes() -> int:
    """이 바이트를 넘는 장만 줄여 본다 — `IMAGE_SHRINK_OVER_BYTES`(기본 1.5MB)."""
    import os
    try:
        return int(os.getenv("IMAGE_SHRINK_OVER_BYTES", str(1536 * 1024)) or 0)
    except (TypeError, ValueError):
        return 1536 * 1024


def _upload_max_pixels() -> int:
    """픽셀 상한(가로×세로) — `IMAGE_UPLOAD_MAX_PIXELS`(기본 1,600만). 세로로 긴 상세 사진(790×15,000)은 건드리지 않는 값."""
    import os
    try:
        return int(os.getenv("IMAGE_UPLOAD_MAX_PIXELS", "16000000") or 0)
    except (TypeError, ValueError):
        return 16_000_000


def _upload_max_width() -> int:
    """가로 상한 — `IMAGE_UPLOAD_MAX_WIDTH`(기본 2,000px). 4,160px 원본은 2,000px로(JPEG은 디코드부터 1/2)."""
    import os
    try:
        return int(os.getenv("IMAGE_UPLOAD_MAX_WIDTH", "2000") or 0)
    except (TypeError, ValueError):
        return 2000


def shrink_image_bytes(body: bytes, *, max_pixels: int, max_width: int = 0):
    """Z10 — 가로가 `max_width`를 넘거나 픽셀이 `max_pixels`를 넘으면 비율 그대로 줄여 JPEG(흰 배경 플래튼)으로.
    둘 다 안 넘으면 None(그대로 쓴다). 프로세스당 한 장씩(`_CONVERT_LOCK`). 실패하면 None."""
    if not max_pixels and not max_width:
        return None
    try:
        from io import BytesIO
        from PIL import Image
    except Exception:
        return None
    with _CONVERT_LOCK:
        im = None
        try:
            im = Image.open(BytesIO(body or b""))
            w, h = im.size
            scale = 1.0
            if max_width and w > max_width:
                scale = min(scale, max_width / float(w))
            if max_pixels and w * h > max_pixels:
                scale = min(scale, (max_pixels / float(w * h)) ** 0.5)
            if scale >= 1.0:
                return None
            _cap = decode_max_pixels()
            if im.format != "JPEG" and _cap and w * h > _cap:
                logger.info("이미지 줄이기 건너뜀(%s %d×%d — 디코드 상한 %d 초과, 원본 사용)", im.format, w, h, _cap)
                return None                                       # Z10-B: 못 줄여 푸는 형식은 원본 화소가 통째로 뜬다
            tw, th = max(1, int(w * scale)), max(1, int(h * scale))
            if im.format == "JPEG":
                im.draft("RGB", (tw, th))
            im.load()
            im.thumbnail((tw, th))
            if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
                rgba = im if im.mode == "RGBA" else im.convert("RGBA")    # 이미 RGBA면 사본을 만들지 않는다
                flat = Image.new("RGB", rgba.size, (255, 255, 255))
                flat.paste(rgba, mask=rgba.getchannel("A"))
                if rgba is not im:
                    rgba.close()
                im.close()
                im = flat
            elif im.mode != "RGB":
                rgb = im.convert("RGB")
                im.close()
                im = rgb
            out = BytesIO()
            im.save(out, format="JPEG", quality=_JPEG_QUALITY)
            return out.getvalue()
        except Exception as exc:                                  # noqa: BLE001 — 못 줄이면 원본(막지 않음)
            logger.info("이미지 줄이기 실패(원본 사용): %s", exc)
            return None
        finally:
            try:
                if im is not None:
                    im.close()
            except Exception:                                     # noqa: BLE001
                pass


def decode_max_pixels() -> int:
    """Z10-B — 우리 프로세스가 **풀어도 되는** 화소 상한(가로×세로) — `IMAGE_DECODE_MAX_PIXELS`(기본 1,200만 ≈ 3,464px 정사각).

    JPEG은 `draft`로 디코드 단계에서 1/2·1/4·1/8로 줄여 풀 수 있다. **PNG·GIF·BMP·WebP는 못 줄여 푼다** — 원본 화소 그대로
    (RGBA면 화소당 4바이트)가 한 번에 뜨고, RGB 변환하면 한 벌 더. 02:24 사전검증(BLACKHOLES 1번 장 = 303KB **PNG**)
    3초 사이 +261MB가 이 모양이다(파일은 작아도 화소가 크다 — 단색 배경 PNG는 압축이 매우 잘 된다).
    상한을 넘는 JPEG 아닌 장은 **풀지 않는다** — 호출부가 「판정 못 함」(막지 않음)이나 원본 바이트 그대로 보내기로 간다."""
    import os
    try:
        return int(os.getenv("IMAGE_DECODE_MAX_PIXELS", "12000000") or 0)
    except (TypeError, ValueError):
        return 12_000_000


def image_head(raw: bytes) -> tuple:
    """`(형식, 가로, 세로)` — 머리말만 읽는다(화소는 안 푼다). 못 읽으면 `("", 0, 0)`."""
    try:
        from io import BytesIO
        from PIL import Image
        with Image.open(BytesIO(raw or b"")) as im:
            return str(im.format or ""), int(im.size[0]), int(im.size[1])
    except Exception:                                             # noqa: BLE001
        return "", 0, 0


def open_small(raw: bytes, max_side: int) -> tuple:
    """Z10-B — 이미지 바이트 → **긴 변 `max_side` 이하 RGB**(투명은 흰 배경) — `(이미지 | None, 형식, 가로, 세로, 사유)`.

    - 머리말로 크기부터 본다. JPEG은 `draft`로 줄여 푼다(원본 화소를 다 풀지 않음).
    - JPEG이 아니고 화소가 `decode_max_pixels()`를 넘으면 **풀지 않고** None + 사유.
    - 푸는 것은 프로세스당 한 장씩(`_CONVERT_LOCK`) — 대표 사진 판정·OCR·네이버 변환이 같은 줄에 선다.
    - 줄이기(`thumbnail`)를 RGB 변환보다 **먼저** — 원본 크기 RGB 사본을 만들지 않는다.
    """
    try:
        from io import BytesIO
        from PIL import Image
    except Exception as exc:                                       # noqa: BLE001
        return None, "", 0, 0, f"Pillow 없음({type(exc).__name__})"
    try:
        im = Image.open(BytesIO(raw or b""))
    except Exception as exc:                                       # noqa: BLE001
        return None, "", 0, 0, f"이미지를 열지 못했어요({type(exc).__name__})"
    fmt, (w, h) = str(im.format or ""), im.size
    side = max(1, int(max_side or 1))
    cap = decode_max_pixels()
    if fmt != "JPEG" and cap and w * h > cap:
        im.close()
        return None, fmt, w, h, (f"{fmt or '이미지'} {w}×{h}(화소 {w * h / 1e6:.0f}M)이 서버 디코드 상한 {cap / 1e6:.0f}M을 넘어 "
                                 f"풀지 않았어요")
    with _CONVERT_LOCK:
        try:
            if fmt == "JPEG":
                im.draft("RGB", (side, side))
            im.load()
            im.thumbnail((side, side))
            if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
                rgba = im if im.mode == "RGBA" else im.convert("RGBA")
                flat = Image.new("RGB", rgba.size, (255, 255, 255))
                flat.paste(rgba, mask=rgba.getchannel("A"))
                if rgba is not im:
                    rgba.close()
                im.close()
                im = flat
            elif im.mode != "RGB":
                rgb = im.convert("RGB")
                im.close()
                im = rgb
            return im, fmt, w, h, ""
        except Exception as exc:                                   # noqa: BLE001
            try:
                im.close()
            except Exception:                                      # noqa: BLE001
                pass
            return None, fmt, w, h, f"이미지를 풀지 못했어요({type(exc).__name__})"


def screen_images(urls, *, probe_fn=None, min_px: int = MIN_PX, max_px: int = MAX_PX) -> dict:
    """등록 전 이미지 규격 심사. 반환 {ok, images, dropped[], unknown[], reason}.

    - 정규화(대형본 치환) 후 실치수를 재본다.
    - **측정된 치수가 min_px 미만이면 제외**(그 이미지로 카나리를 태우지 않는다).
    - 측정 불가(미상)는 **제외하지 않는다** — '확인 실패'를 '규격 미달'로 단정하지 않는다(정직).
      대신 unknown에 담아 표기한다.
    - 남은 이미지가 0장이면 ok=False + 사유(대표이미지 전멸 → 호출부가 등록 차단).
    """
    urls = normalize_image_urls(urls)
    if not urls:
        return {"ok": False, "images": [], "dropped": [], "unknown": [],
                "reason": "이미지 0장 — 등록 불가"}
    probe = probe_fn if probe_fn is not None else probe_image_size
    kept, dropped, unknown = [], [], []
    for u in urls:
        size = None
        try:
            size = probe(u)
        except Exception:
            size = None
        if not size:
            unknown.append(u)
            kept.append(u)                         # 미상은 통과(확인 실패 ≠ 미달)
            continue
        w, h = size
        if w < min_px or h < min_px:
            dropped.append({"url": u, "size": f"{w}x{h}", "reason": f"{min_px}px 미만"})
            continue
        if w > max_px or h > max_px:
            dropped.append({"url": u, "size": f"{w}x{h}", "reason": f"{max_px}px 초과"})
            continue
        kept.append(u)
    if not kept:
        return {"ok": False, "images": [], "dropped": dropped, "unknown": unknown,
                "reason": (f"규격 통과 이미지 0장 — 등록 중단(대표이미지 필수). "
                           f"제외 {len(dropped)}장: "
                           + "; ".join(f"{d['size']} {d['reason']}" for d in dropped[:3]))}
    return {"ok": True, "images": kept, "dropped": dropped, "unknown": unknown, "reason": ""}
