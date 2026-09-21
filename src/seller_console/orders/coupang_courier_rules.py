"""쿠팡 택배사 코드표 **사용 규칙** — 검색·검증 (F44-a).

데이터는 [[coupang_courier_codes]]가 정본이고 **거기엔 로직을 두지 않는다**
(문서를 그대로 옮긴 표라, 코드가 섞이면 다음 개정 때 무엇이 문서고 무엇이 우리 것인지 갈린다).

## 이 모듈이 하는 셋

| | 무엇 | 규칙 |
|---|---|---|
| **검색** | `find(질의)` | **코드 정확일치 → 이름/별칭 부분일치** 순 |
| **판정** | `status(코드)` | 폐업/합병이면 **선택 불가**로 표시 |
| **검증** | `validate(코드, 송장번호)` | 자리수·패턴 — 안 맞으면 **전송 전 보류** |

## ★ 지어내지 않는 자리 셋

1. **후계 매핑 금지.** `KOREX`(대한통운[합병])가 나와도 `CJGLS`로 바꾸지 않는다 —
   문서에 그런 말이 없다. 「합병/폐업 — 쿠팡 미지원」이라고 말하고 멈춘다.
2. **자리수 미지정(`lens=None`)은 검증을 건너뛰고 그렇다고 말한다.**
   「규격 미지정」이라고 적을 뿐, 아무 값이나 맞다고 하지 않는다.
3. **별칭은 문서 이름의 통용 축약만.** `CJ`·`대한통운`·`롯데`·`로젠`·`우체국`·`한진`·`경동`
   일곱뿐이다(오너 승인). 늘릴 때도 **문서 이름에서 자르는 것**만 한다.

## 「○○와 동일」은 상속이다

문서가 자리수 칸에 「대한통운과 동일」이라고 쓴 행들이 있다. 그걸 **그 뜻 그대로**
`inherit=참조코드`로 두고, 검증할 때 참조 대상의 규칙을 따라간다 —
숫자를 베껴 쓰면 원본이 바뀔 때 **사본만 낡는다**(F34-2의 사본 드리프트).
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from .coupang_courier_codes import BY_CODE, COUPANG_COURIERS, CoupangCourier

#: 별칭 — **문서 이름의 통용 축약**(오너 승인 2026-09-21). 발명이 아니다.
COUPANG_ALIASES: Dict[str, str] = {
    "CJ": "CJGLS",
    "대한통운": "CJGLS",
    "롯데": "HYUNDAI",
    "로젠": "KGB",
    "우체국": "EPOST",
    "한진": "HANJIN",
    "경동": "KDEXP",
}

UNSUPPORTED_LABEL = "합병/폐업 — 쿠팡 미지원"
NO_SPEC_LABEL = "규격 미지정"


def _norm(s: str) -> str:
    return "".join(ch for ch in str(s or "").lower().strip() if ch not in " -_()")


def effective_rule(code: str) -> Tuple[Optional[tuple], Optional[str], bool, str]:
    """`(자리수, 패턴, 영문허용, 규칙출처코드)` — **`inherit`를 따라간다**.

    「대한통운과 동일」을 숫자로 베껴 두지 않았으므로, 원본이 바뀌면 상속한 쪽도 같이 바뀐다.
    """
    seen = set()
    cur = BY_CODE.get(str(code or "").strip().upper())
    while cur is not None:
        if cur.inherit and cur.inherit in BY_CODE and cur.inherit not in seen:
            seen.add(cur.code)
            parent = BY_CODE[cur.inherit]
            # 자리수·패턴이 비어 있을 때만 부모를 따른다(문서가 값을 준 행은 그 값이 이긴다).
            lens = cur.lens or parent.lens
            pattern = cur.pattern or parent.pattern
            return lens, pattern, (cur.alnum or parent.alnum), parent.code
        return cur.lens, cur.pattern, cur.alnum, cur.code
    return None, None, False, ""


def lens_label(code: str) -> str:
    """화면에 적을 자리수 규칙 — 없으면 **「규격 미지정」**이라고 말한다."""
    lens, pattern, _alnum, _src = effective_rule(code)
    if pattern:
        c = BY_CODE.get(str(code or "").upper())
        if c is not None and c.note:
            return c.note
        return f"형식 {pattern}"
    if not lens:
        return NO_SPEC_LABEL
    if len(lens) > 3 and list(lens) == list(range(lens[0], lens[-1] + 1)):
        return f"{lens[0]}~{lens[-1]}자리"
    return " · ".join(f"{n}자리" for n in lens)


def status(code: str) -> Dict:
    """한 코드의 상태 — 화면이 그대로 쓴다."""
    c = BY_CODE.get(str(code or "").strip().upper())
    if c is None:
        return {"found": False, "code": str(code or "").strip().upper(), "name": "",
                "active": False, "selectable": False,
                "reason": "쿠팡 코드표에 없는 코드입니다", "lens_label": ""}
    return {
        "found": True, "code": c.code, "name": c.name, "active": c.active,
        # ★ 폐업/합병은 **고를 수 없다.** 후계를 짐작해 바꾸지도 않는다.
        "selectable": c.active,
        "reason": "" if c.active else UNSUPPORTED_LABEL,
        "lens_label": lens_label(c.code),
        "example": c.example,
        "note": c.note,
        "tracking": c.code != "DIRECT",
    }


def validate(code: str, tracking_no: str) -> Tuple[bool, str]:
    """`(보낼 수 있나, 사유)` — 못 보내면 **전송 전에** 멈춘다.

    문서 첫 줄이 「규격에 맞지 않는 운송장은 에러」라고 적고 있다. 그 에러를 마켓에서
    받느니 여기서 멈추는 게 낫다 — 마켓 왕복 한 번과, 사람이 원인을 찾는 시간을 아낀다.

    `lens`가 없으면(규격 미지정) **검증을 건너뛰고 통과**시킨다. 모르면서 막는 것도,
    모르면서 맞다고 하는 것도 안 된다 — 화면이 「규격 미지정」이라고 말한다.
    """
    st = status(code)
    if not st["found"]:
        return False, st["reason"]
    if not st["active"]:
        return False, f"{st['name']}({st['code']})는 {UNSUPPORTED_LABEL}입니다"

    num = str(tracking_no or "").strip()
    if not num:
        return False, "운송장 번호를 입력하세요"

    lens, pattern, alnum, _src = effective_rule(st["code"])
    if pattern and not re.match(pattern, num):
        return False, (f"쿠팡 규격에 맞지 않습니다 — {st['name']}({st['code']}) "
                       f"{lens_label(st['code'])}"
                       + (f" · 예: {st['example']}" if st["example"] else ""))
    if not lens and not pattern:
        # ★★ 문서가 규격을 안 줬다 → **검증을 건너뛴다.** 모르면서 막지 않는다.
        #   (화면은 「규격 미지정」이라고 적어, 통과가 「맞다」가 아님을 말한다.)
        return True, ""
    # 자리수를 준 행은 문서 예시가 전부 숫자다(영문 섞이는 곳은 `alnum`/`pattern`으로 표시돼 있다).
    if not alnum and not pattern and not num.isdigit():
        return False, f"{st['name']}({st['code']})는 숫자만 받습니다"
    if lens and len(num) not in lens:
        return False, (f"쿠팡 규격: {lens_label(st['code'])} — 넣은 값은 {len(num)}자리입니다"
                       + (f" · 예: {st['example']}" if st["example"] else ""))
    return True, ""


def _row(c: CoupangCourier) -> Dict:
    d = status(c.code)
    d["search_terms"] = sorted({c.code, c.code.lower(), c.name, _norm(c.name)} |
                               {a for a, code in COUPANG_ALIASES.items() if code == c.code})
    return d


def find(query: str, limit: int = 20) -> List[Dict]:
    """검색 — **코드 정확일치 → 이름/별칭 부분일치** 순.

    정확일치를 먼저 내는 이유: 코드를 아는 사람은 **그걸 치고**, 그때 부분일치가 위에 오면
    자기가 아는 코드를 한참 찾아야 한다. 폐업 행도 **숨기지 않고** 내되 선택 불가로 표시한다 —
    없는 척하면 「내 택배사가 왜 없지」가 되고, 그건 사유가 사라진 것이다.
    """
    q = str(query or "").strip()
    if not q:
        return [_row(c) for c in COUPANG_COURIERS][:limit]

    qn = _norm(q)
    exact, alias, partial = [], [], []
    for c in COUPANG_COURIERS:
        if c.code.upper() == q.upper():
            exact.append(_row(c))
        elif COUPANG_ALIASES.get(q) == c.code or COUPANG_ALIASES.get(q.upper()) == c.code:
            alias.append(_row(c))
        elif qn and (qn in _norm(c.name) or qn in c.code.lower()):
            partial.append(_row(c))
    return (exact + alias + partial)[:limit]


def resolve_name(name: str) -> str:
    """이름·별칭 → **코드**. 확실할 때만 답한다(애매하면 빈 문자열).

    ★ 이건 「한국어 → 코드」 자동 변환이 **아니다.** 검색 결과에서 사람이 고르게 하는 것이
    정본이고, 이 함수는 **정확히 일치하는 이름·별칭**만 코드로 바꾼다.
    부분일치로 코드를 정하면 그게 침묵 매핑이다(F44 b 금지).
    """
    q = str(name or "").strip()
    if not q:
        return ""
    if q.upper() in BY_CODE:
        return q.upper()
    if q in COUPANG_ALIASES:
        return COUPANG_ALIASES[q]
    hits = [c.code for c in COUPANG_COURIERS if _norm(c.name) == _norm(q)]
    return hits[0] if len(hits) == 1 else ""
