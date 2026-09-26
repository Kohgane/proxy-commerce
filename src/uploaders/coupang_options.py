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
# F51 — SKU별 다중 등록(오너 결정 2026-09-26: 연다)
# ─────────────────────────────────────────────────────────────────────────────
#
# F48-c는 「색상 값이 13개 — 여러 옵션 등록은 SKU별 가격이 필요합니다」로 **보류**했다. 이제 SKU별 가격이
# 있으면(ICE 컨텍스트 — F49-T 2부) 그 보류를 풀고 `items[]`를 SKU 수만큼 만든다.
#
# 규칙(오너 F51):
#   1. SKU마다 item — 옵션명은 **용어집으로** 메타 이름에 맞춘다(颜色分类 → 색상). 원가 = 그 SKU 가격,
#      재고 = quantity, 대표 이미지 = 그 값의 이미지. **재고 0은 뺀다(사유 표시).**
#   2. 보류 해제는 **SKU가 있고 재고 있는 SKU 전부에 SKU별 판매가가 있을 때만.** 아니면 지금 문구 그대로.
#   3. 판매가는 SKU 원가로 **각각** 낸다(식은 `calc_sell_price` 하나 — 호출부가 채워 온다).
#      속성 3개 제한(볼트 지뢰)·색상 값 용어집 규칙(F48-b)은 **SKU마다 그대로** 적용된다.
#   5. 이 트랙은 쿠팡만.

#: 옵션 **이름** 용어집 — 메타의 attributeTypeName으로. 오너가 지정한 것만(F51, 2026-09-26).
#:   값(색상 한자 → 한국어)은 여기가 아니라 D3 용어집(`color_ko`)이다(F48-b 규칙 그대로).
OPTION_NAME_GLOSSARY = {"颜色分类": "색상"}


def option_name_for_meta(name: str, meta_names) -> str:
    """상품 옵션 이름 → 메타 이름. 같으면 그대로, 용어집에 있으면 그 이름, 아니면 빈 문자열."""
    names = {_norm(n): n for n in meta_names}
    if _norm(name) in names:
        return names[_norm(name)]
    g = OPTION_NAME_GLOSSARY.get(str(name or "").strip())
    if g and _norm(g) in names:
        return names[_norm(g)]
    return ""


def _sku_list(product: Dict) -> List[Dict]:
    return [k for k in (product.get("skus") or []) if isinstance(k, dict) and k.get("spec")]


def sku_mode(product: Dict) -> tuple:
    """`(쓸 수 있나, 재고 있는 SKU, 재고 0 SKU, 사유)` — F51 규칙 2의 판정 한 곳."""
    skus = _sku_list(product)
    if not skus:
        return False, [], [], "SKU 없음"
    zero = [k for k in skus if k.get("stock") == 0]
    live = [k for k in skus if k.get("stock") != 0]
    if not live:
        return False, [], zero, "재고 있는 SKU가 없습니다"
    no_price = [k for k in live if not (_as_float(k.get("sell_price_krw")) > 0)]
    if no_price:
        return False, live, zero, f"SKU별 판매가가 없는 SKU {len(no_price)}개"
    return True, live, zero, ""


