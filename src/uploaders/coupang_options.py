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
    """한자 색상값 → 정본 한국어(용어집 정확 일치만). 없으면 빈 문자열."""
    from src.services.image_text_glossary import option_value_line
    return option_value_line(value)


def glossary_line_count() -> int:
    """옵션 값 섹션 정본 줄 수(후보 목록 화면이 「용어집 N줄」로 쓴다)."""
    from src.services import image_text_glossary as _g
    return len(_g.OPTION_VALUE_LINES)


# F51-b(오너 2026-09-27): **「색상은 용어집만」(F48-b)은 폐기.** 하루 10건 목표에 상품마다 값 10개를
#   손으로 용어집에 넣는 건 못 버틴다. 대신 순서를 정하고, 사람이 볼 값에는 배지를 단다:
#     0) 오너가 이 상품에서 고친 값(`option_value_overrides`) — 그대로
#     1) 용어집 정확 일치                       — 배지 없음
#     2) 용어집 토큰 치환(白色→화이트 …)         — 「번역기 값 — 확인」
#     3) 번역기 `values_ko`(브랜드·영문 토큰 보존) — 「번역기 값 — 확인」
#     4) 그래도 비면 보류(사유)
HOW_LABEL = {"override": "직접 수정", "glossary": "용어집", "token": "용어집 조각 치환",
             "polish": "정리 규칙", "translator": "번역기"}
_ASCII_TOK = re.compile(r"[A-Za-z0-9][A-Za-z0-9.+\-]*")


def value_ko_map(product: Dict) -> Dict[str, str]:
    """상품 옵션의 번역기 값 — `{원문 값: values_ko}`(번역 안 된 값은 빠진다)."""
    out: Dict[str, str] = {}
    for o in product.get("options") or []:
        if not isinstance(o, dict):
            continue
        vals, kos = list(o.get("values") or []), list(o.get("values_ko") or [])
        for i, v in enumerate(vals):
            sv = str(v.get("name") if isinstance(v, dict) else v or "").strip()
            if i < len(kos) and sv:
                out[sv] = str(kos[i] or "").strip()
    for key in ("option_values_ko", "_values_ko"):      # 편집 화면 본문 / 등록 경로(to_collected)
        extra = product.get(key)
        if isinstance(extra, dict):
            out.update({str(k): str(v) for k, v in extra.items() if str(v or "").strip()})
    return out


def resolve_option_value(value: str, *, values_ko: str = "", override: str = "") -> Dict:
    """한 값의 한국어 — `{value, how, confirm, why}`. `value`가 비면 보류(`why`가 사유)."""
    from src.services.image_text_glossary import option_value_tokens
    v = str(value or "").strip()
    if str(override or "").strip():
        return {"value": str(override).strip(), "how": "override", "confirm": False, "why": ""}
    if not _CJK.search(v):
        return {"value": v, "how": "", "confirm": False, "why": ""}
    g = color_ko(v)
    if g:
        return {"value": g, "how": "glossary", "confirm": False, "why": ""}
    t = option_value_tokens(v)
    if t:
        return {"value": t, "how": "token", "confirm": True, "why": ""}
    # T1/T2(오너 2026-09-30-H): 복합 값 `색상[소재]부속 접미사`를 조각별로 — 판촉 접미사(海外特供)는 지우고,
    #   소재·부속·색상은 규칙표(원격 JSON)로 옮긴 뒤 **쿠팡 28자에 맞춰 소재부터** 줄인다. 한자가 남으면 다음 단계.
    from src.collectors import ko_polish as _kp
    p = _kp.option_value(v)
    if p["value"]:
        return {"value": _kp.shorten(p["value"]), "how": "polish", "confirm": True, "why": ""}
    ko = _kp.polish_ko(str(values_ko or "").strip())
    if ko and len(ko) > _kp.MAX_OPTION_VALUE:
        ko = _kp.shorten(ko)
    if ko and ko != v and not _CJK.search(ko):
        lost = [tok for tok in _ASCII_TOK.findall(v) if tok.lower() not in ko.lower()]
        if not lost:
            return {"value": ko, "how": "translator", "confirm": True, "why": ""}
        return {"value": "", "how": "", "confirm": False,
                "why": f"번역기 값이 원문의 영문·숫자({', '.join(lost)})를 잃었습니다"}
    if ko and _CJK.search(ko):
        why = "번역기 값에 한자가 남았습니다"
    else:
        why = "용어집에도 번역기 값에도 없습니다 — 한국어 번역을 먼저 돌리거나 값을 직접 넣어 주세요"
    return {"value": "", "how": "", "confirm": False, "why": why}


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
    # ④ F48-d: 적용모델(자유 텍스트) — 제목의 **영문+숫자 모델 토큰**(applewatch7/9·S8·Ultra2)으로 선채움.
    #   화면이 「제목에서 추출 — 확인」 배지를 단다. 토큰이 없으면 빈칸(= 보류) 그대로.
    if key.replace(" ", "") == "적용모델" and entry.get("dataType") != "NUMBER":
        toks = model_tokens(product.get("title_original") or product.get("title") or "")
        if toks:
            return ", ".join(toks)[:28], MODEL_SOURCE, ""
    return "", "", ""


