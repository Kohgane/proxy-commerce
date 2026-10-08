"""Y7(오너 2026-10-04) — 「쿠팡 노출」 대표 사진 자동 판정. 쿠팡 검색 카드에 실제로 뜰 장(= 등록이 보낼 첫 장)을 잰다.

판정 줄(전부 **재서** 낸다 — 못 재면 「판정 못 함」, 통과로 치지 않고 보류도 하지 않는다):
- 정사각인가 — 아니면 쿠팡 검색 카드는 **가운데를 잘라** 보여 준다(미리보기도 그렇게 자른다).
- 긴 변 < 500px — 「반려 예상 — 500px 미만」(사전검증 보류).
- 글자·워터마크 — 텐센트 OCR API(Z7: 로컬 RapidOCR 제거)가 두 글자 이상 읽으면 「텍스트 있음 — 반려 가능」(사전검증 보류).
  OCR 호출이 실패하면 「글자 판정 못 함」(사유코드 `ocr_unavailable`) — 보류하지 않고 결과도 캐시하지 않는다(다음에 다시 잰다).
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


# Z7(2026-10-08): OCR은 텐센트 API — 로컬 모델 메모리는 사라졌지만 동시 호출 수는 그대로 1로 묶는다(공급사 QPS·비용).
# Y6-C B(오너 2026-10-07): 쿠팡 노출 미리보기 502. OCR(RapidOCR)이 원본 해상도 그대로 요청 안에서 돌았다 —
#   로컬 4코어 실측 800px 0.8초 · 1920px 4.5초, Render 작은 CPU에선 몇 배. 미리보기·사전검증·이미지 번역 사전판정이
#   한꺼번에 OCR을 돌리면 워커가 gunicorn 120초를 넘겨 죽고 프록시가 502 HTML을 준다. → OCR은 프로세스당 동시 1개,
#   미리보기는 요청 밖(백그라운드)에서 재고 화면은 3초마다 묻는다.
_OCR_SEM = threading.BoundedSemaphore(max(1, int(os.getenv("COUPANG_IMAGE_CHECK_CONCURRENCY", "1") or 1)))


def _read_text(raw: bytes):
    """OCR은 프로세스당 동시 1개 — Z8: 줄이 5초 넘게 밀리면 기다리지 않고 「판정 못 함」(ocr_busy, 막지 않음)."""
    from src.services import image_text_precheck as P
    from src.utils.locks import try_lock
    with try_lock(_OCR_SEM, code="ocr_busy", what="대표 사진 글자 판정(OCR 동시 1개)") as got:
        if not got:
            return None, ""
        return P.all_text(raw)


def check_bytes(raw: bytes) -> Dict[str, Any]:
    """`{state, w, h, square, long_side, small, white_pct, text, seen, flags[]}` — state: ok|unknown."""
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(raw))
        w, h = im.size                                        # 크기는 머리말에서 — 원본 화소를 다 풀지 않는다
        if max(w, h) > 400:
            im.draft("RGB", (max(1, w // 4), max(1, h // 4)))  # Z7: JPEG는 1/4로 풀어 흰 배경만 잰다(메모리)
        im.load()
    except Exception as exc:                                  # noqa: BLE001 — 깨진 바이트·포맷 미지원
        return {"state": "unknown", "why": f"이미지를 열지 못했어요({type(exc).__name__})", "flags": []}
    long_side = max(w, h)
    square = abs(w - h) <= SQUARE_TOL * long_side
    rgb = im.convert("RGB")
    small = rgb.resize((max(1, w // 4), max(1, h // 4))) if long_side > 400 else rgb
    del rgb, im
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
    ocr_why = ""
    if text is None:
        from src.services.image_text_precheck import last_unavailable
        ocr_why = last_unavailable() or "텐센트 OCR 실패"
        flags.append({"key": "ocr_unavailable", "code": "ocr_unavailable", "hold": False,
                      "line": f"글자 판정 못 함({ocr_why}) — 등록은 막지 않아요"})
    if not square:
        flags.append({"key": "not_square", "hold": False,
                      "line": f"정사각 아님({w}×{h}) — 쿠팡 검색 카드엔 가운데를 잘라 보여요"})
    return {"state": "ok", "w": w, "h": h, "square": square, "long_side": long_side,
            "small": long_side < MIN_LONG_SIDE, "white_pct": white_pct,
            "text": text, "seen": seen, "flags": flags, "ocr": "unavailable" if text is None else "ok", "ocr_why": ocr_why}


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
    if res.get("state") == "ok" and res.get("ocr") != "unavailable":       # Z7: 판정 못 한 결과는 굳히지 않는다
        with _LOCK:
            _CACHE[key] = res
            while len(_CACHE) > _CACHE_MAX:
                _CACHE.popitem(last=False)
    return res


def reset_cache() -> None:
    with _LOCK:
        _CACHE.clear()
        _FAIL.clear()
        _RUNNING.clear()


# ── 요청 밖에서 재기(미리보기) ─────────────────────────────────────────────────
_FAIL: Dict[str, dict] = {}          # 주소 → 못 잰 결과(사유) — 5분 동안 같은 사유를 돌려준다(폴링이 사유를 받게)
_RUNNING: Dict[str, float] = {}      # 주소 → 시작 시각
_FAIL_TTL = 300.0


def cached(url: str) -> Optional[dict]:
    """잰 결과가 있으면(성공 캐시 또는 5분 안 실패) 그것, 없으면 None."""
    import time as _t
    key = str(url or "")
    with _LOCK:
        if key in _CACHE:
            return _CACHE[key]
        f = _FAIL.get(key)
        if f and _t.time() - f.get("_at", 0) < _FAIL_TTL:
            return {k: v for k, v in f.items() if k != "_at"}
    return None


def _bg(url: str) -> None:
    import time as _t
    try:
        res = check_url(url)
    except Exception as exc:                                  # noqa: BLE001 — 백그라운드는 죽지 않는다
        res = {"state": "unknown", "why": f"판정 실패 {type(exc).__name__}: {str(exc)[:120]}", "flags": []}
    with _LOCK:
        if res.get("state") == "ok" and res.get("ocr") != "unavailable":
            _CACHE[url] = res
            _CACHE.move_to_end(url)
            while len(_CACHE) > _CACHE_MAX:
                _CACHE.popitem(last=False)
        else:
            _FAIL[url] = dict(res, _at=_t.time())
        _RUNNING.pop(url, None)


def start_check(url: str) -> dict:
    """미리보기용 — 결과가 있으면 그대로, 없으면 백그라운드로 재기 시작하고 `{state: pending}`(요청은 기다리지 않는다)."""
    import time as _t
    if not enabled():
        return {"state": "unknown", "why": "판정 꺼짐(COUPANG_IMAGE_CHECK=0)", "flags": []}
    key = str(url or "")
    if not key:
        return {"state": "unknown", "why": "이미지 0장", "flags": []}
    hit = cached(key)
    if hit is not None:
        return hit
    with _LOCK:
        started = _RUNNING.get(key)
        if not started:
            _RUNNING[key] = _t.time()
            threading.Thread(target=_bg, args=(key,), daemon=True, name="cpx-check").start()
    return {"state": "pending", "why": "대표 사진을 재는 중", "flags": [],
            "since": round(_t.time() - (started or _RUNNING.get(key) or _t.time()), 1)}


def rep_url(pd: dict, market: str) -> str:
    """판정 대상 대표 장(등록이 보낼 첫 장) — 쿠팡 아님·꺼짐·이미지 0장·「그래도 등록」이면 ''."""
    if not str(market or "").startswith("coupang") or not enabled():
        return ""
    imgs = [u for u in (pd.get("images_effective") or pd.get("images") or []) if isinstance(u, str) and u.strip()]
    if not imgs:
        return ""
    ov = pd.get("rep_image_override") or {}
    if isinstance(ov, dict) and ov.get("url") == imgs[0]:
        return ""
    return imgs[0]


def kick(pd: dict, market: str) -> None:
    """Z9 — 사전검증용: 결과가 없으면 백그라운드로 재기 시작만 한다(기다리지 않음)."""
    rep = rep_url(pd, market)
    if rep and cached(rep) is None:
        start_check(rep)


def rep_pending(pd: dict, market: str) -> bool:
    """대표 장 판정이 아직 안 끝났나(재 둔 결과도, 5분 안 실패 기록도 없음)."""
    rep = rep_url(pd, market)
    return bool(rep) and cached(rep) is None


def wait_done(urls, until_ts: float, step: float = 0.5) -> bool:
    """주어진 장들의 판정이 끝날 때까지(또는 `until_ts`까지) 기다린다 — 잡 스레드 전용(요청 스레드에서 부르지 않는다)."""
    import time as _t
    keys = [str(u) for u in urls if u]
    while _t.time() < until_ts:
        if all(cached(k) is not None for k in keys):
            return True
        _t.sleep(step)
    return all(cached(k) is not None for k in keys)


def hold(pd: dict, market: str, cached_only: bool = False) -> Optional[Dict[str, str]]:
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
        # 미리보기는 요청 안에서 재지 않는다(cached_only) — 아직 안 쟀으면 보류 줄은 결과가 오면 그린다.
        res = (cached(rep) or {}) if cached_only else check_url(rep)
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
