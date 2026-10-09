"""Y7(오너 2026-10-08) — 네이버 커머스 조합형 옵션(`detailAttribute.optionInfo`).

예전엔 네이버 등록 몸통에 옵션 칸이 없었다 — SKU가 8개인 상품도 **한 가격·한 재고**로 올라갔다.
이제 신규 등록(`POST /v2/products`)에 조합형 옵션을 싣는다. 수정(`update_product`)은 건드리지 않는다.

스키마(커머스API 원상품 정보 구조체, Context7 `/websites/apicenter_commerce_naver` 대조):
  optionInfo = {
    optionCombinationSortType: CREATE,
    optionCombinationGroupNames: {optionGroupName1, optionGroupName2},
    optionCombinations: [{optionName1, optionName2, stockQuantity, price, sellerManagerCode, usable}],
    useStockManagement: true,
  }
  · price = **판매가 대비 옵션 추가금**(정수, 0 이상으로 맞춘다 — 판매가를 가장 싼 조합으로 둔다).
  · stockQuantity ≤ 99,999,999.
  · 조합형 그룹은 문서상 최대 3개 — 오너 스펙은 **2축까지**.
  · 단독형(optionSimple)과 조합형은 같이 못 쓴다 — 우리는 조합형만 쓴다.

값은 `option_ko`(= 쿠팡 SKU와 같은 `resolve_option_value` 한 사슬)에서 온다 — 두 마켓 옵션 값이 갈리지 않는다.

★ 조합 수 상한: **공식 API 문서에 숫자가 없다**(그룹 3개 제한만 있다). 그래서 상한은 설정값
  `NAVER_OPTION_COMBO_LIMIT`(기본 500 — 근거 미확인, 오너 확인 필요)로 두고, 넘으면 보내지 않고
  사유코드 `option_limit`로 보류한다. 네이버가 다른 이유로 거부하면 그 응답 원문이 그대로 보인다.
"""
from __future__ import annotations

import math
import os
from typing import Dict, List

#: 오너 스펙 — 축 2개까지(문서상 조합형 그룹 최대 3개).
MAX_AXES = 2
#: 공식 문서에 숫자 없음 — 기본값은 근거 미확인(오너 확인 필요). env로 조정.
DEFAULT_COMBO_LIMIT = 500
#: 커머스API stockQuantity 상한(문서).
STOCK_MAX = 99_999_999

REASON_LIMIT = "option_limit"
REASON_UNTRANSLATED = "option_untranslated"
REASON_DUPLICATE = "option_duplicate"
REASON_PRICE = "option_price"
#: Y7-I(오너 2026-10-09 23:25 KST 400 「중복된 옵션이 있습니다. (옵션명 : 색상)」) — 그룹 이름 중복·빈 이름.
REASON_GROUP_DUP = "naver_option_dup"


def combo_limit() -> int:
    try:
        v = int(str(os.getenv("NAVER_OPTION_COMBO_LIMIT") or "").strip())
        return v if v > 0 else DEFAULT_COMBO_LIMIT
    except ValueError:
        return DEFAULT_COMBO_LIMIT


def _ceil10(v: float) -> int:
    return int(math.ceil(float(v) / 10.0) * 10)


def _skus(product: Dict) -> List[Dict]:
    """옵션 SKU — 스펙이 있고 옵션이 아닌 문구(보증·서비스)는 뺀다(쿠팡 U4와 같은 판정)."""
    from src.uploaders.coupang_options import non_option_sku
    return [k for k in (product.get("skus") or [])
            if isinstance(k, dict) and k.get("spec") and not non_option_sku(k)]


def group_names(product: Dict, axes: int) -> List[str]:
    """조합형 그룹 이름 — 축 이름 한 함수(`option_ko.options_view` → `axis_ko`, 원문 열쇠). 사전검증·등록이 같이 쓴다."""
    from src.collectors import option_ko as K
    groups = [a["name_ko"] for a in K.options_view(product)][:axes]
    if len(groups) < axes:                         # 옵션 축 이름이 없으면 SKU 스펙 순서로 「옵션1」…
        groups += [f"옵션{i + 1}" for i in range(len(groups), axes)]
    return groups


def group_hold(product: Dict) -> str:
    """Y7-I — 그룹 이름이 비었거나 겹치면 보내지 않는다(네이버 400 「중복된 옵션이 있습니다」). 아니면 ''."""
    skus = _skus(product or {})
    if len(skus) <= 1:
        return ""
    axes = max(len(k.get("spec") or []) for k in skus)
    groups = group_names(product, min(axes, MAX_AXES))
    if any(not str(g or "").strip() for g in groups):
        return "보류: 네이버 옵션 그룹 이름이 비었어요 — 옵션 탭에서 축 이름을 넣어 주세요"
    seen, dup = set(), []
    for g in groups:
        k = str(g).strip().lower()
        if k in seen:
            dup.append(g)
        seen.add(k)
    if dup:
        return (f"보류: 네이버 옵션 그룹 이름이 겹쳐요({' · '.join(groups)}) — 「{dup[0]}」이 두 번. "
                "옵션 탭에서 축 이름을 나눠 주세요")
    return ""


