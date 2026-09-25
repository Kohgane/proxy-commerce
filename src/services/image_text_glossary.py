"""src/services/image_text_glossary.py — D3 2단계: **용어집 번역**.

## 어디에 쓰나

D3 렌더 트랙은 텐센트의 **렌더본을 버리고** `TransDetails`를 「박스 + 원문」으로만 쓴다
(1단계). 그 원문을 **우리가 번역해서**(2단계) 박스에 다시 그린다(3단계).

이 파일은 **2단계**다. 번역기 자체는 여기 없다 — **주입받는다**(`translate_fn`).
공급사를 바꿔도 규칙은 그대로여야 하고, 계약이 라이브 호출 없이 규칙을 잴 수 있어야 한다.

## 규칙 셋 (오너 브리프 2026-09-20)

| # | 규칙 | 왜 |
|---|---|---|
| A | **브랜드 토큰(대문자 영문) 보존** | 워드마크를 번역하면 그건 다른 상품이다 |
| D | **영문+숫자만인 줄은 미번역** | 제품 화면 속 UI(시계 화면 등) — 건드리면 가짜가 된다 |
| B | **관용 사전 우선**(`三合一` → `3-in-1`) | 직역이 「삼합일」을 만들었다(실측) |

축 이름(A·B·D)은 [[F33 벤치 5축]]과 **같은 것**을 가리킨다 — 판정과 생성이 같은 표를 본다.

> ★★ **규칙과 판정기가 같은 표를 봐야 한다.** 생성이 쓰는 사전과 채점이 쓰는 사전이
> 다르면, 만들면서 틀리고 재면서 통과한다.

그래서 브랜드 토큰·관용 사전·영문 판정은 **`image_bench_axes`를 그대로 쓴다**(재구현 0).

## 실패는 원문을 남긴다

번역이 실패하면 **원문 그대로** 둔다. 빈 문자열이나 지어낸 말로 덮지 않는다 —
그 줄은 다음 단계에서 「번역 안 됨」으로 보이고, 그게 사실이다.
"""
from __future__ import annotations

import logging
import re
from typing import Callable, Dict, List, Optional

from src.services.image_bench_axes import (IDIOMS, _BRAND_TOKEN, _EN_UI, _NOT_BRAND,  # noqa: F401
                                            is_en_ui)

logger = logging.getLogger(__name__)

# 보호 토큰 — 번역기가 **건드릴 수 없는 모양**이어야 한다. 한글·중국어 번역기가
#   영문 단어를 옮기려 드는 것을 막는다. 숫자만 남겨 파손 시 복원이 실패하도록 둔다
#   (조용히 반쯤 복원되느니 실패가 낫다).
_PH = "␂{}␃"          # STX/ETX — 자연어에 안 나오는 제어문자
_PH_RE = re.compile("␂(\\d+)␃")


def is_untranslatable(source: str) -> bool:
    """이 줄을 **번역하지 않는다**고 판정 — 영문+숫자+기호만인 줄 (규칙 D).

    제품 화면 속 UI(시계의 `12:30`·`START`)가 여기 걸린다. 번역하면 **없던 한국어가
    제품 사진에 생긴다** — 그건 상품을 잘못 설명하는 것이다.
    """
    # D3-6 ② — 판정기(D축)와 **같은 함수**를 쓴다(전각 `Ａｌａｒｍ` 도 영문 UI다).
    return is_en_ui(source)


def brand_tokens_in(source: str) -> List[str]:
    """이 줄의 브랜드 토큰 — 판정기와 **같은 사전**을 쓴다 (규칙 A)."""
    out, seen = [], set()
    for tok in _BRAND_TOKEN.findall(str(source or "")):
        if tok in _NOT_BRAND or tok in seen or tok.isdigit():
            continue
        seen.add(tok)
        out.append(tok)
    return out


def protect(source: str) -> tuple:
    """브랜드 토큰을 자리표시자로 바꾼다 — `(masked, tokens)` (규칙 A).

    번역기에 원문 브랜드를 그대로 주면 옮기거나 음차한다(`PORTER` → `포터`).
    **워드마크는 번역 대상이 아니다** — 그건 그 물건의 이름이다.
    """
    toks = brand_tokens_in(source)
    masked = str(source or "")
    for i, tok in enumerate(toks):
        masked = re.sub(r"\b" + re.escape(tok) + r"\b", _PH.format(i), masked)
    return masked, toks


