"""Y7(오너 2026-10-04) — 「쿠팡 노출」 대표 사진 자동 판정. 쿠팡 검색 카드에 실제로 뜰 장(= 등록이 보낼 첫 장)을 잰다.

판정 줄(전부 **재서** 낸다 — 못 재면 「판정 못 함」, 통과로 치지 않고 보류도 하지 않는다):
- 정사각인가 — 아니면 쿠팡 검색 카드는 **가운데를 잘라** 보여 준다(미리보기도 그렇게 자른다).
- 긴 변 < 500px — 「반려 예상 — 500px 미만」(사전검증 보류).
- 글자·워터마크 — 서버 로컬 OCR(RapidOCR, 무료)이 두 글자 이상 읽으면 「텍스트 있음 — 반려 가능」(사전검증 보류).
- 흰 배경 비율 — 가장자리 띠(사방 6%)에서 흰색(RGB 모두 240 이상)인 화소의 비율. 보류하지 않고 숫자만 보인다.

`COUPANG_IMAGE_CHECK=0`이면 끈다(사전검증 보류도 안 건다 — 테스트 기본값).
"""
from __future__ import annotations

import io
import logging
import os
import re
import threading
from collections import OrderedDict
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

MIN_LONG_SIDE = 500
SQUARE_TOL = 0.02            # 가로세로 차가 긴 변의 2% 이내면 정사각
WHITE_MIN = 240
BORDER_FRAC = 0.06
_CACHE: "OrderedDict[str, dict]" = OrderedDict()
_LOCK = threading.Lock()
_CACHE_MAX = 256
_INTERNAL = re.compile(r"^/seller/collect/image-ko/([A-Za-z0-9_-]+)/(\d+)(?:\?kind=(detail|gallery))?")


def enabled() -> bool:
    return str(os.getenv("COUPANG_IMAGE_CHECK", "1")).strip() != "0"


def _read_text(raw: bytes):
    from src.services import image_text_precheck as P
    return P.all_text(raw)


def check_bytes(raw: bytes) -> Dict[str, Any]:
    """`{state, w, h, square, long_side, small, white_pct, text, seen, flags[]}` — state: ok|unknown."""
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(raw))
        im.load()
    except Exception as exc:                                  # noqa: BLE001 — 깨진 바이트·포맷 미지원
        return {"state": "unknown", "why": f"이미지를 열지 못했어요({type(exc).__name__})", "flags": []}
    w, h = im.size
    long_side = max(w, h)
    square = abs(w - h) <= SQUARE_TOL * long_side
    rgb = im.convert("RGB")
    small = rgb.resize((max(1, w // 4), max(1, h // 4))) if long_side > 400 else rgb
    sw, sh = small.size
    sbw, sbh = max(1, int(sw * BORDER_FRAC)), max(1, int(sh * BORDER_FRAC))
    px = small.load()
    total = white = 0
    for y in range(sh):
        for x in range(sw):
            if sbw <= x < sw - sbw and sbh <= y < sh - sbh:
                continue
            r, g, b = px[x, y]
            total += 1
            white += r >= WHITE_MIN and g >= WHITE_MIN and b >= WHITE_MIN
    white_pct = round(white / total * 100) if total else 0
    text, seen = _read_text(raw)
    flags = []
    if long_side < MIN_LONG_SIDE:
        flags.append({"key": "small", "hold": True, "line": f"반려 예상 — 500px 미만(긴 변 {long_side}px)"})
    if text:
        flags.append({"key": "text", "hold": True, "line": f"텍스트 있음 — 반려 가능(읽은 글자 「{seen}」)"})
    if not square:
        flags.append({"key": "not_square", "hold": False,
                      "line": f"정사각 아님({w}×{h}) — 쿠팡 검색 카드엔 가운데를 잘라 보여요"})
    return {"state": "ok", "w": w, "h": h, "square": square, "long_side": long_side,
            "small": long_side < MIN_LONG_SIDE, "white_pct": white_pct,
            "text": text, "seen": seen, "flags": flags}


def _bytes_for(url: str) -> tuple:
    """`(bytes, 사유)` — 우리 번역본 주소는 저장소에서, 그 밖은 내려받는다."""
    m = _INTERNAL.match(str(url or ""))
    if m:
        from src.services.image_translate_store import read_translated
        raw = read_translated(m.group(1), int(m.group(2)), kind=m.group(3) or "gallery")
        return (raw, "") if raw else (b"", "번역본 바이트가 없어요")
    if not str(url or "").startswith(("http://", "https://")):
        return b"", "읽을 수 없는 주소예요"
    from src.services.image_translate_tencent import fetch_image
    return fetch_image(url)


def check_url(url: str) -> Dict[str, Any]:
    """주소 하나 판정(프로세스 캐시 256장). 꺼져 있거나 못 읽으면 state=unknown + why."""
    if not enabled():
        return {"state": "unknown", "why": "판정 꺼짐(COUPANG_IMAGE_CHECK=0)", "flags": []}
    key = str(url or "")
    with _LOCK:
        if key in _CACHE:
            _CACHE.move_to_end(key)
            return _CACHE[key]
    raw, why = _bytes_for(key)
    res = check_bytes(raw) if raw else {"state": "unknown", "why": why or "이미지를 읽지 못했어요", "flags": []}
    if res.get("state") == "ok":
        with _LOCK:
            _CACHE[key] = res
            while len(_CACHE) > _CACHE_MAX:
                _CACHE.popitem(last=False)
    return res


def reset_cache() -> None:
    with _LOCK:
        _CACHE.clear()


def hold(pd: dict, market: str) -> Optional[Dict[str, str]]:
    """쿠팡 사전검증 보류 줄(없으면 None) — 대표 사진(등록이 보낼 첫 장)이 500px 미만이거나 글자가 박혔을 때.

    「그래도 등록」(`rep_image_override.url`이 지금 대표 장과 같을 때)이면 보류하지 않는다 — 대표 장을 바꾸면 다시 잰다.
    """
    if not str(market or "").startswith("coupang") or not enabled():
        return None
    imgs = [u for u in (pd.get("images_effective") or pd.get("images") or []) if isinstance(u, str) and u.strip()]
    if not imgs:
        return None
    rep = imgs[0]
    ov = pd.get("rep_image_override") or {}
    if isinstance(ov, dict) and ov.get("url") == rep:
        return None
    try:
        res = check_url(rep)
    except Exception as exc:                                  # noqa: BLE001 — 판정 실패는 보류 사유가 아니다
        logger.warning("[쿠팡 대표 사진] 판정 실패(보류 안 함): %s", exc)
        return None
    bad = [f for f in res.get("flags") or [] if f.get("hold")]
    if not bad:
        return None
    return {"short": "대표 사진 " + "·".join("500px 미만" if f["key"] == "small" else "텍스트 있음" for f in bad),
            "fix": "rep_image",
            "line": "쿠팡 대표 사진: " + " · ".join(f["line"] for f in bad)
                    + " — 「쿠팡 노출」 탭에서 다른 장을 대표로 고르거나 「그래도 등록」"}