MODEL_SOURCE = "제목에서 추출"
_MODEL_TOK = re.compile(r"[A-Za-z0-9][A-Za-z0-9/.\-]*")


def model_tokens(title: str) -> List[str]:
    """제목의 모델 토큰 — 영문과 숫자가 **둘 다** 든 ASCII 토큰만(브랜드·일반 영단어는 제외)."""
    out: List[str] = []
    for t in _MODEL_TOK.findall(str(title or "")):
        t = t.strip("/.-")
        if re.search(r"[A-Za-z]", t) and re.search(r"\d", t) and t not in out:
            out.append(t)
    return out


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
    # F51-b-3: 옵션 이름도 해석 순서(오너 수정 → 용어집 → 번역기)로 메타 이름표를 단 사본으로 본다.
    product = with_meta_names(product, [m["attributeTypeName"] for m in meta])

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

    attributes, missing, resolved = [], [], []
    for m, (value, source, why) in chosen:
        name = m["attributeTypeName"]
        if why:
            holds.append(why)
            continue
        if not value:
            missing.append(name)
            continue
        if _CJK.search(value) and ("색상" in name or source == "옵션"):
            # F51-b: 해석 순서(오너 수정 → 용어집 → 조각 치환 → 번역기) — 한 곳(`resolve_option_value`).
            _ov = product.get("option_value_overrides") if isinstance(product.get("option_value_overrides"), dict) else {}
            r = resolve_option_value(value, values_ko=value_ko_map(product).get(value, ""),
                                     override=_ov.get(value, ""))
            if not r["value"]:
                holds.append(f"옵션 값 미해석: {value} — {r['why']}")
                continue
            if r["how"]:
                resolved.append({"name": name, "orig": value, "value": r["value"][:28], "how": r["how"],
                                 "how_label": HOW_LABEL.get(r["how"], r["how"]), "confirm": r["confirm"]})
            value = r["value"]
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
    return {"attributes": attributes, "holds": holds, "notes": notes, "search_extra": search_extra,
            "resolved": resolved}


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
OPTION_NAME_GLOSSARY = {"颜色分类": "색상", "商品规格": "규격", "尺码": "사이즈", "款式": "종류"}   # F51-b-3


def names_ko_map(product: Dict) -> Dict[str, str]:
    """옵션 이름의 번역기 값 — `{원문 이름: name_ko}`(번역기 `translate_options`가 남긴 것)."""
    out: Dict[str, str] = {}
    for o in product.get("options") or []:
        if isinstance(o, dict) and o.get("name") and str(o.get("name_ko") or "").strip():
            out[str(o["name"]).strip()] = str(o["name_ko"]).strip()
    for key in ("option_names_ko", "_names_ko"):
        extra = product.get(key)
        if isinstance(extra, dict):
            out.update({str(k): str(v) for k, v in extra.items() if str(v or "").strip()})
    return out


