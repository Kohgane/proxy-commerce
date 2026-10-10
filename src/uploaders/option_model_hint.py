"""Y7-N(오너 2026-10-10) — 옵션 이름 「사이즈」인데 값이 **모델명** 하나뿐인 축 → 이름을 「모델」로 바꾸자는 **후보**.

실측: BLACKHOLES 블랙홀 미니 벽등 — 옵션 「大小」(→사이즈) 값 = 【BLACKHOLES】 하나. 사이즈가 아니라 모델명이다.
쿠팡 메타 매핑(사이즈 칸에 【BLACKHOLES】)은 실패가 맞고 **그대로 둔다** — 여기선 이름 후보만 낸다(자동 적용 없음).

조건: 옵션 이름(원문 또는 보이는 이름)이 사이즈 계열(大小·尺寸·尺码·사이즈·size)이고, 값이 **1개**이며 그 값이
  `【…】`로 감싸였거나 영문 대문자 낱말 하나(숫자·`-`·`_` 허용, 소문자 없음)일 때. 사이즈 표기(XL·FREE·3XL…)는 뺀다.
"""
from __future__ import annotations

import re
from typing import Dict, List

SUGGEST = "모델"
_SIZE_NAMES = {"大小", "尺寸", "尺码", "尺碼", "사이즈", "크기", "size"}
_BRACKET = re.compile(r"^\s*【[^【】]{1,40}】\s*$")
_CAPS = re.compile(r"^\s*[A-Z][A-Z0-9_\-]{1,39}\s*$")
# 진짜 사이즈 표기(대문자지만 모델명 아님) — XS·S·M·L·XL·XXL·3XL·FREE·ONESIZE 등
_SIZE_INNER = re.compile(r"[号码尺寸]|cm|mm|inch|英寸|사이즈|\d+\s*(?:호|인치)", re.I)   # 【大号】·【30cm】 — 사이즈 맞다
_SIZE_WORD = re.compile(r"^\s*(?:X{0,4}[SML]|\dX[SL]|FREE|FREESIZE|ONESIZE|OS|F|[A-Z]?\d+[A-Z]?)\s*$")


def _val(v) -> str:
    return str((v.get("name") if isinstance(v, dict) else v) or "").strip()


def looks_like_model(value: str) -> bool:
    s = str(value or "").strip()
    if _BRACKET.match(s):
        inner = s.strip("【】 ")
        return not (_SIZE_WORD.match(inner) or _SIZE_INNER.search(inner))
    return bool(_CAPS.match(s)) and not _SIZE_WORD.match(s)


def suggestions(product: Dict) -> List[Dict]:
    """`[{orig, label, value, suggest, why}]` — 해당 축이 없으면 []. `orig`=원래 옵션 이름(저장 열쇠)."""
    out: List[Dict] = []
    for o in (product or {}).get("options") or []:
        if not isinstance(o, dict):
            continue
        names = {str(o.get(k) or "").strip() for k in ("name", "src_name", "name_ko")}
        if not any(n.lower() in _SIZE_NAMES or n in _SIZE_NAMES for n in names if n):
            continue
        vals = [_val(v) for v in (o.get("values") or []) if _val(v)]
        if len(vals) != 1 or not looks_like_model(vals[0]):
            continue
        label = str(o.get("name_ko") or o.get("name") or "").strip()
        if label in ("大小", "尺寸", "尺码", "尺碼"):
            label = "사이즈"
        out.append({"orig": str(o.get("src_name") or o.get("name") or "").strip(), "label": label,
                    "value": vals[0], "suggest": SUGGEST,
                    "why": f"「{label}」 값이 {vals[0]} 하나뿐 — 사이즈가 아니라 모델명 같아요"})
    return out
