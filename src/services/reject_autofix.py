# -*- coding: utf-8 -*-
"""반려 사유 자동 수정(오너 2026-10-13 — 「사전검증에 반려사유 자동수정 붙여라」).

사전검증이 **사람이 글자를 고쳐야** 풀리는 사유로 멈추면(표시광고 위험 문구 · 상품명에 남은 원문 ·
그 마켓에서 받았던 반려 사유) 보류로 끝내지 않고 Claude(Anthropic API)로 그 칸만 고친 뒤 다시 잰다.

고치는 칸은 셋뿐이다 — 상품명(`title_ko`, 없으면 `title`) · 쿠팡 상품명(`coupang_name`) · 옵션 값(`options[].values_ko`).
사진·카테고리·속성·가격, 상표·라이선스 보류(T3·Y6), 차단(유통기한·콘센트)은 **손대지 않는다**(글자로 풀 일이 아니다).

규칙:
- 고친 값은 **우리 판정을 다시 통과해야** 쓴다(표시광고 문구 0 · 한자·가나 0 · 길이 · 옵션 값 개수 같음). 하나라도 어기면 안 쓴다.
- 고친 기록은 수집 기록 `reject_autofix`에 원래 값과 같이 남는다. 등록·다음 사전검증은 `apply_saved`로 같은 값을 싣는다 —
  **화면 값이 원래 값 그대로일 때만**(셀러가 그 칸을 손으로 고쳤으면 셀러가 이긴다). 되돌리면(`undone`) 싣지 않는다.
- 같은 재료(사유+칸)로는 한 번만 묻는다(`sig`). 하루 상한 `REJECT_AUTOFIX_DAILY_CAP`(기본 200).
- 키가 없거나 실패하면 지금처럼 보류 — 실패 사유를 그대로 싣는다(가짜 성공 금지).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
FORMAT_VERSION = 1
NAME_MAX = 100                     # 쿠팡 sellerProductName·네이버 상품명 모두 100자 안에서 안전
_TOOL = "apply_fixes"

#: 글자로 풀 수 없는 지난 반려(사진 규격·상표·애플 사전승인·임시저장·속성/옵션 단위) — Claude에 묻지 않는다.
_PAST_SKIP_KINDS = ("image_spec", "trademark", "apple_category", "saved_pending", "option_unit", "option_value")


def model() -> str:
    return (os.getenv("REJECT_AUTOFIX_MODEL") or "claude-sonnet-5").strip()


def enabled() -> bool:
    if str(os.getenv("REJECT_AUTOFIX_ENABLED", "1")).strip().lower() in ("0", "false", "off", "no"):
        return False
    return bool(_api_key())


def _api_key() -> str:
    from src.utils.env import env_str
    return env_str("ANTHROPIC_API_KEY") or ""


# ── 사유 모으기 ────────────────────────────────────────────────────────────────

def _title_field(pd: Dict[str, Any]) -> str:
    return "title_ko" if str(pd.get("title_ko") or "").strip() else "title"


def collect(product_data: Dict[str, Any], results: list, extra: Optional[dict] = None) -> List[Dict[str, str]]:
    """사전검증 결과에서 **글자로 고칠 수 있는** 사유만 — `[{market, kind, line}]`.

    kind: ad_claim(표시광고 위험 문구) · foreign_name(상품명에 원문) · past_rejection(그 마켓에서 받았던 반려 사유).
    """
    out: List[Dict[str, str]] = []

    def add(m, kind, line):
        row = {"market": str(m or ""), "kind": kind, "line": str(line or "").strip()[:400]}
        if row["line"] and row not in out:
            out.append(row)

    for r in results or []:
        code = str(getattr(r, "error_code", "") or "")
        details = [str(x) for x in (getattr(r, "details", None) or [])]
        if code == "ad_claim_risk":
            for line in details or [getattr(r, "message", "")]:
                add(r.market, "ad_claim", line)
        elif code == "coupang_hold":
            for line in details:
                if "원문(외국어)이 남은 칸" in line and "상품명" in line:
                    add(r.market, "foreign_name", line)
        elif getattr(r, "hold", False) and "translate" in (getattr(r, "fixes", None) or []):
            for line in details:
                if "한자·가나가 남았어요" in line and "상품명" in line:
                    add(r.market, "foreign_name", line)
    # 지난 반려 사유는 마켓 기록에 계속 남아 있다 — 이미 그 사유로 고친 글자가 실려 있으면 다시 묻지 않는다(고친 이름으로 또 고치는 고리 방지)
    applied = product_data.get("reject_autofix") if isinstance(product_data.get("reject_autofix"), dict) else {}
    handled = {(r.get("market"), r.get("line")) for r in (applied.get("reasons") or [])
               if r.get("kind") == "past_rejection"} if applied.get("status") == "done" and not applied.get("undone") else set()
    for row in past_rejections(extra, [getattr(r, "market", "") for r in results or []], product_data):
        if (row["market"], row["line"]) not in handled:
            add(row["market"], "past_rejection", row["line"])
    return out


def past_rejections(extra: Optional[dict], markets: List[str], product_data: Optional[dict] = None) -> List[Dict[str, str]]:
    """이 상품이 이번에 재는 마켓에서 **받았던 반려 사유**(마켓 상태 팝업이 남긴 `review.comment`) 중 글자 사유만."""
    if not extra:
        return []
    from src.pipeline.reject_watch import classify_rejection
    want = {str(m) for m in markets if m}
    title = str((product_data or {}).get("title_ko") or (product_data or {}).get("title") or "")
    out = []
    for key in ("uploaded", "uploaded_removed"):
        for u in extra.get(key) or []:
            if not isinstance(u, dict) or str(u.get("market") or "") not in want:
                continue
            rv = u.get("review") or {}
            cmt = str(rv.get("comment") or "").strip()
            if rv.get("state") != "rejected" or not cmt:
                continue
            kind = classify_rejection(cmt, title=title).get("kind")
            if kind in _PAST_SKIP_KINDS:
                continue
            row = {"market": str(u["market"]), "line": f"지난 반려 사유: {cmt[:300]}"}
            if row not in out:
                out.append(row)
    return out


# ── 지금 값 · 서명 ─────────────────────────────────────────────────────────────

def current_fields(pd: Dict[str, Any]) -> Dict[str, Any]:
    """고칠 수 있는 칸의 지금 값."""
    opts = []
    for o in pd.get("options") or []:
        if isinstance(o, dict):
            opts.append({"name": str(o.get("name_ko") or o.get("name") or ""),
                         "values_ko": [str(v or "") for v in (o.get("values_ko") or [])]})
    tf = _title_field(pd)
    return {"title_field": tf, "title": str(pd.get(tf) or ""), "coupang_name": str(pd.get("coupang_name") or ""),
            "options": opts}


def signature(reasons: List[dict], fields: Dict[str, Any]) -> str:
    blob = json.dumps({"r": sorted((r["kind"], r["line"]) for r in reasons), "f": fields, "m": model(),
                       "v": FORMAT_VERSION}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:20]


# ── Claude 호출 ────────────────────────────────────────────────────────────────

_SYSTEM = (
    "너는 한국 오픈마켓(쿠팡·네이버 스마트스토어) 해외구매대행 상품의 등록 문구를 고치는 검수자다. "
    "주어진 반려·보류 사유를 없애는 데 필요한 **최소한의 글자만** 고친다. "
    "규칙: (1) 할인율·기간·쿠폰·순위·최저가·최고·1위·무료배송 같은 표시광고 문구는 지운다(다른 과장 표현으로 바꾸지 않는다). "
    "(2) 한자·가나는 자연스러운 한국어로 옮긴다. 브랜드·모델명은 원래 표기(영문 등)를 유지한다. "
    "(3) 없는 기능·스펙·인증·호환 기기·수량을 지어내지 않는다. 사실을 더하지 말고 빼기만 한다. "
    "(4) 사유와 상관없는 칸·단어는 그대로 둔다. 상품명은 100자 이내. "
    "(5) 옵션 값은 개수와 순서를 바꾸지 않는다(고칠 값만 바꾼다). "
    "(6) 지난 반려 사유가 사진·서류·카테고리·상표권처럼 글자로 풀 수 없는 것이면 아무것도 바꾸지 말고 fixable=false로 답한다. "
    f"답은 반드시 {_TOOL} 도구로만 한다."
)

_SCHEMA = {
    "type": "object",
    "properties": {
        "fixable": {"type": "boolean", "description": "글자를 고쳐 사유를 풀 수 있으면 true"},
        "title": {"type": "string", "description": "고친 상품명(바꿀 것이 없으면 원래 값 그대로)"},
        "coupang_name": {"type": "string", "description": "고친 쿠팡 상품명(원래 비어 있으면 빈 문자열)"},
        "options": {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": "string"}, "values_ko": {"type": "array", "items": {"type": "string"}}},
            "required": ["name", "values_ko"]}},
        "why": {"type": "string", "description": "무엇을 왜 바꿨는지 한국어 한두 문장"},
    },
    "required": ["fixable", "title", "coupang_name", "options", "why"],
}


def _call(fields: Dict[str, Any], reasons: List[dict], timeout: float) -> Tuple[Optional[dict], dict]:
    """`(tool_input, ai_call)` — 실패면 tool_input None, ai_call.error에 원문."""
    user = ("사유:\n" + "\n".join(f"- [{r['market']}] {r['line']}" for r in reasons)
            + "\n\n지금 값(JSON):\n" + json.dumps({k: v for k, v in fields.items() if k != "title_field"},
                                                ensure_ascii=False, indent=1))
    body = {"model": model(), "max_tokens": 1500, "system": _SYSTEM,
            "tools": [{"name": _TOOL, "description": "고친 칸을 돌려준다", "input_schema": _SCHEMA}],
            "tool_choice": {"type": "tool", "name": _TOOL},
            "messages": [{"role": "user", "content": user}]}
    ai_call = {"provider": "anthropic", "model": model(), "prompt_head": user[:600], "response_head": "", "error": ""}
    req = urllib.request.Request(API_URL, data=json.dumps(body, ensure_ascii=False).encode("utf-8"), method="POST",
                                 headers={"x-api-key": _api_key(), "anthropic-version": API_VERSION,
                                          "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        txt = ""
        try:
            txt = exc.read().decode("utf-8", "replace")
        except Exception:
            pass
        ai_call["error"] = f"HTTP {exc.code} {txt[:300]}"
        return None, ai_call
    except Exception as exc:                                      # noqa: BLE001 — 시간 초과·망 오류
        ai_call["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
        return None, ai_call
    ai_call["response_head"] = raw[:600]
    try:
        d = json.loads(raw)
        usage = d.get("usage") or {}
        ai_call["tokens"] = {"in": usage.get("input_tokens"), "out": usage.get("output_tokens")}
        for blk in d.get("content") or []:
            if blk.get("type") == "tool_use" and blk.get("name") == _TOOL and isinstance(blk.get("input"), dict):
                return blk["input"], ai_call
        ai_call["error"] = f"도구 응답 없음 (stop_reason={d.get('stop_reason')})"
    except Exception as exc:                                      # noqa: BLE001
        ai_call["error"] = f"응답 해석 실패 {type(exc).__name__}"
    return None, ai_call


# ── 검증 ──────────────────────────────────────────────────────────────────────

def _changes(before: Dict[str, Any], got: Dict[str, Any]) -> Tuple[List[dict], List[str]]:
    """`(changes, problems)` — 바뀐 칸 목록과 우리 판정 위반."""
    from src.collectors.ko_polish import ban_hits, has_foreign
    changes: List[dict] = []
    problems: List[str] = []

    def name_change(field, label, old, new):
        new = re.sub(r"\s+", " ", str(new or "")).strip()
        if not old or new == old:
            return
        if not new:
            problems.append(f"{label}이 비었어요")
        elif len(new) > NAME_MAX:
            problems.append(f"{label} {len(new)}자(100자 넘음)")
        elif ban_hits(new):
            problems.append(f"{label}에 표시광고 문구가 남았어요 「{ban_hits(new)[0]}」")
        elif has_foreign(new):
            problems.append(f"{label}에 한자·가나가 남았어요")
        else:
            changes.append({"field": field, "label": label, "before": old, "after": new})

    name_change(before["title_field"], "상품명", before["title"], got.get("title"))
    name_change("coupang_name", "쿠팡 상품명", before["coupang_name"], got.get("coupang_name"))
    new_opts = got.get("options") or []
    for i, o in enumerate(before["options"]):
        n = new_opts[i] if i < len(new_opts) and isinstance(new_opts[i], dict) else None
        if n is None:
            continue
        nv = [re.sub(r"\s+", " ", str(v or "")).strip() for v in (n.get("values_ko") or [])]
        if nv == o["values_ko"]:
            continue
        if len(nv) != len(o["values_ko"]):
            problems.append(f"옵션 「{o['name']}」 값 개수가 바뀌었어요({len(o['values_ko'])}→{len(nv)})")
            continue
        if len(set(v for v in nv if v)) != len([v for v in nv if v]):
            problems.append(f"옵션 「{o['name']}」 값이 겹쳐요")
            continue
        for j, (a, b) in enumerate(zip(o["values_ko"], nv)):
            if a == b or not a:
                continue
            if not b:
                problems.append(f"옵션 「{o['name']}」 값이 비었어요")
            elif ban_hits(b):
                problems.append(f"옵션 값에 표시광고 문구가 남았어요 「{ban_hits(b)[0]}」")
            elif has_foreign(b):
                problems.append("옵션 값에 한자·가나가 남았어요")
            else:
                changes.append({"field": "option", "option": i, "index": j, "label": f"옵션 「{o['name']}」",
                                "before": a, "after": b})
    return changes, problems


# ── 실행 ──────────────────────────────────────────────────────────────────────

def run(product_data: Dict[str, Any], reasons: List[dict], *, timeout: float = 20.0,
        previous: Optional[dict] = None) -> dict:
    """Claude로 고친다 — 기록 한 벌(`status`: done · nochange · failed · skipped). 쓰기(저장)는 부르는 쪽."""
    now = datetime.now(timezone.utc).isoformat()
    fields = current_fields(product_data)
    sig = signature(reasons, fields)
    rec = {"v": FORMAT_VERSION, "at": now, "model": model(), "reasons": reasons, "sig": sig, "changes": [],
           "status": "", "error": "", "why": ""}
    if not reasons:
        return {**rec, "status": "skipped", "error": "고칠 글자 사유 없음"}
    if not enabled():
        return {**rec, "status": "skipped", "error": "ANTHROPIC_API_KEY 없음 — 자동 수정 안 함"}
    if previous and previous.get("sig") == sig and previous.get("status") in ("done", "nochange", "failed"):
        return {**previous, "status": "cached"}
    cap = int(os.getenv("REJECT_AUTOFIX_DAILY_CAP", "200") or 200)
    try:
        from src.db import image_translate_queue_pg as st
        took, n = st.take_start("reject_autofix:day:" + now[:10], cap)
    except Exception:                                             # noqa: BLE001 — 세지 못하면 막지 않는다
        took, n = True, -1
    if not took:
        return {**rec, "status": "skipped", "error": f"오늘 자동 수정 상한 {cap}건을 다 썼어요"}
    got, ai_call = _call(fields, reasons, timeout)
    rec["ai_call"] = ai_call
    if got is None:
        return {**rec, "status": "failed", "error": ai_call.get("error") or "응답 없음"}
    rec["why"] = str(got.get("why") or "")[:300]
    if got.get("fixable") is False:
        return {**rec, "status": "nochange", "error": "글자로 풀 사유가 아니라고 판단 — " + rec["why"]}
    changes, problems = _changes(fields, got)
    if problems:
        return {**rec, "status": "failed", "error": "고친 값이 우리 판정을 못 넘었어요 — " + " · ".join(problems[:3])}
    if not changes:
        return {**rec, "status": "nochange", "error": "바꾼 칸이 없어요 — " + rec["why"]}
    rec["changes"] = changes
    rec["status"] = "done"
    logger.info("[반려 자동 수정] 칸 %d개 고침 model=%s 사유=%s", len(changes), rec["model"],
                ",".join(sorted({r['kind'] for r in reasons})))
    return rec


def apply(product_data: Dict[str, Any], rec: Optional[dict]) -> Dict[str, Any]:
    """기록의 바뀐 칸을 싣는다 — **지금 값이 원래 값과 같을 때만**(셀러가 고친 칸은 셀러가 이긴다). 되돌린 기록은 싣지 않는다."""
    if not isinstance(rec, dict) or rec.get("status") != "done" or rec.get("undone"):
        return product_data
    pd = dict(product_data)
    opts = None
    applied = 0
    for c in rec.get("changes") or []:
        f = c.get("field")
        if f == "option":
            if opts is None:
                opts = [dict(o) if isinstance(o, dict) else o for o in (pd.get("options") or [])]
            i, j = int(c.get("option", -1)), int(c.get("index", -1))
            if 0 <= i < len(opts) and isinstance(opts[i], dict):
                vals = list(opts[i].get("values_ko") or [])
                if 0 <= j < len(vals) and str(vals[j] or "") == c.get("before"):
                    vals[j] = c["after"]
                    opts[i]["values_ko"] = vals
                    applied += 1
        elif f in ("title_ko", "title", "coupang_name"):
            if str(pd.get(f) or "") == c.get("before"):
                pd[f] = c["after"]
                applied += 1
    if opts is not None:
        pd["options"] = opts
    if applied:
        pd["reject_autofix"] = rec
    return pd
