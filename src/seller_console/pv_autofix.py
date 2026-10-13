"""AF1(오너 2026-10-13 「사전검증에 반려사유 자동수정 붙여라」) — 사전검증이 찾은 **글자로 고칠 수 있는 반려 사유**를
Claude로 고치고 다시 잰다.

고치는 것(사전검증이 이미 찾는 사유 그대로 — 새 판정 발명 0):
  ① 표시광고 위험 문구(`ad_claim_risk` — 할인율·기간·쿠폰·「1위」「최저가」) — 상품명·쿠팡 상품명·옵션 값
  ② 원문(한자·가나)이 남은 칸(「번역」 보류 · 쿠팡 「원문(외국어)이 남은 칸」) — 남은 조각만 한국어로
  ③ 옵션 값 미해석(「번역」 보류) — 원문 값 → 한국어(해석 사슬 0번 `option_value_overrides`, 셀러가 넣은 값이 이긴다)
  ④ Shopify 영문 제목 없음(`title_not_english`) — 영문 제목
고치지 않는 것: 상표 위험·IP(오너 판단) · 차단(유통기한·콘센트) · 가격·사진·카테고리·배송 — 글자로 풀 문제가 아니다.

규칙:
- Claude 답은 **같은 판정으로 다시 잰다**(`ban_hits`·`has_foreign`·쿠팡 상품명 규칙·길이). 걸리면 그 조각은 버리고 이유를 남긴다.
- 고친 내용은 수집 기록 `extra.auto_fix`에만 둔다(원래 칸은 그대로) — 등록·사전검증이 **같은 자리**(`apply`)에서 얹는다.
  그 칸이 아직 **고칠 때 그 값**일 때만 바꾼다 — 셀러가 그 뒤 손으로 고쳤으면 셀러 글이 이긴다.
- 되돌리기 = `auto_fix.undone` + `auto_fix_off`(그 상품은 다시 켤 때까지 자동 수정 안 함).
- 같은 재료로 실패한 시도는 6시간 동안 다시 부르지 않는다(돈 · 같은 실패 반복 방지).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

VERSION = 1
RETRY_AFTER = timedelta(hours=6)
MAX_SEGMENTS = 30
MAX_VALUES = 40
OPTION_VALUE_MAX = 25            # 쿠팡 옵션 값 30자 — 여유를 둔다
TITLE_MAX = 100
TITLE_EN_MAX = 200

_FOREIGN_CH = r"぀-ヿ㐀-鿿豈-﫿"
#: 한자·가나로 시작해 그 뒤에 붙은 숫자·영문·한자·기호까지 — 「XL码」·「黑色款(加大)」 같은 덩어리 한 개
_SEG_RE = re.compile(rf"[{_FOREIGN_CH}][{_FOREIGN_CH}0-9A-Za-z·\-/+()（）\[\]【】 ]*")
_CJK_RE = re.compile(r"[぀-ヿ㐀-鿿豈-﫿가-힣]")


def enabled() -> bool:
    return os.getenv("PREVALIDATE_AUTOFIX", "1").strip() != "0"


def _kp():
    from src.collectors import ko_polish
    return ko_polish


def _s(v) -> str:
    return str(v or "").strip()


def _eq(a, b) -> bool:
    return _s(a) == _s(b) and _s(b) != ""


# ── 1. 사유 모으기 ──────────────────────────────────────────────────────────────────────

def _is_fixable_row(r) -> List[str]:
    """이 마켓 줄이 글자로 풀 수 있는 사유를 가졌나 → 사유 종류 목록."""
    code = str(getattr(r, "error_code", "") or "")
    fixes = list(getattr(r, "fixes", None) or [])
    details = " ".join(str(x) for x in (getattr(r, "details", None) or []))
    kinds = []
    if code == "ad_claim_risk":
        kinds.append("ad")
    if getattr(r, "hold", False) and "translate" in fixes:
        kinds.append("translate")
    if code == "coupang_hold" and ("원문(외국어)" in details or "미해석" in details):
        kinds.append("translate")
    if code == "title_not_english":
        kinds.append("en")
    return kinds


def _segments(text: str) -> List[str]:
    out = []
    for m in _SEG_RE.finditer(str(text or "")):
        seg = m.group(0).strip(" -/·+")
        if seg and _kp().has_foreign(seg) and seg not in out:
            out.append(seg[:80])
    return out


def _option_values_ko(pd: dict) -> List[str]:
    out = []
    for o in pd.get("options") or []:
        if isinstance(o, dict):
            for v in o.get("values_ko") or []:
                if isinstance(v, str) and v.strip() and v not in out:
                    out.append(v)
    return out


def collect(pd: Dict[str, Any], results) -> Optional[Dict[str, Any]]:
    """사전검증 결과 → 고칠 재료. 없으면 None."""
    kinds_by_market: Dict[str, List[str]] = {}
    for r in results or []:
        k = _is_fixable_row(r)
        if k:
            kinds_by_market[str(getattr(r, "market", "") or "")] = k
    if not kinds_by_market:
        return None
    kinds = {k for ks in kinds_by_market.values() for k in ks}
    kp = _kp()
    req: Dict[str, Any] = {"markets": sorted(kinds_by_market), "title_ko": "", "coupang_name": "", "title_en": "",
                           "values": [], "segments": [], "unresolved": [], "need_en": False, "lines": []}
    if "ad" in kinds:
        t = _s(pd.get("title_ko") or pd.get("title"))
        if t and kp.ban_hits(t):
            req["title_ko"] = t
        cn = _s(pd.get("coupang_name"))
        if cn and kp.ban_hits(cn):
            req["coupang_name"] = cn
        req["values"] = [v for v in _option_values_ko(pd) if kp.ban_hits(v)][:MAX_VALUES]
        frags = sorted({f for t in [req["title_ko"], req["coupang_name"]] + req["values"] for f in kp.ban_hits(t)})
        if frags:
            req["lines"].append("표시광고 위험 문구 " + " · ".join(f"「{f}」" for f in frags[:6]))
    if "translate" in kinds:
        try:
            from .upload_dispatcher import apply_outbound_text, outbound_foreign_fields, unresolved_option_values
            texts = [v for _f, v in outbound_foreign_fields(apply_outbound_text(pd))]
            req["unresolved"] = [v for v in unresolved_option_values(pd)][:MAX_VALUES]
        except Exception as exc:                                     # noqa: BLE001 — 재료 못 모으면 이 종류만 건너뛴다
            logger.warning("[자동 수정] 원문 칸 판정 실패: %s", exc)
            texts = []
        texts += [_s(pd.get("coupang_name")), _s(pd.get("brand"))] + _option_values_ko(pd)
        for o in pd.get("options") or []:
            if isinstance(o, dict):
                texts.append(_s(o.get("name_ko")))
        texts += [str(t) for t in (pd.get("keywords") or []) if isinstance(t, str)]
        for sp in pd.get("detail_specs") or []:
            if isinstance(sp, (list, tuple)):
                texts += [str(x) for x in sp]
        segs: List[str] = []
        for t in texts:
            for s in _segments(t):
                if s not in segs and s not in req["unresolved"]:
                    segs.append(s)
        req["segments"] = segs[:MAX_SEGMENTS]
        if req["segments"]:
            req["lines"].append(f"원문(한자·가나) 조각 {len(req['segments'])}개")
        if req["unresolved"]:
            req["lines"].append(f"옵션 값 미해석 {len(req['unresolved'])}개")
    if "en" in kinds:
        req["need_en"] = True
        req["title_en"] = _s(pd.get("title_en"))
        req["lines"].append("Shopify 영문 제목 없음")
    if not (req["title_ko"] or req["coupang_name"] or req["values"] or req["segments"] or req["unresolved"] or req["need_en"]):
        return None
    req["context"] = {"title_ko": _s(pd.get("title_ko") or pd.get("title"))[:120], "title_src": _s(pd.get("title_src"))[:160],
                      "brand": _s(pd.get("brand"))[:60], "category": _s(pd.get("category_code") or pd.get("category"))[:20]}
    req["hash"] = hashlib.sha1(json.dumps({k: req[k] for k in ("title_ko", "coupang_name", "values", "segments",
                                                               "unresolved", "need_en", "title_en")},
                                          ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    return req


# ── 2. Claude에게 묻기 ─────────────────────────────────────────────────────────────────

SYSTEM = (
    "너는 한국 오픈마켓(쿠팡·스마트스토어·11번가) 상품 등록 편집자다. 사전검증이 찾은 반려 사유만 고친다.\n"
    "규칙:\n"
    "1. 표시광고 위험 문구(할인율·기간 한정·쿠폰 금액·1위·최저가·최고·특가·무료배송·정품보장 같은 판촉어)는 지운다. "
    "새 판촉어·과장·효능을 넣지 않는다.\n"
    "2. 브랜드·모델명·숫자 규격(용량·크기·개수)은 그대로 둔다. 없는 사양을 지어내지 않는다. "
    "고칠 글에 없는 브랜드·상표 이름(가구 디자이너 상표·캐릭터·영화·게임 이름 등)은 원문 맥락에 있어도 새로 넣지 않는다.\n"
    "3. 한자·일본어는 자연스러운 한국어로 옮긴다. 결과에 한자·가나를 남기지 않는다.\n"
    "4. 옵션 값은 짧게(25자 이내) — 색상·사이즈·구성만. 예: 黑色 XL码 → 블랙 XL\n"
    "5. 상품명은 「브랜드 + 상품명 + 핵심 속성」 꼴, 문장형·쉼표 나열 금지, 100자 이내.\n"
    "6. 영문 제목(Shopify)은 자연스러운 영어 상품명, 한글·한자 없이 150자 이내.\n"
    "7. 고칠 필요가 없거나 확신이 없는 칸은 빈 문자열로 둔다(안 바꿈).\n"
    "주어진 JSON 스키마로만 답한다."
)

_PAIR = {"type": "object", "properties": {"before": {"type": "string"}, "after": {"type": "string"}},
         "required": ["before", "after"], "additionalProperties": False}
SCHEMA = {
    "type": "object",
    "properties": {
        "title_ko": {"type": "string"},
        "coupang_name": {"type": "string"},
        "title_en": {"type": "string"},
        "values": {"type": "array", "items": _PAIR},
        "translations": {"type": "array", "items": _PAIR},
    },
    "required": ["title_ko", "coupang_name", "title_en", "values", "translations"],
    "additionalProperties": False,
}


def _prompt(req: Dict[str, Any]) -> str:
    ask = {
        "상품 맥락": req.get("context") or {},
        "고칠 상품명(표시광고 문구 제거, 빈칸이면 손대지 않음)": req.get("title_ko") or "",
        "고칠 쿠팡 상품명(표시광고 문구 제거)": req.get("coupang_name") or "",
        "고칠 옵션 값(표시광고 문구 제거 → values에 before/after)": req.get("values") or [],
        "한국어로 옮길 원문 조각(→ translations에 before=원문 그대로/after=한국어)": req.get("segments") or [],
        "한국어로 옮길 옵션 원문 값(→ translations, 25자 이내)": req.get("unresolved") or [],
        "영문 제목 필요": bool(req.get("need_en")),
        "지금 영문 제목": req.get("title_en") or "",
    }
    return ("아래 재료만 고쳐라. 고칠 게 없는 칸은 빈 문자열/빈 배열.\n"
            "출력: title_ko(고친 상품명) · coupang_name(고친 쿠팡 상품명) · title_en(영문 제목, 필요할 때만) · "
            "values(옵션 값 before→after) · translations(원문 조각·옵션 원문 값 before→after).\n"
            + json.dumps(ask, ensure_ascii=False))


def _new_marks(before: str, after: str) -> List[str]:
    """답에 **새로** 들어간 상표 라벨(레플리카·IP·drop — 파이프라인이 일부러 지우는 이름). 고칠 글에 있던 것은 제외."""
    kp = _kp()
    try:
        old = set(kp.mark_hits(before))
        return [m for m in kp.mark_hits(after) if m not in old]
    except Exception:                                                # noqa: BLE001 — 규칙 못 읽으면 이 판정만 건너뛴다
        return []


def _check_name(before: str, after: str, *, coupang: bool) -> str:
    """버릴 이유(빈 문자열 = 써도 됨)."""
    kp = _kp()
    if not after or after == before:
        return "바꾼 것이 없음"
    if kp.ban_hits(after):
        return "표시광고 문구가 남음 「" + "·".join(kp.ban_hits(after)[:3]) + "」"
    if kp.has_foreign(after):
        return "한자·가나가 남음"
    if len(after) > TITLE_MAX:
        return f"{TITLE_MAX}자 초과"
    nm = _new_marks(before, after)
    if nm:
        return "상표 이름이 새로 들어감 「" + "·".join(nm[:3]) + "」"
    if coupang:
        try:
            from src.uploaders.coupang_title import check_name
            new = [w for w in check_name(after) if w not in check_name(before)]
            if new:
                return "쿠팡 상품명 규칙: " + " · ".join(new)
        except Exception:
            pass
    return ""


def _ko_ok(after: str, *, limit: int) -> str:
    kp = _kp()
    if not after:
        return "빈 답"
    if kp.has_foreign(after):
        return "한자·가나가 남음"
    if kp.ban_hits(after):
        return "표시광고 문구 「" + "·".join(kp.ban_hits(after)[:3]) + "」"
    if len(after) > limit:
        return f"{limit}자 초과"
    try:
        mk = kp.mark_hits(after)
    except Exception:                                                # noqa: BLE001
        mk = []
    if mk:                                                           # 옵션 값·옮긴 조각엔 상표 이름을 싣지 않는다(파이프라인과 같은 규칙)
        return "상표 이름 「" + "·".join(mk[:3]) + "」"
    return ""


def judge(req: Dict[str, Any], ans: Dict[str, Any]) -> tuple:
    """Claude 답 → `(changes, rejected)`. 같은 판정으로 다시 재서 걸린 조각은 버린다."""
    changes: List[Dict[str, Any]] = []
    rejected: List[str] = []
    for fld, coupang in (("title_ko", False), ("coupang_name", True)):
        before, after = _s(req.get(fld)), _s(ans.get(fld))
        if not before:
            continue
        why = _check_name(before, after, coupang=coupang)
        if why:
            rejected.append(f"{'쿠팡 상품명' if coupang else '상품명'}: {why}")
            continue
        changes.append({"kind": "field", "field": fld, "before": before, "after": after})
    if req.get("need_en"):
        after = _s(ans.get("title_en"))
        if not after:
            rejected.append("영문 제목: 빈 답")
        elif _CJK_RE.search(after):
            rejected.append("영문 제목: 한글·한자가 남음")
        elif len(after) > TITLE_EN_MAX:
            rejected.append(f"영문 제목: {TITLE_EN_MAX}자 초과")
        elif _new_marks(_s(req.get("title_en")) + " " + _s((req.get("context") or {}).get("title_ko")), after):
            rejected.append("영문 제목: 상표 이름이 새로 들어감 「" + "·".join(
                _new_marks(_s(req.get("title_en")) + " " + _s((req.get("context") or {}).get("title_ko")), after)[:3]) + "」")
        else:
            changes.append({"kind": "field", "field": "title_en", "before": _s(req.get("title_en")), "after": after})
    want_values = set(req.get("values") or [])
    for p in ans.get("values") or []:
        b, a = _s((p or {}).get("before")), _s((p or {}).get("after"))
        if b not in want_values:
            continue
        why = _ko_ok(a, limit=OPTION_VALUE_MAX) or ("" if a != b else "바꾼 것이 없음")
        if why:
            rejected.append(f"옵션 값 「{b[:20]}」: {why}")
            continue
        changes.append({"kind": "value", "before": b, "after": a})
    segs, unres = set(req.get("segments") or []), set(req.get("unresolved") or [])
    for p in ans.get("translations") or []:
        b, a = _s((p or {}).get("before")), _s((p or {}).get("after"))
        if b in unres:
            why = _ko_ok(a, limit=OPTION_VALUE_MAX)
            if why:
                rejected.append(f"옵션 원문 「{b[:20]}」: {why}")
                continue
            changes.append({"kind": "override", "src": b, "after": a})
        elif b in segs:
            why = _ko_ok(a, limit=max(40, 2 * len(b) + 30))
            if why:
                rejected.append(f"원문 「{b[:20]}」: {why}")
                continue
            changes.append({"kind": "text", "before": b, "after": a})
    return changes, rejected


def run(req: Dict[str, Any]) -> Dict[str, Any]:
    """Claude 한 번 → 시도 기록 `{status, changes, rejected, error, ai_call, input_hash, reasons, at}`.

    status: done(바꾼 것 1개 이상) · rejected(답은 왔는데 전부 규칙에 걸림) · failed(호출 실패) · unavailable(키·예산)
    """
    from src.ai import claude_client as cc
    rec = {"v": VERSION, "at": datetime.now(timezone.utc).isoformat(), "input_hash": req.get("hash") or "",
           "reasons": list(req.get("lines") or []), "markets": list(req.get("markets") or []),
           "changes": [], "rejected": [], "error": "", "ai_call": {}}
    try:
        ans, meta = cc.messages_json(SYSTEM, _prompt(req), SCHEMA, max_tokens=2500, timeout=30, note="pv_autofix")
    except cc.ClaudeUnavailable as exc:
        return {**rec, "status": "unavailable", "error": str(exc)}
    except cc.ClaudeError as exc:
        return {**rec, "status": "failed", "error": str(exc)[:300], "ai_call": {"status": exc.status, "body": exc.body[:300]}}
    except Exception as exc:                                         # noqa: BLE001
        return {**rec, "status": "failed", "error": f"{type(exc).__name__}: {str(exc)[:200]}"}
    changes, rejected = judge(req, ans)
    rec.update(changes=changes, rejected=rejected, ai_call=meta)
    rec["status"] = "done" if changes else "rejected"
    return rec


def should_skip(req: Dict[str, Any], ex: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """같은 재료로 실패한 시도가 6시간 안이면 다시 부르지 않는다 — 그 기록을 돌려준다."""
    last = ex.get("auto_fix_try") if isinstance(ex.get("auto_fix_try"), dict) else {}
    if not last or last.get("input_hash") != req.get("hash") or last.get("status") not in ("failed", "rejected", "unavailable"):
        return None
    try:
        at = datetime.fromisoformat(str(last.get("at")))
    except Exception:
        return None
    if datetime.now(timezone.utc) - at < RETRY_AFTER:
        return last
    return None


def merge(ex: Dict[str, Any], rec: Dict[str, Any]) -> Dict[str, Any]:
    """새로 고친 것을 누적 `auto_fix`에 얹는다(같은 대상은 새 것으로). 되돌린 기록은 새로 시작."""
    cur = ex.get("auto_fix") if isinstance(ex.get("auto_fix"), dict) and not (ex.get("auto_fix") or {}).get("undone") else {}
    def key(c):
        return (c.get("kind"), c.get("field") or "", c.get("before") or c.get("src") or "")
    old = {key(c): c for c in (cur.get("changes") or [])}
    for c in rec.get("changes") or []:
        old[key(c)] = c
    return {"v": VERSION, "at": rec.get("at"), "changes": list(old.values()), "undone": False,
            "model": (rec.get("ai_call") or {}).get("model") or ""}


# ── 3. 얹기(등록·사전검증 같은 자리) ───────────────────────────────────────────────────────

_TEXT_KEYS = ("title", "title_ko", "coupang_name", "description", "description_ko", "brand")


def apply(pd: Dict[str, Any], ex: Dict[str, Any]) -> Dict[str, Any]:
    """저장된 `auto_fix`를 등록 몸통에 얹는다. 그 칸이 **고칠 때 그 값**일 때만 — 셀러가 고쳤으면 그대로."""
    af = ex.get("auto_fix") if isinstance(ex, dict) else None
    if not isinstance(af, dict) or af.get("undone") or ex.get("auto_fix_off") or not af.get("changes"):
        return pd
    out = dict(pd or {})
    n = 0
    texts = [c for c in af["changes"] if c.get("kind") == "text" and c.get("before") and c.get("after")]
    for c in af["changes"]:
        k = c.get("kind")
        if k == "field":
            f, b, a = c.get("field"), c.get("before"), c.get("after")
            if f == "title_ko":
                for key in ("title_ko", "title"):
                    if _eq(out.get(key), b):
                        out[key] = a
                        n += 1
            elif f == "coupang_name" and _eq(out.get("coupang_name"), b):
                out["coupang_name"], out["coupang_name_source"] = a, "autofix"
                n += 1
            elif f == "title_en" and (not _s(out.get("title_en")) or _eq(out.get("title_en"), b)
                                      or _CJK_RE.search(_s(out.get("title_en")))):
                out["title_en"] = a
                n += 1
        elif k == "value":
            opts = []
            for o in out.get("options") or []:
                if isinstance(o, dict) and any(_eq(v, c["before"]) for v in (o.get("values_ko") or [])):
                    o = dict(o, values_ko=[c["after"] if _eq(v, c["before"]) else v for v in o.get("values_ko") or []])
                    n += 1
                opts.append(o)
            if opts:
                out["options"] = opts
            vk = out.get("option_values_ko")
            if isinstance(vk, dict):
                out["option_values_ko"] = {kk: (c["after"] if _eq(vv, c["before"]) else vv) for kk, vv in vk.items()}
        elif k == "override" and c.get("src") and c.get("after"):
            ov = dict(out.get("option_value_overrides") or {}) if isinstance(out.get("option_value_overrides"), dict) else {}
            if not _s(ov.get(c["src"])):                         # 셀러가 넣은 값이 이긴다
                ov[c["src"]] = c["after"]
                n += 1
            out["option_value_overrides"] = ov
    if texts:
        def rep(s):
            if not isinstance(s, str) or not s:
                return s
            for c in texts:
                if c["before"] in s:
                    s = s.replace(c["before"], c["after"])
            return s
        for key in _TEXT_KEYS:
            if isinstance(out.get(key), str):
                nv = rep(out[key])
                if nv != out[key]:
                    out[key] = nv
                    n += 1
        for key in ("keywords", "tags"):
            if isinstance(out.get(key), list):
                out[key] = [rep(t) for t in out[key]]
        opts = []
        for o in out.get("options") or []:
            if isinstance(o, dict):
                o = dict(o, name_ko=rep(o.get("name_ko")) if o.get("name_ko") else o.get("name_ko"),
                         values_ko=[rep(v) for v in (o.get("values_ko") or [])])
            opts.append(o)
        if opts:
            out["options"] = opts
        if isinstance(out.get("detail_specs"), list):
            out["detail_specs"] = [[rep(x) for x in sp] if isinstance(sp, (list, tuple)) else sp for sp in out["detail_specs"]]
        if isinstance(out.get("detail_auto"), dict) and isinstance(out["detail_auto"].get("text"), str):
            out["detail_auto"] = dict(out["detail_auto"], text=rep(out["detail_auto"]["text"]))
    if n:
        out["auto_fix_applied"] = n
    return out


# ── 4. 카드 한 줄 ─────────────────────────────────────────────────────────────────────

def change_lines(changes: List[Dict[str, Any]], limit: int = 6) -> List[str]:
    lab = {"title_ko": "상품명", "coupang_name": "쿠팡 상품명", "title_en": "영문 제목"}
    out = []
    for c in changes or []:
        k = c.get("kind")
        if k == "field":
            b = _s(c.get("before"))
            out.append(f"{lab.get(c.get('field'), c.get('field'))} " + (f"「{b[:40]}」 → " if b else "") + f"「{_s(c.get('after'))[:60]}」")
        elif k == "value":
            out.append(f"옵션 값 「{_s(c.get('before'))[:20]}」 → 「{_s(c.get('after'))[:25]}」")
        elif k == "override":
            out.append(f"옵션 원문 「{_s(c.get('src'))[:20]}」 → 「{_s(c.get('after'))[:25]}」")
        elif k == "text":
            out.append(f"원문 「{_s(c.get('before'))[:20]}」 → 「{_s(c.get('after'))[:30]}」")
    if len(out) > limit:
        out = out[:limit] + [f"외 {len(out) - limit}건"]
    return out


def card(rec: Dict[str, Any]) -> Dict[str, Any]:
    """잡 결과(화면이 그리는 모양) — 키 값·원문 응답은 싣지 않는다."""
    ai = rec.get("ai_call") or {}
    return {"status": rec.get("status") or "", "reasons": list(rec.get("reasons") or []),
            "lines": change_lines(rec.get("changes") or []), "n": len(rec.get("changes") or []),
            "rejected": list(rec.get("rejected") or [])[:6], "error": _s(rec.get("error"))[:240],
            "model": ai.get("model") or "", "ms": ai.get("ms") or 0, "cost_usd": ai.get("cost_usd") or 0}