def resolve_option_name(name: str, meta_names, *, name_ko: str = "", override: str = "") -> Dict:
    """F51-b-3: 옵션 **이름** → 카테고리 메타 속성명. 순서 = 오너 수정 → 같은 이름 → 용어집 → 번역기 → 보류.

    `{meta, how, candidate, why}` — `meta`가 비면 보류. `candidate`는 용어집·번역기가 낸 한국어(메타엔 없음).
    """
    from src.collectors.ko_polish import MAX_OPTION_NAME
    # K-0: 쿠팡 attributeTypeName 25자 — 넘는 이름은 **자르지 않고** 후보에서 뺀다(보류 → 「미해석」).
    names = {_norm(n): n for n in meta_names if len(str(n or "")) <= MAX_OPTION_NAME}
    long_names = [n for n in meta_names if len(str(n or "")) > MAX_OPTION_NAME]
    nm = str(name or "").strip()
    ov = str(override or "").strip()
    if ov:
        if _norm(ov) in names:
            return {"meta": names[_norm(ov)], "how": "override", "candidate": ov, "why": ""}
    if _norm(nm) in names:
        return {"meta": names[_norm(nm)], "how": "", "candidate": nm, "why": ""}
    g = OPTION_NAME_GLOSSARY.get(nm, "")
    if g and _norm(g) in names:
        return {"meta": names[_norm(g)], "how": "glossary", "candidate": g, "why": ""}
    ko = str(name_ko or "").strip()
    if ko and ko != nm and _norm(ko) in names:
        return {"meta": names[_norm(ko)], "how": "translator", "candidate": ko, "why": ""}
    cand = g or (ko if ko != nm else "")
    too_long = [n for n in long_names if _norm(n) in {_norm(x) for x in (ov, nm, g, ko) if x}]
    if too_long:
        return {"meta": "", "how": "", "candidate": cand,
                "why": f"옵션 이름 미해석 — 「{too_long[0]}」이 쿠팡 옵션명 한도 {MAX_OPTION_NAME}자를 넘습니다(자르지 않음). "
                       "다른 메타 속성을 골라 주세요"}
    return {"meta": "", "how": "", "candidate": cand,
            "why": (f"옵션 「{nm}」" + (f"(→{cand})" if cand else "")
                    + "이 이 카테고리 메타 속성에 없어 SKU별로 나눌 수 없습니다 — 메타 속성 중에서 골라 주세요")}


def _name_ctx(product: Dict) -> tuple:
    ov = product.get("option_name_overrides") if isinstance(product.get("option_name_overrides"), dict) else {}
    return names_ko_map(product), ov


def option_name_for_meta(name: str, meta_names, product: Optional[Dict] = None) -> str:
    """상품 옵션 이름 → 메타 이름(해석 순서 `resolve_option_name`). 못 찾으면 빈 문자열."""
    kos, ov = _name_ctx(product or {})
    nm = str(name or "").strip()
    return resolve_option_name(nm, meta_names, name_ko=kos.get(nm, ""), override=ov.get(nm, ""))["meta"]