def restore(text: str, tokens: List[str]) -> tuple:
    """자리표시자를 브랜드로 되돌린다 — `(text, ok)`.

    **두 가지를 다 본다:**

    1. 남은 자리표시자가 있나 — 제어문자가 상품 이미지에 박히면 안 된다.
    2. **넣었던 토큰이 전부 돌아왔나** — 번역기가 자리표시자를 통째로 **버리면**
       남은 것도 없고(1번 통과) **브랜드는 사라진다.** 그게 더 나쁘다:
       깨진 글자는 눈에 띄지만, 없어진 브랜드는 안 띈다.

    하나라도 어긋나면 `ok=False`이고, 호출부가 **원문을 남긴다**.
    """
    out = str(text or "")
    missing = False
    for i, tok in enumerate(tokens):
        ph = _PH.format(i)
        if ph not in out:
            missing = True          # 번역기가 자리표시자를 지웠다 = 브랜드 소실
            continue
        out = out.replace(ph, tok)
    if missing or _PH_RE.search(out):
        return out, False
    return out, True


def apply_idioms(source: str, translated: str) -> str:
    """관용구가 **직역으로 나왔으면** 바른 말로 바꾼다 (규칙 B).

    사전에 있는 것만 손댄다. 없는 표현은 **건드리지 않는다** —
    모르는 말을 고치는 건 번역이 아니라 발명이다.
    """
    out = str(translated or "")
    for idi in IDIOMS:
        if idi["source"] not in str(source or ""):
            continue
        good = idi["good"][0]
        for bad in idi["bad"]:
            if bad in out:
                out = out.replace(bad, good)
        # 직역도 바른 말도 없는데 원문에 관용구가 있었다면, 바른 말을 **덧붙이지 않는다**.
        #   번역기가 뜻을 옮겼을 수도 있다(예: 「3가지 기능」). 판정은 벤치가 한다.
    return out


#: ★ D3-4 ④ — **문체 지시**(오너 브리프 2026-09-21).
#:
#: 상품 이미지의 글자는 상품명이 아니라 **광고 카피**다. 일반 번역 프롬프트는
#: 「~입니다」로 끝나는 평서문을 낸다 — 표지에 그게 박히면 광고가 아니라 설명문이 된다.
#:
#: ⚠️ 이 지시는 **지시를 따를 수 있는 프로바이더**에서만 효력이 있다(LLM). 사전형 MT는
#: 문체를 못 바꾸므로, 그럴 때 번역기는 `style_applied=False`를 남긴다 — 따른 척하지 않는다.
STYLE_INSTRUCTION = (
    "이 문장은 상품 이미지에 박히는 **제품 광고 카피**입니다. 짧은 명사구나 구호로 쓰고, "
    "평서형 종결(~입니다·~합니다·~이다·~해요)을 쓰지 마세요."
)


def _norm_line(s: str) -> str:
    return re.sub(r"\s+", "", str(s or ""))


#: 원문 줄 → **오너가 확정한 정본 한국어**. 표는 `image_bench_axes.IDIOMS`가 정본이고
#: 여기서는 **읽기만 한다** — 생성과 판정이 두 표를 보면 만들면서 틀리고 재면서 통과한다.
LINE_GLOSSARY = {_norm_line(i["source"]): i["ko"] for i in IDIOMS if i.get("ko")}


def glossary_line(source: str) -> str:
    """이 줄에 **정본 한국어**가 있나 — 없으면 빈 문자열.

    실측으로 오역이 확인된 카피만 들어 있다. 있으면 **번역기를 부르지 않는다**:
    이미 정답을 아는 줄에 돈과 시간을 쓰고 **또 틀릴** 이유가 없다.
    """
    return LINE_GLOSSARY.get(_norm_line(source), "")


#: 관용구의 **정본 한국어** — `ko`가 있으면 그것, 없으면 `good`의 첫 형태(`三合一` → `3-in-1`).
IDIOM_CANON = [(i["source"], i.get("ko") or i["good"][0]) for i in IDIOMS if i.get("good")]


def protect_idioms(masked: str, tokens: List[str]) -> tuple:
    """줄 **안의** 관용구를 자리표시자로 바꾼다 — `(masked, tokens)` (D3-6 ①).

    ## 왜 (오너 벤치 실측 2026-09-25)

    용어집은 **줄 전체가 같을 때만** 먹었다(`glossary_line`). `三合一`이 다른 글자와 한 줄에
    붙어 오면 통째로 번역기에 가서 「삼합일」이 됐고, `拒绝混乱`은 페이지마다 다른 말이 됐다.
    관용구는 **번역기에 주지 않는다** — 브랜드와 같은 자리표시자로 감싸 두고, 돌아올 때
    정본을 박는다. 번역기가 자리표시자를 버리면 `restore`가 실패로 잡는다(원문 유지).
    """
    out, toks = str(masked or ""), list(tokens or [])
    for src, canon in IDIOM_CANON:
        if src in out:
            out = out.replace(src, _PH.format(len(toks)))
            toks.append(canon)
    return out, toks


