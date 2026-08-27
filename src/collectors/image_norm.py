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
    try:
        with Image.open(BytesIO(bytes(body or b""))) as im:
            im.load()
            if fmt == "JPEG":
                if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
                    rgba = im.convert("RGBA")
                    flat = Image.new("RGB", rgba.size, (255, 255, 255))
                    flat.paste(rgba, mask=rgba.split()[-1])      # 알파 → 흰 배경 플래튼
                    im = flat
                elif im.mode != "RGB":
                    im = im.convert("RGB")
            out = BytesIO()
            im.save(out, format=fmt, quality=_JPEG_QUALITY)
            return out.getvalue()
    except Exception as exc:
        logger.warning("이미지 변환 실패(%s): %s", tgt, exc)
        return None


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
    part = _make_part(body, ext)
    if part is None:
        return _skip(on_skip, u, f'메타 생성 실패(선언 {ext} vs 실제 {detect_image_format(body) or "미상"})')
    return part


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