def with_meta_names(product: Dict, meta_names) -> Dict:
    """옵션 이름을 해석된 메타 이름으로 바꾼 사본 — 단일 등록 계획이 같은 이름표를 본다."""
    out = dict(product)
    opts = []
    for o in product.get("options") or []:
        if isinstance(o, dict) and o.get("name"):
            m = option_name_for_meta(o["name"], meta_names, product)
            opts.append({**o, "name": m} if m else o)
        else:
            opts.append(o)
    out["options"] = opts
    return out


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
    mapped, name_picks = [], []
    kos, ov = _name_ctx(product)
    for o in axes:
        nm = str(o["name"]).strip()
        r = resolve_option_name(nm, meta_names, name_ko=kos.get(nm, ""), override=ov.get(nm, ""))
        if not r["meta"]:
            holds.append(r["why"])
            # 오너가 고를 목록 — 이 카테고리 메타 속성명 전부(드롭다운).
            name_picks.append({"orig": nm, "candidate": r["candidate"], "choices": list(meta_names)})
        mapped.append(r["meta"])
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
        # F51-b: 번역기 값·오너 수정은 **원 옵션**에 붙어 있다 — 값 1개짜리로 줄인 뒤에도 찾게 넘긴다.
        one["_values_ko"] = value_ko_map(product)
        # 축 속성(예: 색상)에 한 값을 쳐 두었으면 SKU 모드에선 쓰지 않는다 — 그 값이 모든 SKU를 덮으면
        #   10개가 같은 옵션이 된다. 값은 SKU마다 그 SKU의 옵션 값에서 나온다.
        axis_names = {_norm(n) for n in mapped if n}
        one["attributes"] = [a for a in (product.get("attributes") or [])
                             if isinstance(a, dict) and _norm(a.get("attributeTypeName")) not in axis_names]
        plan = plan_attributes(raw_meta_attrs, one, meta_ok=True)
        for h in plan["holds"]:
            if h.startswith("옵션 값 미해석: "):
                unmapped.append(h[len("옵션 값 미해석: "):].split(" — ")[0])
            elif h not in holds:
                holds.append(h)
        for n in plan["notes"]:
            if n not in notes:
                notes.append(n)
        search_extra += [x for x in plan["search_extra"] if x not in search_extra]
        label = " / ".join(a["attributeValueName"] for a in plan["attributes"]
                           if _norm(a["attributeTypeName"]) in axis_names)
        items.append({"sku_id": str(k.get("sku_id") or ""), "spec": spec, "label": label,
                      "attributes": plan["attributes"], "sell_price_krw": k.get("sell_price_krw"),
                      "cost": k.get("price"), "currency": k.get("currency") or "",
                      "stock": k.get("stock"), "image": k.get("image") or "",
                      "resolved": plan.get("resolved") or [],
                      "confirm": any(r.get("confirm") for r in (plan.get("resolved") or []))})
    # F51-b 3: 번역 결과가 SKU끼리 같아지면 **원문 차이 부분**을 옮겨 붙여 유일하게(「블랙」 vs 「블랙 선정리형」).
    #   그래도 같으면 보류 + 사유. 축 값이 안 들어간 SKU(미해석으로 이미 보류)는 비교하지 않는다 —
    #   공통 속성(수량)만 남아 전부 같아 보이는 것은 「같은 옵션」이 아니다(F51 캡처: 9줄 거짓 보류).
    holds += _dedupe_axis_values(items, axis_names)
    if unmapped:
        holds.append(f"옵션 값 {len(unmapped)}개를 한국어로 옮기지 못했습니다 — 값을 직접 넣거나 번역을 먼저 돌려 주세요: "
                     + ", ".join(unmapped))
    return {"multi": True, "items": items, "holds": holds, "notes": notes, "search_extra": search_extra,
            "name_picks": name_picks,
            "axis_names": [{"orig": o["name"], "meta": mapped[i]} for i, o in enumerate(axes)]}


def _common_affix(strs: List[str]) -> tuple:
    a = min(len(x) for x in strs)
    p = 0
    while p < a and all(x[p] == strs[0][p] for x in strs):
        p += 1
    q = 0
    while q < a - p and all(x[len(x) - 1 - q] == strs[0][len(strs[0]) - 1 - q] for x in strs):
        q += 1
    return p, q


