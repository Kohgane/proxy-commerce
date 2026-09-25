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

from src.services.image_bench_axes import IDIOMS, _BRAND_TOKEN, _EN_UI, _NOT_BRAND  # noqa: F401

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
    s = str(source or "").strip()
    return bool(s) and bool(_EN_UI.match(s))


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
    for ln in lines or []:
        row = dict(ln)
        src = str(row.get("source") or "")
        plan = plan_line(src)
        row["action"] = plan["action"]
        row["rule_reason"] = plan["reason"]
        row["protected"] = plan["tokens"]
        row["translate_error"] = ""

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
