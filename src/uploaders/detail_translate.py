"""Y11-P(오너 2026-10-15 19:01 VRSUK) — 마켓에 나갈 상세 설명에 **남은 한자 줄**을 등록 직전에 텐센트 텍스트 번역으로 옮긴다.

실측: VRSUK(타오바오) 상세 원문 = 페이지 글자 통째(탭 라벨·구매평·문답·규격표). 한국어 번역본(`description_ko`)이 비어
쿠팡 사전검증이 「원문(외국어)이 남은 칸: 상세 「用户评价 参数信息 图文详情 看了又看 用户评价」」로 멈췄다.
탭 라벨·남의 글 블록은 `detail_ui_junk.strip_page_ui`가 빼고, 그래도 남은 한자 줄(규격표 등)은 여기서 옮긴다.

규칙
  - 옮기는 줄 = 한자·가나가 있고 한글이 없는 줄(`market_description`이 버리는 바로 그 줄). 한글이 섞인 줄은 건드리지 않는다.
  - 붙어 있는 줄끼리 1,400자 안으로 묶어 한 번에 보낸다(텐센트 SourceText 상한 1,500자 — `translate_text`가 자른다).
    돌아온 줄 수가 같으면 줄마다 바꾸고, 다르면 그 묶음을 돌아온 글 그대로 넣는다(줄을 지어내지 않는다).
  - 번역이 실패한 묶음은 원문 그대로 둔다 → 뒤의 `market_description`이 한자 줄을 뺀다(예전 동작 — 마켓에 중국어 0).
  - 같은 글은 프로세스 안에서 한 번만 묻는다(사전검증 마켓 병렬·등록에서 같은 본문을 여러 번 지난다).
  - 수집 원본은 덮어쓰지 않는다 — 나가는 몸통에만 쓴다.
"""
from __future__ import annotations

import hashlib
import logging
import re
import threading
from collections import OrderedDict
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

CHUNK_MAX = 1400
_HANGUL = re.compile(r"[가-힣]")
_CACHE: "OrderedDict[str, dict]" = OrderedDict()
_CACHE_MAX = 256
_LOCK = threading.Lock()
_KEY_LOCKS: Dict[str, threading.Lock] = {}


def _foreign_line(line: str) -> bool:
    from src.collectors.ko_polish import has_foreign
    s = str(line or "").strip()
    return bool(s) and has_foreign(s) and not _HANGUL.search(s)


def _default_translate(text: str) -> dict:
    from src.services.image_translate_tencent import translate_text
    return translate_text(text, source="zh", target="ko", timeout_sec=8)


RECENT_KEY = "detail_translate:recent"


def _record_call(chars: int, lines: int, r: dict, ms: int) -> None:
    """Y11P-2(오너 2026-10-15) — 텐센트 TextTranslate 실호출 기록 40줄(운영 DB `detail_translate:recent`) — 로그를 못 볼 때
    호출 수·응답 코드·실패 사유 보고용. 글 내용·키는 안 남긴다. 실패해도 일은 계속."""
    try:
        from datetime import datetime, timezone
        from src.db import image_translate_queue_pg as st
        cur = st.state_get(RECENT_KEY) or {}
        row = {"at": datetime.now(timezone.utc).isoformat(), "chars": chars, "lines": lines, "ok": bool(r.get("ok")),
               "why": str(r.get("why") or "")[:80], "ms": ms}
        st.state_set(RECENT_KEY, {"rows": list(cur.get("rows") or [])[-39:] + [row],
                                  "total": int(cur.get("total") or 0) + 1,
                                  "failed": int(cur.get("failed") or 0) + (0 if row["ok"] else 1)})
    except Exception as exc:                                      # noqa: BLE001
        logger.debug("[상세 번역] 기록 실패: %s", exc)