def _dedupe_axis_values(items: List[Dict], axis_names: set) -> List[str]:
    """같은 축 값이 된 SKU들 — 원문 차이를 한국어로 붙여 가른다. 못 가르면 보류 문장을 돌려준다."""
    from src.services.image_text_glossary import option_value_line, option_value_tokens
    holds: List[str] = []

    def _key(it):
        return tuple((a["attributeTypeName"], a["attributeValueName"]) for a in it["attributes"])

    def _has_axis(it):
        return any(_norm(a["attributeTypeName"]) in axis_names for a in it["attributes"])

    groups: Dict[tuple, List[Dict]] = {}
    for it in items:
        if _has_axis(it):
            groups.setdefault(_key(it), []).append(it)
    for key, grp in groups.items():
        if len(grp) < 2:
            continue
        origs = ["".join(it["spec"]) for it in grp]
        p, q = _common_affix(origs)
        fixed = True
        for it, o in zip(grp, origs):
            diff = o[p:len(o) - q].strip("（）() ")
            if not diff:
                continue
            ko = option_value_line(diff) or option_value_tokens(diff)
            if not ko:
                fixed = False
                break
            for a in it["attributes"]:
                if _norm(a["attributeTypeName"]) in axis_names:
                    a["attributeValueName"] = (a["attributeValueName"] + " " + ko)[:28]
                    break
            it["label"] = " / ".join(a["attributeValueName"] for a in it["attributes"]
                                     if _norm(a["attributeTypeName"]) in axis_names)
            it["confirm"] = True
            it.setdefault("resolved", []).append({"orig": diff, "value": ko, "how": "token",
                                                  "how_label": "원문 차이 붙임", "confirm": True})
        keys = [_key(it) for it in grp]
        if not fixed or len(set(keys)) < len(keys):
            specs = " · ".join("「" + " / ".join(it["spec"]) + "」" for it in grp)
            holds.append(f"옵션 값이 같아집니다({grp[0]['label']}): {specs}"
                         " — 원문 차이를 한국어로 옮기지 못해 보류합니다(값을 직접 고쳐 주세요)")
    return holds


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
    _meta_names = [x["attributeTypeName"] for x in parse_meta(raw_meta_attrs)]
    named = with_meta_names(product, _meta_names)
    fields = []
    for m in parse_meta(raw_meta_attrs):
        if not m["required"] or "gtin" in m["attributeTypeName"].lower():
            continue
        value, source, why = _value_for(m, named)
        if plan.get("multi"):
            axis = {_norm(option_name_for_meta(o.get("name"), _meta_names, product))
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
            "multi": bool(plan.get("multi")), "items": plan.get("items") or [],
            # F51-b-3: 메타에 없는 축 이름 — 오너가 메타 속성명에서 고를 목록(드롭다운).
            "name_picks": plan.get("name_picks") or [],
            # F51-b: 단일 등록에서도 해석된 값(배지·인라인 수정 재료)
            "resolved": plan.get("resolved") or [],
            # F51-b 6: SKU별 판매가에 쓴 환율(값·출처·갱신 시각) — `with_sku_prices`가 붙인다.
            "fx": product.get("fx_info") or None}


def common_value_tokens(values) -> list:
    """F53 — 옵션 원문 **전부에 공통**인 용어집 토큰의 한국어 표기(값이 2개 이상일 때만).

    쿠팡 상품명의 「핵심 속성」 재료다(三合一 → 3in1). 색상처럼 SKU마다 갈리는 값은 공통이 아니라 안 온다.
    D3 용어집은 **이 파일 한 곳에서만** 표로 읽는다(`test_d3_3b` — 렌더·번역 파이프 연결 0).
    """
    vals = [str(v) for v in (values or []) if str(v).strip()]
    if len(vals) < 2:
        return []
    from src.services import image_text_glossary as _g
    out = []
    for src, ko in _g.OPTION_VALUE_TOKENS.items():
        if all(src in v for v in vals) and ko not in out:
            out.append(ko)
    return out
