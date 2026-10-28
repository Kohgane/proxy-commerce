"""순찰 106-C(오너 2026-10-26) — 등록 전 AI 검수: 「한국 손님이 보면 이상한 점」 5줄 이내. **AI는 제안만, 결정은 사람.**

- 재료(글자만 — 사진은 보내지 않는다): 상품명 · 옵션(나가는 한국어 값) · 판매가(원) · 사진 목록(대표·상세 장 수) · 상세 앞 3장의 사진 글자.
- 공급자: Anthropic만(`ANTHROPIC_API_KEY`) — `llm.complete`가 월 예산(`AI_MONTHLY_BUDGET_USD`)을 먼저 본다.
- **상품당 1회**: 결과는 수집 기록 `ai_review`에 남고, 다음 사전검증은 그 값을 그대로 보인다(다시 부르지 않는다).
- 가족(`FAMILY_EMAILS`) 상품이면 오너 텔레그램에 같은 줄을 한 번.

반환 모양(카드): `{status: done|skip|failed, lines:[...], at, provider, model, usd, why}`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

MAX_LINES = 5
LINE_MAX = 90
KEY = "ai_review"

_SYSTEM = ("당신은 한국 온라인 쇼핑몰(쿠팡·스마트스토어)의 꼼꼼한 상품 검수 담당자입니다. 해외 구매대행 상품의 등록 직전 글자를 보고, "
           "한국 손님이 보면 어색하거나 오해하거나 불안해할 점만 짚습니다. 고치는 글은 쓰지 말고, 무엇이 왜 이상한지만 짧게.")


def _text(pd: dict, ex: dict) -> str:
    """AI에 보낼 글 — 상품명 · 옵션 · 가격 · 사진 목록 · 상세 앞 3장 글자. 비밀값·주소(URL)는 넣지 않는다."""
    lines = [f"상품명: {str(pd.get('title_ko') or pd.get('title') or '').strip()[:120]}"]
    cn = str(pd.get("coupang_name") or "").strip()
    if cn:
        lines.append(f"쿠팡 상품명: {cn[:120]}")
    try:
        from src.collectors import option_ko
        for a in option_ko.options_view(pd)[:4]:
            vals = [v.get("ko") or v.get("src") for v in a.get("values") or []][:12]
            lines.append(f"옵션 {a.get('name_ko') or a.get('name')}: " + " / ".join(str(v) for v in vals))
    except Exception as exc:                                     # noqa: BLE001
        logger.debug("[AI 검수] 옵션 읽기 실패: %s", exc)
    try:
        from src.seller_console.shipping_ratio import sell_krw
        sell = int(round(sell_krw(pd, "coupang") or 0))
    except Exception:                                            # noqa: BLE001
        sell = 0
    src_price = f"{pd.get('price') or ''} {pd.get('currency') or ''}".strip()
    if sell:
        lines.append(f"판매가(시스템 계산값 — 화면엔 정확한 금액으로만 나감): {sell:,}원")   # V42-1: 「약」·원가 통화는 우리 표기라 검수 대상 아님
    imgs = [u for u in (pd.get("images_effective") or pd.get("images") or []) if u]
    det = [u for u in (pd.get("detail_images") or []) if u]
    lines.append(f"사진: 대표·갤러리 {len(imgs)}장 · 상세 {len(det)}장")
    try:
        from src.services import detail_image_plan as dip
        by_idx = {int(e.get("idx", -1)): e for e in (ex.get("detail_images_ko") or []) if isinstance(e, dict)}
        for i in sorted(by_idx)[:3]:
            e = by_idx[i]
            t = str(e.get("target_text") or "").strip() or dip.entry_text(e)
            if t:
                lines.append(f"상세 {i + 1}번 사진 글자: {t[:300]}")
    except Exception as exc:                                     # noqa: BLE001
        logger.debug("[AI 검수] 상세 글자 읽기 실패: %s", exc)
    return "\n".join(lines)


FIELDS = ("title", "option", "description", "none")        # V42-1: 짚은 점이 어디 것인지 — title만 「수락」으로 바로 고친다


def _prompt(body: str) -> str:
    return (body + f"\n\n위 상품이 한국 쇼핑몰에 올라가기 직전이에요. 한국 손님이 보기에 이상한 점을 **최대 {MAX_LINES}개**로 짚으세요"
            "(번역투·뜻이 안 통하는 말·중국 가게 안내·숫자/단위 오류·옵션과 상품명 불일치·과장 표현 등). "
            f"issue는 {LINE_MAX}자 이내로 어디가 왜 이상한지. field는 그 점이 어디 것인지 — title(상품명)·option(옵션)·description(상세)·none(그 외). "
            "field가 title이면 fix에 **고친 상품명 전체**(한 줄, 80자 이내)를 넣고, 그 외는 fix를 null로. "
            "판매가·원가 줄은 시스템 값이라 표기 형식(약·통화)은 짚지 마세요. 이상한 점이 없으면 빈 목록.\n"
            '답 형식: {"items": [{"issue": "…", "field": "title|option|description|none", "fix": "…" 또는 null}]}')


def enabled() -> bool:
    """`AI_REVIEW`(기본 1) — 0이면 부르지 않는다(저장된 검수는 그대로 보인다)."""
    import os
    return str(os.getenv("AI_REVIEW", "1")).strip().lower() not in ("0", "false", "no", "off")


def cached(ex: dict) -> Optional[Dict[str, Any]]:
    """저장된 검수(성공한 것만 — 실패·건너뜀은 다음 사전검증에서 다시 부른다)."""
    r = (ex or {}).get(KEY)
    return dict(r) if isinstance(r, dict) and r.get("status") == "done" else None


def run(pd: dict, ex: dict) -> Dict[str, Any]:
    """한 번 부른다(이미 있으면 그대로 돌려준다). 키가 없거나 예산이 넘치면 `skip`/`failed` — 등록은 막지 않는다."""
    have = cached(ex)
    if have:
        return dict(have, cached=True)
    from src.ai import llm
    if not enabled():
        return {"status": "skip", "lines": [], "why": "AI 검수가 꺼져 있어요(AI_REVIEW=0)"}
    if not llm.anthropic_ready():
        return {"status": "skip", "lines": [], "why": "AI 키가 없어 검수를 건너뛰었어요"}
    r = llm.complete(_prompt(_text(pd, ex)), system=_SYSTEM, size="small", max_tokens=600, purpose="ai_review",
                     timeout=20.0, json_mode=True, providers=["anthropic"])
    now = datetime.now(timezone.utc).isoformat()
    if not r.get("text"):
        return {"status": "failed", "lines": [], "at": now, "why": str(r.get("error") or "빈 답")[:160]}
    js = llm.parse_json(r["text"]) or {}
    items = _parse_items(js)
    return {"status": "done", "lines": [it["issue"] for it in items], "items": items, "at": now,
            "provider": r.get("provider"), "model": r.get("model"), "usd": round(float(r.get("usd") or 0), 5)}


def _parse_items(js) -> List[Dict[str, Any]]:
    """`{"items":[{issue, field, fix}]}` → 정리된 목록. 옛 `{"lines":[…]}`도 받는다(field none)."""
    out: List[Dict[str, Any]] = []
    raw = js.get("items") if isinstance(js, dict) else None
    if not isinstance(raw, list):
        raw = [{"issue": x, "field": "none"} for x in ((js.get("lines") if isinstance(js, dict) else None) or [])]
    for x in raw:
        if isinstance(x, str):
            x = {"issue": x, "field": "none"}
        if not isinstance(x, dict):
            continue
        issue = str(x.get("issue") or "").strip()[:LINE_MAX]
        if not issue:
            continue
        field = str(x.get("field") or "none").strip().lower()
        field = field if field in FIELDS else "none"
        fix = str(x.get("fix") or "").strip()[:120] if field == "title" else ""
        out.append({"issue": issue, "field": field, "fix": fix or None})
        if len(out) >= MAX_LINES:
            break
    return out


def decide(ex: dict, idx: int, action: str, *, by: str = "") -> Dict[str, Any]:
    """V42-1(오너 2026-10-28 20:08 「수락·기각 버튼이 있어서 누르면 바로 수정되게」) — 한 항목에 결정 기록.
    accept + field=title → `title_ko`(·`coupang_name`이 있으면 같이) 를 fix로 바꾼다. 되돌리기 = 편집 칸에서 직접(원래 값은 `prev`에 남긴다).
    반환 `{ok, changed:{필드: 새 값}, why}`."""
    r = (ex or {}).get(KEY)
    if not isinstance(r, dict) or r.get("status") != "done":
        return {"ok": False, "changed": {}, "why": "AI 검수 결과가 없어요 — 사전검증을 먼저"}
    items = r.get("items") or [{"issue": x, "field": "none", "fix": None} for x in (r.get("lines") or [])]
    try:
        it = items[int(idx)]
    except (ValueError, TypeError, IndexError):
        return {"ok": False, "changed": {}, "why": "그 항목이 없어요"}
    if action not in ("accept", "reject"):
        return {"ok": False, "changed": {}, "why": "accept 또는 reject"}
    changed: Dict[str, Any] = {}
    if action == "accept":
        if it.get("field") != "title" or not it.get("fix"):
            return {"ok": False, "changed": {}, "why": "이 항목은 자동으로 못 고쳐요 — 「편집」으로 직접"}
        prev = {"title_ko": ex.get("title_ko"), "coupang_name": ex.get("coupang_name")}
        ex["title_ko"] = it["fix"]
        changed["title_ko"] = it["fix"]
        if ex.get("coupang_name"):
            ex["coupang_name"] = it["fix"]
            changed["coupang_name"] = it["fix"]
        ex.pop("pv_ready", None)                                 # 상품명이 바뀌었다 — 「등록 준비 완료」는 다시 검증 뒤에
    dec = dict(r.get("decisions") or {})
    dec[str(int(idx))] = {"action": action, "at": datetime.now(timezone.utc).isoformat(), "by": str(by or "")[:60],
                          **({"prev": prev} if action == "accept" else {})}
    r["decisions"] = dec
    r["items"] = items
    ex[KEY] = r
    return {"ok": True, "changed": changed, "why": ""}


def telegram_text(title: str, item_id: str, review: Dict[str, Any]) -> str:
    body = "\n".join(f"· {x}" for x in review.get("lines") or []) or "· 이상한 점 없음"
    return f"🧐 등록 전 AI 검수(가족 상품)\n{str(title)[:60]} ({str(item_id)[:8]})\n{body}\n— AI 제안이에요. 결정은 사람이."


def card(review: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """카드 모양 — 접힌 줄 「AI 검수」. 없으면 {}."""
    if not isinstance(review, dict) or review.get("status") not in ("done", "failed", "skip", "running"):
        return {}
    out = {k: review.get(k) for k in ("status", "lines", "at", "why", "cached", "decisions") if review.get(k) is not None}
    items = review.get("items")
    if items is None and review.get("lines"):
        items = [{"issue": x, "field": "none", "fix": None} for x in review["lines"]]      # 옛 저장본
    if items is not None:
        out["items"] = items
    return out