def _as_float(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def plan_sku_items(raw_meta_attrs, product: Dict, *, meta_ok: bool = True) -> Dict:
    """SKU마다 `plan_attributes`를 돌려 item 계획을 만든다 — `{multi, items, holds, notes, search_extra}`."""
    ok, live, zero, why = sku_mode(product)
    if not ok:
        return {"multi": False, "why": why}
    if not meta_ok:
        return {"multi": True, "items": [], "holds": ["카테고리 메타를 읽지 못했습니다 — 옵션 규칙을 확인할 수 없어 보류"],
                "notes": [], "search_extra": []}
    meta = parse_meta(raw_meta_attrs)
    meta_names = [m["attributeTypeName"] for m in meta]
    axes = [o for o in (product.get("options") or []) if isinstance(o, dict) and o.get("name")]
    holds, notes, search_extra = [], [], []
    mapped = []
    for o in axes:
        m = option_name_for_meta(o["name"], meta_names)
        if not m:
            holds.append(f"옵션 「{o['name']}」이 이 카테고리 메타에 없어 SKU별로 나눌 수 없습니다"
                         " — 옵션 이름 용어집에 정본을 추가해야 합니다")
        mapped.append(m)
    if zero:
        notes.append("재고 0이라 등록에서 뺀 SKU " + str(len(zero)) + "개: "
                     + ", ".join(" / ".join(k["spec"]) for k in zero))
    items, unmapped, seen = [], [], {}
    for k in live:
        spec = list(k.get("spec") or [])
        # 이 SKU 하나만 가진 상품으로 바꿔 **기존 규칙 그대로** 돌린다(값 1개 → 「값이 N개」 보류 없음).
        one = dict(product)
        one["options"] = [{"name": (mapped[i] or axes[i]["name"]), "values": [spec[i]]}
                          for i in range(min(len(axes), len(spec)))]
        one.pop("skus", None)
        # 축 속성(예: 색상)에 한 값을 쳐 두었으면 SKU 모드에선 쓰지 않는다 — 그 값이 모든 SKU를 덮으면
        #   10개가 같은 옵션이 된다. 값은 SKU마다 그 SKU의 옵션 값에서 나온다.
        axis_names = {_norm(n) for n in mapped if n}
        one["attributes"] = [a for a in (product.get("attributes") or [])
                             if isinstance(a, dict) and _norm(a.get("attributeTypeName")) not in axis_names]
        plan = plan_attributes(raw_meta_attrs, one, meta_ok=True)
        for h in plan["holds"]:
            if h.startswith("색상 미매핑: "):
                unmapped.append(h[len("색상 미매핑: "):].split(" — ")[0])
            elif h not in holds:
                holds.append(h)
        for n in plan["notes"]:
            if n not in notes:
                notes.append(n)
        search_extra += [x for x in plan["search_extra"] if x not in search_extra]
        key = tuple((a["attributeTypeName"], a["attributeValueName"]) for a in plan["attributes"])
        # 축 값이 안 들어간 SKU(미매핑으로 이미 보류)는 비교하지 않는다 — 공통 속성(수량)만 남아
        #   전부 같아 보이는 것은 「같은 옵션」이 아니다(캡처에서 발견: 9줄 거짓 보류).
        has_axis = any(_norm(a["attributeTypeName"]) in axis_names for a in plan["attributes"])
        if has_axis and key in seen:
            holds.append(f"SKU 「{' / '.join(spec)}」와 「{seen[key]}」의 옵션 값이 같습니다 — 쿠팡은 같은 옵션을 두 번 받지 않습니다")
        if has_axis:
            seen[key] = " / ".join(spec)
        label = " / ".join(a["attributeValueName"] for a in plan["attributes"]
                           if _norm(a["attributeTypeName"]) in axis_names)
        items.append({"sku_id": str(k.get("sku_id") or ""), "spec": spec, "label": label,
                      "attributes": plan["attributes"], "sell_price_krw": k.get("sell_price_krw"),
                      "cost": k.get("price"), "currency": k.get("currency") or "",
                      "stock": k.get("stock"), "image": k.get("image") or ""})
    if unmapped:
        holds.append(f"색상 값 {len(unmapped)}개가 용어집에 없습니다 — 정본 한국어가 있어야 보낼 수 있습니다: "
                     + ", ".join(unmapped))
    return {"multi": True, "items": items, "holds": holds, "notes": notes, "search_extra": search_extra}


def plan_for(raw_meta_attrs, product: Dict, *, meta_ok: bool = True) -> Dict:
    """**사전검증·등록·편집 블록이 같이 부르는** 계획 — SKU 모드면 `plan_sku_items`, 아니면 `plan_attributes`."""
    multi = plan_sku_items(raw_meta_attrs, product, meta_ok=meta_ok)
    if multi.get("multi"):
        attrs = multi["items"][0]["attributes"] if multi.get("items") else []
        return {**multi, "attributes": attrs}
    single = plan_attributes(raw_meta_attrs, product, meta_ok=meta_ok)
    return {**single, "multi": False, "items": [], "sku_why": multi.get("why", "")}


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


# ─────────────────────────────────────────────────────────────────────────────
# F48-c — 오너가 화면에서 **직접 정한 값**을 계획에 싣는다
# ─────────────────────────────────────────────────────────────────────────────
#
# 보류 둘을 사람이 풀 수 있어야 한다(오너 2026-09-26):
#   · 「필수 옵션: 적용모델」 — 메타의 MANDATORY 칸에 **오너가 넣은 값만** 싣는다(기본값 채우기 0).
#   · 「색상 값이 13개」 — 목록에서 **하나를 고르면** 그 값만 남겨 단일 SKU로 간다.
#     고른 값은 **원래 목록에 있던 값**이어야 한다(목록 밖 값은 무시 — 지어낸 값이 옵션이 되지 않게).

def apply_choices(product: Dict, attributes=None, pick=None) -> Dict:
    """상품 사본에 오너 선택을 반영한다 — `{attributes: 입력값 우선 병합, options: 고른 값만}`."""
    out = dict(product or {})
    typed = []
    for a in attributes or []:
        if not isinstance(a, dict):
            continue
        name = str(a.get("attributeTypeName") or "").strip()
        value = str(a.get("attributeValueName") or "").strip()
        if name and value:
            typed.append({"attributeTypeName": name, "attributeValueName": value})
    if typed:
        keep = [a for a in (out.get("attributes") or [])
                if isinstance(a, dict) and _norm(a.get("attributeTypeName"))
                not in {_norm(t["attributeTypeName"]) for t in typed}]
        out["attributes"] = typed + keep
    if isinstance(pick, dict) and pick:
        opts, picked = [], []
        for o in out.get("options") or []:
            if not isinstance(o, dict):
                opts.append(o)
                continue
            chosen = str(pick.get(o.get("name")) or "").strip()
            vals = _opt_values(o)
            if chosen and chosen in vals:
                o = {**o, "values": [chosen]}
                o.pop("value", None)
                picked.append(chosen)
            opts.append(o)
        out["options"] = opts
        # F51: 하나를 골랐으면 **그 SKU만** 남긴다 — 고른 뜻은 단일 SKU다(다중 등록으로 되살아나지 않게).
        if picked and isinstance(out.get("skus"), list):
            out["skus"] = [k for k in out["skus"] if isinstance(k, dict)
                           and all(v in (k.get("spec") or []) for v in picked)]
    return out


def option_form(raw_meta_attrs, product: Dict, *, meta_ok: bool = True,
                choices_from: Optional[Dict] = None) -> Dict:
    """편집 화면 「쿠팡 필수 옵션」 블록의 재료 — 메타 **그대로** + 지금 계획이 보는 값·보류.

    `fields`: MANDATORY 속성마다 `{name, dataType, basicUnit, usableUnits, group, exposed, value, source}`
    — `value`는 **계획이 실제로 찾은 값**(상품 속성·같은 이름 옵션·단일 아이템 수량)뿐이다. 없으면 빈칸.
    `choices`: 값이 2개 이상인 옵션 — 오너가 하나를 고를 목록.
    """
    plan = plan_for(raw_meta_attrs, product, meta_ok=meta_ok)
    fields = []
    for m in parse_meta(raw_meta_attrs):
        if not m["required"] or "gtin" in m["attributeTypeName"].lower():
            continue
        value, source, why = _value_for(m, product)
        if plan.get("multi"):
            axis = {_norm(option_name_for_meta(o.get("name"), [x["attributeTypeName"] for x in parse_meta(raw_meta_attrs)]))
                    for o in product.get("options") or [] if isinstance(o, dict)}
            if _norm(m["attributeTypeName"]) in axis:
                # F51: 이 칸은 SKU마다 다른 값으로 나간다 — 「값이 N개」 보류 문구를 여기 두지 않는다.
                value, source, why = f"SKU별 {len(plan.get('items') or [])}개", "SKU", ""
        fields.append({"name": m["attributeTypeName"], "dataType": m["dataType"],
                       "basicUnit": m["basicUnit"], "usableUnits": m["usableUnits"],
                       "group": m["group"], "exposed": m["exposed"],
                       "value": value, "source": source, "why": why})
    names = {_norm(m["attributeTypeName"]) for m in parse_meta(raw_meta_attrs)}
    choices = []
    # 고를 목록은 **고르기 전** 옵션에서 — 고른 뒤 목록이 사라지면 다시 고를 수가 없다(캡처에서 발견).
    for o in (choices_from or product).get("options") or []:
        if isinstance(o, dict) and o.get("name"):
            vals = _opt_values(o)
            if len(vals) > 1:
                choices.append({"name": o["name"], "values": vals, "in_meta": _norm(o["name"]) in names})
    if plan.get("multi"):
        # F51: SKU별로 나가면 「하나 고르기」는 필요 없다(고르면 오히려 단일 SKU로 줄어든다).
        choices = []
    return {"fields": fields, "choices": choices, "holds": plan["holds"], "notes": plan["notes"],
            "attributes": plan["attributes"], "meta_ok": meta_ok,
            "multi": bool(plan.get("multi")), "items": plan.get("items") or []}