def _only_placeholders(masked: str) -> bool:
    """번역할 글자가 남지 않았다(자리표시자·공백·기호뿐) — 번역기를 부를 이유가 없다."""
    rest = _PH_RE.sub("", str(masked or ""))
    return not re.search(r"[^\W\d_]", rest)


# ─────────────────────────────────────────────────────────────────────────────
# D3-6 ①-b — 라인명 삭제(`line_name_drop`, 오너 결정 2026-09-25)
# ─────────────────────────────────────────────────────────────────────────────
#
# 브랜드 워드마크(`SPORTLINK`) 옆에 붙은 **2~4자 한자**(`随行盾`)는 제품 **라인명**이다.
# 번역하면 「수행방패」 같은 없는 상품명이 생긴다. 오너 결정: **번역 금지, 지우고 아무것도 안 쓴다.**
# 브랜드 로고는 그대로 둔다(영문 UI 규칙이 이미 안 건드린다).
LINE_NAME_RULE = "line_name_drop"
_LINE_NAME = re.compile(r"^[\u4e00-\u9fff]{2,4}$")


def _rect(box) -> Optional[tuple]:
    try:
        x, y = float(box.get("x") or 0), float(box.get("y") or 0)
        w, h = float(box.get("w") or 0), float(box.get("h") or 0)
    except (AttributeError, TypeError, ValueError):
        return None
    return (x, y, w, h) if w > 0 and h > 0 else None


def boxes_adjacent(a, b) -> bool:
    """두 박스가 **붙어 있나** — 같은 줄(세로가 반 이상 겹치고 가로 틈이 글자 높이 2배 이내)
    또는 위아래(가로가 30% 이상 겹치고 세로 틈이 글자 높이 1.5배 이내).

    ⚠️ 비율은 오너 브리프의 「같은 행/인접 박스」를 옮긴 것이다 — 실물 3장으로 교정 전이다.
    """
    ra, rb = _rect(a or {}), _rect(b or {})
    if not ra or not rb:
        return False
    ax, ay, aw, ah = ra
    bx, by, bw, bh = rb
    hmax = max(ah, bh)
    v_overlap = min(ay + ah, by + bh) - max(ay, by)
    h_overlap = min(ax + aw, bx + bw) - max(ax, bx)
    if v_overlap >= 0.5 * min(ah, bh):
        h_gap = max(bx - (ax + aw), ax - (bx + bw), 0)
        return h_gap <= 2.0 * hmax
    if h_overlap >= 0.3 * min(aw, bw):
        v_gap = max(by - (ay + ah), ay - (by + bh), 0)
        return v_gap <= 1.5 * hmax
    return False


def _is_brand_only(source: str) -> bool:
    return is_en_ui(source) and bool(brand_tokens_in(source))


def line_name_drops(lines: List[Dict]) -> Dict[int, str]:
    """`{줄 번호: 사유}` — 라인명으로 보고 **지우기만** 할 줄."""
    brands = [ln.get("box") for ln in lines or [] if _is_brand_only(str(ln.get("source") or ""))]
    out = {}
    if not brands:
        return out
    for i, ln in enumerate(lines or []):
        src = re.sub(r"\s+", "", str(ln.get("source") or ""))
        if _LINE_NAME.match(src) and any(boxes_adjacent(ln.get("box"), b) for b in brands):
            out[i] = f"{LINE_NAME_RULE}: 브랜드 옆 라인명 {src} — 번역하지 않고 지운다(오너 결정)"
    return out


def same_box_line_name(source: str) -> str:
    """브랜드와 라인명이 **한 박스**에 온 줄(`SPORTLINK 随行盾`)이면 사유, 아니면 빈 문자열.

    한 박스 안에서 라인명만 떼어 지우려면 글자 위치를 **추정**해야 한다 — 그건 지어내는 것이다.
    그렇다고 번역하면 오너 결정(「번역 금지」)을 어긴다. 그래서 **원문 그대로 둔다**(안 건드림).
    """
    toks = brand_tokens_in(source)
    if not toks:
        return ""
    rest = str(source or "")
    for t in toks:
        rest = re.sub(r"\b" + re.escape(t) + r"\b", "", rest)
    rest = re.sub(r"\s+", "", rest)
    if _LINE_NAME.match(rest):
        return (f"{LINE_NAME_RULE}: 브랜드와 한 박스인 라인명 {rest} — 떼어 지울 수 없어 "
                "원문 그대로 둔다(번역 금지)")
    return ""