def limit_hold(product: Dict) -> str:
    """구조만 본다(가격 없이도 판정 — 사전검증용). 넘으면 사람 말 한 줄, 아니면 빈 문자열."""
    skus = _skus(product or {})
    if len(skus) <= 1:
        return ""
    axes = max(len(k.get("spec") or []) for k in skus)
    if axes <= MAX_AXES:
        gh = group_hold(product)
        if gh:
            return gh
    if axes > MAX_AXES:
        return (f"보류: 네이버 옵션은 {MAX_AXES}축까지 보내요 — 이 상품은 {axes}축"
                f"({' / '.join(str(s) for s in skus[0].get('spec') or [])}). 축을 줄이면 보낼 수 있어요")
    lim = combo_limit()
    if len(skus) > lim:
        return f"보류: 네이버 옵션 조합 {len(skus):,}개 — 상한 {lim:,}개를 넘어요. 조합을 줄이면 보낼 수 있어요"
    return ""


def plan(product: Dict, *, stock_default: int = 999) -> Dict:
    """`{mode, option_info, sale_price, stock, reason_code, why}`.

    mode: `single`(SKU 0~1개 — 예전 몸통 그대로) · `combo`(옵션 싣기) · `hold`(보내지 않음).
    """
    skus = _skus(product or {})
    out = {"mode": "single", "option_info": None, "sale_price": 0, "stock": 0, "reason_code": "", "why": ""}
    if len(skus) <= 1:
        return out
    hold = limit_hold(product)
    if hold:
        code = REASON_GROUP_DUP if hold == group_hold(product) else REASON_LIMIT
        return {**out, "mode": "hold", "reason_code": code, "why": hold}

    from src.collectors import option_ko as K
    from src.uploaders.coupang_options import _as_float
    axes = max(len(k.get("spec") or []) for k in skus)
    groups = group_names(product, axes)

    rows, no_price, untranslated = [], [], []
    for k in skus:
        names = K.spec_ko(product, list(k.get("spec") or []))
        names += [""] * (axes - len(names))
        if any(K._cjk(n) for n in names + groups):
            untranslated.append(" / ".join(names))
        sp = _as_float(k.get("sell_price_krw"))
        if sp <= 0:
            no_price.append(" / ".join(names))
        rows.append((k, names, sp))

    if untranslated:
        return {**out, "mode": "hold", "reason_code": REASON_UNTRANSLATED,
                "why": f"보류: 한국어로 옮기지 못한 옵션 값 {len(untranslated)}개({untranslated[0]}) — 옵션 탭에서 고쳐 주세요"}
    if no_price:
        return {**out, "mode": "hold", "reason_code": REASON_PRICE,
                "why": f"보류: 판매가를 내지 못한 옵션 {len(no_price)}개({no_price[0]}) — 한 가격으로 대신 올리지 않아요"}
    seen, dup = set(), []
    for _k, names, _sp in rows:
        key = tuple(names)
        if key in seen:
            dup.append(" / ".join(names))
        seen.add(key)
    if dup:
        return {**out, "mode": "hold", "reason_code": REASON_DUPLICATE,
                "why": f"보류: 한국어로 옮기니 같은 옵션이 겹쳐요({dup[0]}) — 옵션 탭에서 이름을 나눠 주세요"}

    base = min(_ceil10(sp) for _k, _n, sp in rows)
    combos, total = [], 0
    for k, names, sp in rows:
        st = k.get("stock")
        try:
            st = int(st) if st is not None else stock_default
        except (TypeError, ValueError):
            st = stock_default
        st = max(0, min(st, stock_default, STOCK_MAX))
        total += st
        c = {f"optionName{i + 1}": names[i] for i in range(axes)}
        c.update({"stockQuantity": st, "price": _ceil10(sp) - base,
                  "sellerManagerCode": str(k.get("sku_id") or k.get("skuId") or k.get("id") or ""),
                  "usable": True})
        combos.append(c)
    if total <= 0:
        return {**out, "mode": "hold", "reason_code": REASON_PRICE, "why": "보류: 재고 있는 옵션이 없어요"}
    info = {
        "optionCombinationSortType": "CREATE",
        "optionCombinationGroupNames": {f"optionGroupName{i + 1}": groups[i] for i in range(axes)},
        "optionCombinations": combos,
        "useStockManagement": True,
    }
    return {**out, "mode": "combo", "option_info": info, "sale_price": base, "stock": total}
