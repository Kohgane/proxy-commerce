"""Y11-P(오너 2026-10-15 19:01 VRSUK) — 마켓에 나갈 상세 설명에 **남은 한자 줄**을 등록 직전에 텐센트 텍스트 번역으로 옮긴다.

실측: VRSUK(타오바오) 상세 원문 = 페이지 글자 통째(탭 라벨·구매평·문답·규격표). 한국어 번역본(`description_ko`)이 비어
쿠팡 사전검증이 「원문(외국어)이 남은 칸: 상세 「用户评价 参数信息 图文详情 看了又看 用户评价」」로 멈췄다.
탭 라벨·남의 글 블록은 `detail_ui_junk.strip_page_ui`가 빼고, 그래도 남은 한자 줄(규격표 등)은 여기서 옮긴다.

규칙
  - 옮기는 줄 = 한자·가나가 있고 한글이 없는 줄(`market_description`이 버리는 바로 그 줄). 한글이 섞인 줄은 건드리지 않는다.
  - 붙어 있는 줄끼리 1,400자 안으로 묶어 한 번에 보낸다(텐센트 SourceText 상한 1,500자 — `translate_text`가 자른다).
    돌아온 줄 수가 같으면 줄마다 바꾸고, 다르면 그 묶음을 돌아온 글 그대로 넣는다(줄을 지어내지 않는다).
  - 번역이 실패한 묶음은 원문 그대로 둔다 → 뒤의 `market_description`이 한자 줄을 뺀다(예전 동작 — 마켓에 중국어 0).
  - Y11P-2(오너 결정 2026-10-15): 실패한 묶음은 **60초 뒤 1회 자동 재시도**(백그라운드 · 성공하면 캐시 → 다음 검증·등록이 씀).
    그래도 실패면 지금처럼 뺀다. 단 실패한 줄에 **규격 키**(材质·尺寸·重量·产地·型号… `detail_ui_junk.json` `spec_keys`)가 있으면
    빼지 않고 쿠팡 보류 + 「다시 번역」(`retry_now`) — 규격이 빠지면 상품 정보가 깨진다.
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

CHUNK_MAX = 2000                  # Y11-Q: 줄바꿈으로 이어 2,000자 묶음(떨어진 줄도 한 묶음 — 51줄이면 1~3회)
_HANGUL = re.compile(r"[가-힣]")
_CACHE: "OrderedDict[str, dict]" = OrderedDict()
_CACHE_MAX = 256
_LOCK = threading.Lock()
_KEY_LOCKS: Dict[str, threading.Lock] = {}
#: 실패한 묶음 `{key: {"at", "state": "pending"|"final", "why"}}` — pending = 60초 뒤 재시도 예약됨, final = 재시도도 실패.
_FAIL: Dict[str, dict] = {}
FINAL_FORGET_SEC = 600            # 재시도까지 실패한 묶음도 10분 뒤엔 다음 검증·등록에서 다시 묻는다


def retry_sec() -> float:
    import os
    try:
        return max(1.0, float(os.getenv("DETAIL_TRANSLATE_RETRY_SEC") or 60))
    except ValueError:
        return 60.0


def is_spec_line(line: str) -> bool:
    """규격 줄인가 — 키(材质·尺寸·重量·产地·型号…)가 들어 있으면(「材质: 实木」·「框架材质」 둘 다)."""
    from src.uploaders.detail_ui_junk import table
    s = str(line or "")
    return any(k in s for k in (table().get("spec_keys") or []))


def _foreign_line(line: str) -> bool:
    from src.collectors.ko_polish import has_foreign
    s = str(line or "").strip()
    return bool(s) and has_foreign(s) and not _HANGUL.search(s)


#: Y11-R(운영 실측 2026-10-16): 텐센트 intl 엔드포인트가 51칸 전부 `InvalidParameterValue — 不支持的语种：zh_to_ko`.
#:   줄 문제가 아니라 **언어쌍 미지원**이었다(이분 탐색은 호출만 늘렸다). 이 응답을 보면 10분 동안 텐센트를 건너뛰고
#:   기존 번역 체인(papago·deepl·azure·anthropic·openai — 상품 번역과 같은 것)으로 옮긴다.
PAIR_DOWN_SEC = 600
_PAIR_DOWN = {"at": 0.0, "message": ""}


def unsupported_pair(r: dict) -> bool:
    """텐센트가 언어쌍을 안 받는다는 응답인가(줄 내용과 무관 — 쪼개 봐야 같은 답)."""
    m = str((r or {}).get("message") or "") + " " + str((r or {}).get("why") or "")
    return ("不支持的语种" in m) or ("UnsupportedLanguage" in m) or ("language" in m.lower() and "support" in m.lower())


def _tencent(text: str) -> dict:
    from src.services.image_translate_tencent import translate_text
    return translate_text(text, source="zh", target="ko", timeout_sec=8, max_chars=CHUNK_MAX)


def _chain(text: str) -> dict:
    """상품 번역과 같은 체인으로 상세 줄 묶음을 옮긴다 — `{ok, text, why, provider, attempts}`(원문을 돌려주면 실패)."""
    from src.seller_console.ai.translator import AITranslator
    res = AITranslator().translate_product({"title": "", "description": text}) or {}
    prov = str(res.get("provider") or "")
    out = str(res.get("description_ko") or "")
    ok = bool(out.strip()) and not res.get("error") and prov not in ("stub", "none") and not prov.endswith("-fallback") \
        and out.strip() != str(text or "").strip() and bool(_HANGUL.search(out))
    why = "" if ok else (str(res.get("translate_error") or res.get("error") or "")[:120] or "번역 체인 결과 없음")
    return {"ok": ok, "text": out if ok else "", "why": why, "provider": prov,
            "attempts": len(res.get("attempts") or []) or 1}


def _default_translate(text: str) -> dict:
    """텐센트 → (언어쌍 미지원·실패면) 번역 체인. 결과에 `provider`·`tencent`(텐센트 응답 요약)를 남긴다."""
    import time as _t
    tc = None
    if _t.monotonic() - _PAIR_DOWN["at"] >= PAIR_DOWN_SEC or not _PAIR_DOWN["at"]:
        try:
            tc = _tencent(text) or {}
        except Exception as exc:                                  # noqa: BLE001
            tc = {"ok": False, "why": type(exc).__name__}
        if tc.get("ok") and str(tc.get("text") or "").strip():
            return dict(tc, provider="tencent")
        if unsupported_pair(tc):
            _PAIR_DOWN.update(at=_t.monotonic(), message=str(tc.get("message") or tc.get("why") or "")[:120])
            logger.warning("[상세 번역] 텐센트 언어쌍 미지원(%s) — %s초 동안 번역 체인으로", _PAIR_DOWN["message"], PAIR_DOWN_SEC)
    try:
        r = _chain(text)
    except Exception as exc:                                      # noqa: BLE001 — 체인도 실패면 텐센트 사유를 남긴다
        r = {"ok": False, "text": "", "why": f"번역 체인 {type(exc).__name__}", "provider": "chain"}
    tsum = ({"tencent": {"why": str(tc.get("why") or "")[:60], "message": str(tc.get("message") or "")[:120]}}
            if tc is not None else {"tencent": {"skipped": "언어쌍 미지원 — 건너뜀"}})
    if not r["ok"] and tc is not None and not unsupported_pair(tc):
        # 체인도 못 옮겼다 — 텐센트 사유(쓰로틀·네트워크)가 더 정확하다
        return dict(tc, ok=False, provider="tencent", **tsum)
    return dict(r, **tsum)


_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\u200b-\u200f\u2028\u2029\ufeff]")


def clean_line(line: str) -> str:
    """보내기 전 정리 — 제어문자·폭 없는 문자 빼고 앞뒤 공백. (빈 줄은 애초에 묶음에 안 들어간다.)"""
    return _CTRL.sub("", str(line or "")).strip()


def line_diag(line: str) -> dict:
    """InvalidParameterValue 부검용 — 그 줄이 왜 이상한지(빈 줄·제어문자·길이·한자 비율). 글은 앞 40자만."""
    raw = str(line or "")
    han = len(re.findall(r"[\u4e00-\u9fff]", raw))
    return {"text": raw[:40], "len": len(raw), "empty": not raw.strip(), "ctrl": bool(_CTRL.search(raw)),
            "han": han, "other": len(raw.strip()) - han}


RECENT_KEY = "detail_translate:recent"


def _record_call(chars: int, lines: int, r: dict, ms: int, extra: dict = None) -> None:
    """Y11P-2(오너 2026-10-15) — 텐센트 TextTranslate 실호출 기록 40줄(운영 DB `detail_translate:recent`) — 로그를 못 볼 때
    호출 수·응답 코드·실패 사유 보고용. 글 내용·키는 안 남긴다. 실패해도 일은 계속."""
    try:
        from datetime import datetime, timezone
        from src.db import image_translate_queue_pg as st
        cur = st.state_get(RECENT_KEY) or {}
        row = {"at": datetime.now(timezone.utc).isoformat(), "chars": chars, "lines": lines, "ok": bool(r.get("ok")),
               "why": str(r.get("why") or "")[:80], "ms": ms, "attempts": int(r.get("attempts") or 1),
               **({"message": str(r.get("message") or "")[:200]} if r.get("message") else {}), **(extra or {})}
        st.state_set(RECENT_KEY, {"rows": list(cur.get("rows") or [])[-39:] + [row],
                                  "total": int(cur.get("total") or 0) + 1,
                                  "failed": int(cur.get("failed") or 0) + (0 if row["ok"] else 1)})
    except Exception as exc:                                      # noqa: BLE001
        logger.debug("[상세 번역] 기록 실패: %s", exc)


def _key(chunk: str) -> str:
    return hashlib.sha1(chunk.encode("utf-8")).hexdigest()


def _call(chunk: str, fn: Callable[[str], dict]) -> dict:
    import time as _t
    t0 = _t.monotonic()
    try:
        r = fn(chunk) or {}
    except Exception as exc:                   # noqa: BLE001 — 번역 실패는 원문 유지
        r = {"ok": False, "text": "", "why": type(exc).__name__}
    r = {"ok": bool(r.get("ok") and str(r.get("text") or "").strip()), "text": str(r.get("text") or ""),
         "why": str(r.get("why") or ""), "message": str(r.get("message") or ""), "attempts": r.get("attempts") or 1,
         "provider": str(r.get("provider") or ""), "tencent": r.get("tencent") or None}
    extra = {k: r[k] for k in ("provider", "tencent") if r.get(k)} or None
    if "InvalidParameter" in r["why"] and not unsupported_pair(r):
        # Y11-Q: 어느 줄·왜(빈 줄·제어문자·길이) — 묶음이면 줄마다, 한 줄이면 그 줄
        extra = dict(extra or {}, lines_diag=[line_diag(x) for x in chunk.split("\n")][:8])
        logger.warning("[상세 번역] InvalidParameterValue — %s · 줄 %s", r["message"][:160], extra["lines_diag"])
    _record_call(len(chunk), chunk.count("\n") + 1, r, int((_t.monotonic() - t0) * 1000), extra)
    return r


def _remember(key: str, r: dict) -> None:
    with _LOCK:
        _CACHE[key] = r
        while len(_CACHE) > _CACHE_MAX:
            _CACHE.popitem(last=False)
        _FAIL.pop(key, None)


def _retry_later(chunk: str, fn: Callable[[str], dict]) -> None:
    """60초 뒤 1회 — 성공이면 캐시(다음 검증·등록이 쓴다), 실패면 final(그 줄은 뺀다)."""
    key = _key(chunk)
    r = _call(chunk, fn)
    if r["ok"]:
        _remember(key, r)
        logger.info("[상세 번역] 60초 뒤 재시도 성공 — %s자", len(chunk))
    else:
        import time as _t
        with _LOCK:
            _FAIL[key] = {"at": _t.monotonic(), "state": "final", "why": r["why"]}
        logger.info("[상세 번역] 60초 뒤 재시도도 실패(%s) — 그 줄은 뺀다", r["why"])


def _cached_call(chunk: str, fn: Callable[[str], dict], force: bool = False) -> dict:
    """캐시 → 실패 기록(pending이면 다시 안 묻고 기다림 · final 10분 지나면 다시) → 실호출. `retry`: pending|final|""."""
    import time as _t
    key = _key(chunk)
    with _LOCK:
        if key in _CACHE:
            _CACHE.move_to_end(key)
            return dict(_CACHE[key], retry="")
        f = _FAIL.get(key)
        if f and not force:
            if f["state"] == "pending" or _t.monotonic() - f["at"] < FINAL_FORGET_SEC:
                return {"ok": False, "text": "", "why": f["why"], "retry": f["state"]}
            _FAIL.pop(key, None)
        kl = _KEY_LOCKS.setdefault(key, threading.Lock())
    with kl:                                   # 같은 묶음을 동시에 묻는 스레드는 한 번만 부른다
        with _LOCK:
            if key in _CACHE:
                return dict(_CACHE[key], retry="")
            f = _FAIL.get(key)
            if f and not force:
                return {"ok": False, "text": "", "why": f["why"], "retry": f["state"]}
        r = _call(chunk, fn)
        retry = ""
        if r["ok"]:
            _remember(key, r)
        elif force:
            with _LOCK:
                _FAIL[key] = {"at": _t.monotonic(), "state": "final", "why": r["why"]}
            retry = "final"
        else:
            with _LOCK:
                _FAIL[key] = {"at": _t.monotonic(), "state": "pending", "why": r["why"]}
            tm = threading.Timer(retry_sec(), _retry_later, args=(chunk, fn))
            tm.daemon = True
            tm.start()
            retry = "pending"
        with _LOCK:
            _KEY_LOCKS.pop(key, None)
        return dict(r, retry=retry)


def _chunks(lines: List[str]) -> List[List[int]]:
    """옮길 줄 번호를 2,000자 묶음으로 — 떨어진 줄도 순서대로 한 묶음(돌아온 줄을 번호로 다시 끼운다)."""
    out: List[List[int]] = []
    cur: List[int] = []
    size = 0
    for i, ln in enumerate(lines):
        if not _foreign_line(ln) or not clean_line(ln):
            continue
        n = len(clean_line(ln)) + 1
        if cur and size + n > CHUNK_MAX:
            out.append(cur)
            cur, size = [], 0
        cur.append(i)
        size += n
    if cur:
        out.append(cur)
    return out


def _translate_group(lines: List[str], g: List[int], fn, force: bool, depth: int = 0) -> List[tuple]:
    """묶음 하나 → `[(줄 번호 묶음, 결과)]`. InvalidParameterValue면 반으로 나눠 다시(최대 4단 · 나쁜 줄만 실패로 남긴다)."""
    chunk = "\n".join(clean_line(lines[i]) for i in g)
    r = _cached_call(chunk, fn, force=force)
    # Y11-R: 언어쌍 미지원은 줄 탓이 아니다 — 쪼개도 같은 답이라 나누지 않는다
    bad_param = not r["ok"] and "InvalidParameter" in str(r.get("why") or "") and not unsupported_pair(r)
    # 떨어진 줄을 한 묶음으로 보냈으니 돌아온 줄 수가 다르면 번호로 못 끼운다 — 그때도 반으로 나눠 다시
    mismatch = r["ok"] and len(str(r.get("text") or "").split("\n")) != len(g)
    if (bad_param or mismatch) and len(g) > 1 and depth < 4:
        mid = len(g) // 2
        return _translate_group(lines, g[:mid], fn, force, depth + 1) + _translate_group(lines, g[mid:], fn, force, depth + 1)
    return [(g, r)]


def translate_leftover(text: str, translate_fn: Optional[Callable[[str], dict]] = None, force: bool = False) -> Dict:
    """`{text, translated, failed, why, retry_pending, spec_failed}` — translated/failed = 옮긴/못 옮긴 **줄(칸) 수**.
    retry_pending = 60초 뒤 재시도를 기다리는 줄 수 · spec_failed = 못 옮긴 규격 줄(원문, 앞 8줄). `force` = 「다시 번역」(기다림 무시)."""
    lines = str(text or "").replace("\r", "").split("\n")
    groups = _chunks(lines)
    res = {"text": str(text or ""), "translated": 0, "failed": 0, "why": "", "retry_pending": 0, "spec_failed": []}
    if not groups:
        return res
    if translate_fn is None:
        from src.services.image_translate_tencent import is_configured
        if not is_configured():                # 키 없음 — 묻지 않는다(뒤에서 한자 줄을 뺀다: 예전 동작 그대로)
            res["why"] = "텐센트 키 없음"
            return res
    fn = translate_fn or _default_translate
    repl: Dict[int, List[str]] = {}
    done = [x for g0 in groups for x in _translate_group(lines, g0, fn, force)]
    for g, r in done:
        if not r["ok"]:
            res["failed"] += len(g)
            res["why"] = res["why"] or r["why"] or "번역 실패"
            if r.get("retry") == "pending":
                res["retry_pending"] += len(g)
            res["spec_failed"] += [lines[i].strip() for i in g if is_spec_line(lines[i])]
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
    res["spec_failed"] = res["spec_failed"][:8]
    if res["failed"]:
        logger.info("[상세 번역] 남은 한자 %s칸 번역 · %s칸 실패(%s) — 실패 줄은 마켓 전송에서 뺀다",
                    res["translated"], res["failed"], res["why"])
    return res


def outbound(text: str, translate_fn: Optional[Callable[[str], dict]] = None, force: bool = False) -> Dict:
    """나갈 상세 = 탭 라벨·남의 글 블록 빼기 → 남은 한자 줄 번역.
    `{text, page_ui_removed, translated, failed, why, retry_pending, spec_failed}`."""
    from src.uploaders.detail_ui_junk import strip_page_ui
    st = strip_page_ui(text)
    tr = translate_leftover(st["text"], translate_fn, force=force)
    return {"text": tr["text"], "page_ui_removed": st["removed"], "translated": tr["translated"],
            "failed": tr["failed"], "why": tr["why"], "retry_pending": tr["retry_pending"], "spec_failed": tr["spec_failed"]}


SPEC_HOLD_CODE = "detail_spec_untranslated"


def spec_hold_line(pd: Dict) -> str:
    """쿠팡 보류 문구 — 못 옮긴 규격 줄이 있으면(빼면 상품 정보가 깨진다). 없으면 ''."""
    spec = list((pd or {}).get("detail_translate_spec_failed") or [])
    if not spec:
        return ""
    head = " · ".join(f"「{x[:14]}」" for x in spec[:3])
    wait = " — 60초 뒤 한 번 더 번역해요" if int((pd or {}).get("detail_translate_retry_pending") or 0) else ""
    return (f"보류: 상세 규격 {len(spec)}줄을 번역하지 못했어요({head}){wait}. 규격은 빼면 상품 정보가 깨져서 "
            f"그대로 보내지 않아요 — 「다시 번역」을 눌러 주세요({(pd or {}).get('detail_translate_why') or '번역 실패'})")


def note(pd: Dict) -> str:
    """사전검증 카드 한 줄 — 「원문 n칸 자동 번역」(못 옮긴 칸이 있으면 같이)."""
    pd = pd or {}
    n, f = int(pd.get("detail_auto_translated") or 0), int(pd.get("detail_translate_failed") or 0)
    if not n and not f:
        return ""
    line = f"원문 {n}칸 자동 번역 — 상세 설명(텐센트 번역)" if n else ""
    if f:
        why = pd.get('detail_translate_why') or '번역 실패'
        if int(pd.get("detail_translate_retry_pending") or 0):
            tail = f"원문 {f}칸 번역 실패({why}) — 60초 뒤 한 번 더 번역해요(그 전에 등록하면 그 칸은 빼고 보내요)"
        else:
            tail = f"원문 {f}칸은 번역하지 못해 뺐어요({why})"
        line = (line + " · " if line else "") + tail
    return line
