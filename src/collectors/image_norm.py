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