def _cached_call(chunk: str, fn: Callable[[str], dict]) -> dict:
    key = hashlib.sha1(chunk.encode("utf-8")).hexdigest()
    with _LOCK:
        if key in _CACHE:
            _CACHE.move_to_end(key)
            return _CACHE[key]
        kl = _KEY_LOCKS.setdefault(key, threading.Lock())
    with kl:                                   # 같은 묶음을 동시에 묻는 스레드는 한 번만 부른다
        with _LOCK:
            if key in _CACHE:
                return _CACHE[key]
        import time as _t
        t0 = _t.monotonic()
        try:
            r = fn(chunk) or {}
        except Exception as exc:               # noqa: BLE001 — 번역 실패는 원문 유지(뒤에서 한자 줄을 뺀다)
            r = {"ok": False, "text": "", "why": type(exc).__name__}
        r = {"ok": bool(r.get("ok") and str(r.get("text") or "").strip()), "text": str(r.get("text") or ""),
             "why": str(r.get("why") or "")}
        _record_call(len(chunk), chunk.count("\n") + 1, r, int((_t.monotonic() - t0) * 1000))
        if r["ok"]:                            # 실패는 굳히지 않는다 — 다음 등록에서 다시 묻는다
            with _LOCK:
                _CACHE[key] = r
                while len(_CACHE) > _CACHE_MAX:
                    _CACHE.popitem(last=False)
        with _LOCK:
            _KEY_LOCKS.pop(key, None)
        return r


def _chunks(lines: List[str]) -> List[List[int]]:
    """옮길 줄 번호를 붙어 있는 덩어리(1,400자 안)로."""
    out: List[List[int]] = []
    cur: List[int] = []
    size = 0
    prev = -2
    for i, ln in enumerate(lines):
        if not _foreign_line(ln):
            continue
        n = len(ln.strip()) + 1
        if cur and (i != prev + 1 or size + n > CHUNK_MAX):
            out.append(cur)
            cur, size = [], 0
        cur.append(i)
        size += n
        prev = i
    if cur:
        out.append(cur)
    return out


def translate_leftover(text: str, translate_fn: Optional[Callable[[str], dict]] = None) -> Dict:
    """`{text, translated, failed, why}` — translated/failed = 옮긴/못 옮긴 **줄(칸) 수**."""
    lines = str(text or "").replace("\r", "").split("\n")
    groups = _chunks(lines)
    res = {"text": str(text or ""), "translated": 0, "failed": 0, "why": ""}
    if not groups:
        return res
    if translate_fn is None:
        from src.services.image_translate_tencent import is_configured
        if not is_configured():                # 키 없음 — 묻지 않는다(뒤에서 한자 줄을 뺀다: 예전 동작 그대로)
            res["why"] = "텐센트 키 없음"
            return res
    fn = translate_fn or _default_translate
    repl: Dict[int, List[str]] = {}
    for g in groups:
        chunk = "\n".join(lines[i].strip() for i in g)
        r = _cached_call(chunk, fn)
        if not r["ok"]:
            res["failed"] += len(g)
            res["why"] = res["why"] or r["why"] or "번역 실패"
            continue
        got = [x.strip() for x in r["text"].split("\n")]
        if len(got) == len(g):
            for i, t in zip(g, got):
                repl[i] = [t]
        else:
            repl[g[0]] = [r["text"].strip()]
            for i in g[1:]:
                repl[i] = []
        res["translated"] += len(g)
    out: List[str] = []
    for i, ln in enumerate(lines):
        out.extend(repl[i] if i in repl else [ln])
    res["text"] = "\n".join(out)
    if res["failed"]:
        logger.info("[상세 번역] 남은 한자 %s칸 번역 · %s칸 실패(%s) — 실패 줄은 마켓 전송에서 뺀다",
                    res["translated"], res["failed"], res["why"])
    return res


def outbound(text: str, translate_fn: Optional[Callable[[str], dict]] = None) -> Dict:
    """나갈 상세 = 탭 라벨·남의 글 블록 빼기 → 남은 한자 줄 번역. `{text, page_ui_removed, translated, failed, why}`."""
    from src.uploaders.detail_ui_junk import strip_page_ui
    st = strip_page_ui(text)
    tr = translate_leftover(st["text"], translate_fn)
    return {"text": tr["text"], "page_ui_removed": st["removed"], "translated": tr["translated"],
            "failed": tr["failed"], "why": tr["why"]}


def note(pd: Dict) -> str:
    """사전검증 카드 한 줄 — 「원문 n칸 자동 번역」(못 옮긴 칸이 있으면 같이)."""
    pd = pd or {}
    n, f = int(pd.get("detail_auto_translated") or 0), int(pd.get("detail_translate_failed") or 0)
    if not n and not f:
        return ""
    line = f"원문 {n}칸 자동 번역 — 상세 설명(텐센트 번역)" if n else ""
    if f:
        line = (line + " · " if line else "") + f"원문 {f}칸은 번역하지 못해 뺐어요({pd.get('detail_translate_why') or '번역 실패'})"
    return line
