"""src/uploaders/coupang_options.py — F48-b 쿠팡 **구매옵션 계획**(전송 전).

## 왜 (오너 브리프 F48, 2026-09-25 · 9/30 D-5)

수행방패 쿠팡 등록이 **구매옵션**에서 거부됐다. 옛 경로(`attr_safe`)는 필수 속성의 값을 못 찾으면
**기본값을 지어 채웠다** — 색상이면 `블랙`, 신발사이즈면 `260`, 사이즈면 `FREE`.
그 값은 상품의 사실이 아니다. 오너 규칙이 바뀌었다:

> MANDATORY attribute 누락 → **보류** + 「필수 옵션: …」 · groupNumber **택1** 규칙 준수 ·
> EXPOSED 옵션은 **메타에 있는 attributeTypeName만** · `dataType=NUMBER`면 값+`usableUnits` 단위("1개") ·
> 타오바오 옵션명이 메타에 없으면 옵션으로 보내지 않고 **단일 아이템 + 「수량 1개」** · 원 옵션은 검색어에만 ·
> 색상 매핑(黑色→블랙)은 **D3 용어집 재사용**, 미매핑은 보류.

볼트 원칙과 같은 말이다 — **「모르면 올리지 않는다」**(옵션가·통화·이미지 폴백 사고의 공통 뿌리).

## 볼트가 준 사실 하나 더 — 속성은 **3개까지**

[[쿠팡 API 지뢰]] 「옵션 속성은 축이 아니라 개수가 3개 제한이다」(2026-09-20, 카테고리 78293 실측):
`len(attributes) > 3`이면 「카테고리는 최대 3개까지 옵션생성이 가능합니다」로 거부된다.
그래서 택1을 적용한 뒤에도 **3개를 넘으면 보류**한다(보내 봐야 거부다).

## 발명 금지

- 메타 필드 이름은 **이미 이 레포가 실응답에서 읽고 있는 것**만 쓴다(`attributeTypeName`·`required`·
  `exposed`·`dataType`·`basicUnit`·`usableUnits` — `CoupangUploader.get_category_attribute_schema`).
  `groupNumber`는 볼트의 실측 메타 로그(`grp=1`·`grp=NONE`)에 있다.
- 옵션 **이름** 매핑 표는 만들지 않는다 — 메타의 이름과 **같을 때만**(공백만 무시) 옵션으로 본다.
- 색상 **값** 매핑은 D3 용어집(`image_bench_axes.IDIOMS`의 `ko`)만 쓴다. 표에 없는 한자 색상은 보류.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional

#: 볼트 실측(카테고리 78293) — attributes 배열 길이 제한.
MAX_ATTRIBUTES = 3

_CJK = re.compile(r"[㐀-䶿一-鿿]")
_PURE_NUMBER = re.compile(r"^\d+(?:\.\d+)?$")
_REQUIRED_WORDS = ("MANDATORY", "REQUIRED", "TRUE", "Y", "필수")


def _norm(s) -> str:
    return re.sub(r"\s+", "", str(s or ""))


def _group(v) -> str:
    """`groupNumber` — 숫자면 그룹, `NONE`·빈 값이면 그룹 없음(빈 문자열)."""
    s = str(v if v is not None else "").strip()
    if not s or s.upper() == "NONE":
        return ""
    return s


def _opt_values(o: Dict) -> List[str]:
    """옵션 값 — `values`(목록, 수집기 정본) 또는 `value`(단수, 편집기 `_initOptions`도 받는 모양)."""
    vals = o.get("values")
    if vals is None and o.get("value") is not None:
        vals = [o.get("value")]
    if isinstance(vals, str):
        vals = vals.split(",")
    return [str(v).strip() for v in (vals or []) if str(v).strip()]


def parse_meta(raw_attrs) -> List[Dict]:
    """카테고리 메타 `attributes[]` 원문 → 계획에 쓰는 모양. 응답에 있는 것만."""
    out = []
    for a in raw_attrs or []:
        if not isinstance(a, dict):
            continue
        name = str(a.get("attributeTypeName") or "").strip()
        if not name:
            continue
        req = str(a.get("required") or "").strip().upper()
        out.append({
            "attributeTypeName": name,
            "required": req in _REQUIRED_WORDS,
            "exposed": str(a.get("exposed") or "").strip(),
            "dataType": str(a.get("dataType") or "").strip().upper(),
            "basicUnit": str(a.get("basicUnit") or "").strip(),
            "usableUnits": [str(u).strip() for u in (a.get("usableUnits") or []) if str(u or "").strip()],
            "group": _group(a.get("groupNumber")),
        })
    return out


def color_ko(value: str) -> str:
    """한자 색상값 → 정본 한국어. **D3 용어집만** 본다. 없으면 빈 문자열(= 보류)."""
    from src.services.image_text_glossary import glossary_line
    return glossary_line(value)


def _number_value(raw: str, entry: Dict) -> tuple:
    """NUMBER 속성 값 — `(값, 사유)`. 단위는 **메타의 usableUnits**에서만 고른다.

    basicUnit이 허용 목록에 있으면 그것, 아니면 허용 목록 첫 단위. 목록이 없으면 basicUnit.
    둘 다 없으면 단위를 붙이지 않는다(지어내지 않는다).
    """
    v = str(raw or "").strip()
    units = entry.get("usableUnits") or []
    basic = entry.get("basicUnit") or ""
    m = re.match(r"^(\d+(?:\.\d+)?)\s*(.*)$", v)
    if not m:
        return "", f"숫자가 아닙니다({v!r})"
    num, tail = m.group(1), m.group(2).strip()
    if tail:
        if units and tail not in units:
            return "", f"허용 밖 단위 {tail!r}(허용 {'/'.join(units)})"
        return f"{num}{tail}", ""
    unit = basic if (basic and (not units or basic in units)) else (units[0] if units else basic)
    return f"{num}{unit}", ""


def _value_for(entry: Dict, product: Dict) -> tuple:
    """이 필수 속성의 **실값** — `(값, 출처, 보류사유)`. 못 찾으면 값은 빈 문자열."""
    name = entry["attributeTypeName"]
    key = _norm(name)
    # ① 상품이 명시적으로 준 속성(수집·편집)
    for a in product.get("attributes") or []:
        if isinstance(a, dict) and _norm(a.get("attributeTypeName")) == key:
            v = str(a.get("attributeValueName") or "").strip()
            if v:
                return v, "상품 속성", ""
    # ② 옵션 — 이름이 메타와 **같을 때만**
    for o in product.get("options") or []:
        if not isinstance(o, dict) or _norm(o.get("name")) != key:
            continue
        vals = _opt_values(o)
        if len(vals) > 1:
            return "", "", (f"「{name}」 값이 {len(vals)}개입니다 — 여러 옵션 등록은 "
                            "SKU별 가격이 필요합니다(지금은 한 값만 남겨 주세요)")
        if vals:
            return vals[0], "옵션", ""
    # ③ 수량 — 단일 아이템이면 사실이다(1개)
    if "수량" in name or "개수" in name:
        return "1", "단일 아이템", ""
    return "", "", ""


def plan_attributes(raw_meta_attrs, product: Dict, *, meta_ok: bool = True) -> Dict:
    """전송할 `attributes`와 **보류 사유**를 정한다.

    반환: `{attributes, holds, notes, search_extra}`
      - `holds`가 비어 있지 않으면 **전송하지 않는다**(사전검증·등록 둘 다 같은 판정).
      - `search_extra`: 옵션으로 못 보낸 원 옵션 값 — 검색어로만 쓴다.
    """
    holds, notes, search_extra = [], [], []
    if not meta_ok:
        return {"attributes": [], "holds": ["카테고리 메타를 읽지 못했습니다 — 옵션 규칙을 확인할 수 없어 보류"],
                "notes": [], "search_extra": []}
    meta = parse_meta(raw_meta_attrs)
    names = {_norm(m["attributeTypeName"]) for m in meta}

    # 메타에 없는 옵션 이름 → 옵션으로 보내지 않는다(자유옵션은 노출 제한). 값은 검색어로만.
    for o in product.get("options") or []:
        if isinstance(o, dict) and o.get("name") and _norm(o["name"]) not in names:
            vals = _opt_values(o)
            search_extra += vals
            notes.append(f"옵션 「{o['name']}」은 이 카테고리 메타에 없어 옵션으로 보내지 않습니다(검색어로만)")

    # gtin(바코드 계열)은 **보내지 않는다** — 옛 정본(5,691건)이 그랬고, 바코드는
    #   `emptyBarcode=True` + 사유로 따로 말한다. 필수여도 옵션 칸의 일이 아니다.
    required = [m for m in meta if m["required"] and "gtin" not in m["attributeTypeName"].lower()]
    # groupNumber 택1 — 같은 그룹의 필수 속성은 **하나만** 채운다.
    by_group: Dict[str, List[Dict]] = {}
    singles = []
    for m in required:
        (by_group.setdefault(m["group"], []) if m["group"] else singles).append(m)

    chosen = []
    for m in singles:
        chosen.append((m, _value_for(m, product)))
    for g, members in by_group.items():
        pick = None
        for m in members:
            got = _value_for(m, product)
            if got[0]:
                pick = (m, got)
                break
        if pick is None:
            # 그룹 안에서 하나도 못 채웠다 — 무엇 중 하나가 필요한지 말한다.
            reasons = [r for _m in members for r in [_value_for(_m, product)[2]] if r]
            holds.append("필수 옵션(택1): " + " 또는 ".join(x["attributeTypeName"] for x in members)
                         + (f" — {reasons[0]}" if reasons else ""))
        else:
            chosen.append(pick)

    attributes, missing = [], []
    for m, (value, source, why) in chosen:
        name = m["attributeTypeName"]
        if why:
            holds.append(why)
            continue
        if not value:
            missing.append(name)
            continue
        if "색상" in name and _CJK.search(value):
            ko = color_ko(value)
            if not ko:
                holds.append(f"색상 미매핑: {value} — D3 용어집에 정본을 추가해야 보낼 수 있습니다")
                continue
            value = ko
        if m["dataType"] == "NUMBER" or _PURE_NUMBER.match(value):
            if m["dataType"] == "NUMBER" or m["basicUnit"] or m["usableUnits"]:
                value, why_n = _number_value(value, m)
                if why_n:
                    holds.append(f"「{name}」 {why_n}")
                    continue
        item = {"attributeTypeName": name, "attributeValueName": value[:28]}
        if m["exposed"]:
            item["exposed"] = m["exposed"]
        attributes.append(item)
    if missing:
        holds.insert(0, "필수 옵션: " + ", ".join(missing))
    if len(attributes) > MAX_ATTRIBUTES:
        holds.append(f"옵션 속성이 {len(attributes)}개입니다 — 쿠팡은 {MAX_ATTRIBUTES}개까지만 받습니다"
                     "(볼트 실측: 카테고리 78293)")
    return {"attributes": attributes, "holds": holds, "notes": notes, "search_extra": search_extra}


# ─────────────────────────────────────────────────────────────────────────────
# F48-c — 쿠팡 거부 문장을 **한 줄씩**
# ─────────────────────────────────────────────────────────────────────────────
#
# 실응답 한 벌(볼트 「조용한 실패」): `{"code":"ERROR","message":"유효하지 않은 ISBN 값이 존재합니다.|
# 유효하지 않은 구매 옵션 값이 존재합니다."}` — 두 사유가 **`|`로 붙어** 온다. 한 줄로 보이면
# 사람은 첫 문장만 읽는다. 오너 지시: `|`로 나누고, `errorItems[].itemAttributes[].message`도
# **그대로** 화면에(문서 응답 예시). 우리가 문장을 고쳐 쓰지 않는다.

def _json(body):
    import json
    if isinstance(body, dict):
        return body
    try:
        v = json.loads(str(body or ""))
        return v if isinstance(v, dict) else {}
    except Exception:
        return {}


def error_lines(body) -> List[str]:
    """거부 응답(본문 문자열 또는 dict) → 문장 목록. 못 읽으면 빈 목록(호출부가 원문 한 줄을 쓴다)."""
    js = _json(body)
    out: List[str] = []

    def _add(s):
        for part in str(s or "").split("|"):
            part = part.strip()
            if part and part not in out:
                out.append(part)

    _add(js.get("message"))
    for it in js.get("errorItems") or []:
        if not isinstance(it, dict):
            continue
        for ia in it.get("itemAttributes") or []:
            if isinstance(ia, dict):
                _add(ia.get("message"))
        _add(it.get("message"))
    return out