def plan_line(source: str) -> Dict:
    """이 줄을 어떻게 다룰지 — `{action, reason, tokens}`. 번역 전에 정해진다."""
    s = str(source or "").strip()
    if not s:
        return {"action": "skip", "reason": "빈 줄", "tokens": []}
    if is_untranslatable(s):
        return {"action": "keep", "reason": "영문·숫자만 — 제품 화면 UI", "tokens": []}
    return {"action": "translate", "reason": "", "tokens": brand_tokens_in(s)}


def translate_lines(lines: List[Dict], translate_fn: Callable[[str], str],
                    *, target: str = "ko") -> List[Dict]:
    """줄 목록에 규칙을 적용해 **그려질 문자열**을 정한다.

    `lines` = 1단계가 낸 `[{source, target, box, ...}]`. 공급사의 `target`(렌더본에 쓰인
    번역)은 **참고만** 한다 — 우리가 다시 번역한다(그게 이 트랙의 요지다).

    각 줄에 붙는 것: `render_text`(그릴 글자) · `action` · `rule_reason` ·
    `protected`(보호한 브랜드) · `translate_error`(있으면 원문 유지).

    **`translate_fn`은 주입이다.** 여기서 공급사를 고르지 않는다 —
    계약이 라이브 호출 없이 규칙만 잴 수 있어야 한다.
    """
    out = []
    drops = line_name_drops(lines or [])
    for n, ln in enumerate(lines or []):
        row = dict(ln)
        src = str(row.get("source") or "")
        plan = plan_line(src)
        row["action"] = plan["action"]
        row["rule_reason"] = plan["reason"]
        row["protected"] = plan["tokens"]
        row["translate_error"] = ""

        if n in drops:
            # ①-b — **지우고 아무것도 안 쓴다.** 3단계가 `action == "drop"`을 지우기만 한다.
            row.update(action="drop", rule_reason=drops[n], render_text="", rule=LINE_NAME_RULE)
            out.append(row)
            continue

        same = same_box_line_name(src) if plan["action"] == "translate" else ""
        if same:
            row.update(action="keep", rule_reason=same, rule=LINE_NAME_RULE)
            plan["action"] = "keep"

        if plan["action"] != "translate":
            row["render_text"] = src
            out.append(row)
            continue

        # ★ D3-4 ④ — **정본이 있는 줄은 번역기를 안 부른다.** 답을 아는데 또 물어서
        #   또 틀릴 이유가 없다. 어디서 왔는지는 `glossary_hit`으로 남는다.
        fixed = glossary_line(src)
        if fixed:
            row["render_text"] = fixed
            row["glossary_hit"] = src
            out.append(row)
            continue

        masked, toks = protect(src)
        # D3-6 ① — 줄 **안의** 관용구도 번역기에 주지 않는다(정본을 박는다).
        masked, toks = protect_idioms(masked, toks)
        if toks[len(plan["tokens"]):]:
            row["glossary_hit"] = src
        if _only_placeholders(masked):
            # 번역할 말이 남지 않았다 — 부르지 않는다(브랜드·정본만으로 된 줄).
            text, ok = restore(masked, toks)
            row["render_text"] = text
            out.append(row)
            continue
        try:
            got = translate_fn(masked)
        except Exception as exc:
            # 실패하면 **원문을 남긴다.** 빈칸이나 지어낸 말로 덮지 않는다.
            logger.warning("[D3 용어집] 번역 실패(원문 유지): %s", exc)
            row["render_text"] = src
            row["translate_error"] = f"{type(exc).__name__}: {str(exc)[:120]}"
            out.append(row)
            continue

        text, ok = restore(str(got or ""), toks)
        if not ok or not str(text).strip():
            row["render_text"] = src
            row["translate_error"] = ("브랜드 자리표시자를 되돌리지 못했습니다"
                                      if not ok else "번역기가 빈 문자열을 돌려줬습니다")
            out.append(row)
            continue

        row["render_text"] = apply_idioms(src, text)
        out.append(row)
    return out


def summarize(rows: List[Dict]) -> Dict:
    """무엇을 했는지 — `{total, translated, kept, failed, glossary}`. **분모는 잰 것만.**"""
    rows = rows or []
    return {
        "total": len(rows),
        "translated": sum(1 for r in rows if r.get("action") == "translate"
                          and not r.get("translate_error")),
        "kept": sum(1 for r in rows if r.get("action") == "keep"),
        "failed": sum(1 for r in rows if r.get("translate_error")),
        # 정본 용어집이 받아 낸 줄 — 번역기를 안 부른 수(D3-4 ④).
        "glossary": sum(1 for r in rows if r.get("glossary_hit")),
    }
