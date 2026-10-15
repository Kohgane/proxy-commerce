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
  · price = **판매가 대비 옵션 추가금**(정수). Y11-P: 범위는 판매가의 ±50%(1만 원 이상 — 실측 400) — 가장 싼 조합이
    범위를 못 맞추면 판매가 기준을 옵션 판매가 중 범위를 맞추는 값으로 옮긴다(추가금이 음수일 수 있다 · `pick_base`).
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
#: Y11-P(오너 2026-10-15 19:01 VRSUK 400 원문) — 옵션값 길이·옵션가 범위·가격대 분할 제안.
REASON_NAME_LEN = "naver_option_name_len"
REASON_PRICE_RANGE = "naver_option_price_range"
REASON_SPLIT = "naver_option_split"

#: 옵션값(optionName1~3) 글자 상한 — 실측(VRSUK 400 「optionCombinations[13..15].optionName1 25자 초과」, 28·29·30자 거부).
#: 공식 문서(Context7 `/websites/apicenter_commerce_naver`)엔 숫자가 없다.
OPTION_NAME_MAX = 25
#: 상품명 상한 — 판매자센터 안내 100자(문서엔 숫자 없음 · 미실측).
TITLE_MAX = 100


def price_range(sale_price: int):
    """옵션가(판매가 대비 추가금) 허용 범위 `(최저, 최고)` 원.

    실측: 판매가 3,592,100원 → 400 「price 범위 -1,796,050 ~ 1,796,050」 = 판매가의 ±50%(1만 원 이상 구간).
    1만 원 미만 구간은 판매자센터 안내값(2천 원 미만 0~+100% · 2천~1만 원 -50%~+100%) — **미실측**.
    """
    sp = int(sale_price or 0)
    if sp < 2000:
        lo, hi = 0.0, 1.0
    elif sp < 10000:
        lo, hi = -0.5, 1.0
    else:
        lo, hi = -0.5, 0.5
    return int(math.ceil(sp * lo)), int(math.floor(sp * hi))


def _fits(base: int, prices: List[int]) -> bool:
    lo, hi = price_range(base)
    return all(lo <= p - base <= hi for p in prices)


def pick_base(prices: List[int]) -> Dict:
    """판매가(기준가) — 옵션 판매가(각 옵션의 마진이 담긴 값)는 그대로 두고 **모든 추가금이 범위 안**에 들게.

    순서: ① 가장 싼 옵션가(예전 동작 · 추가금 0 이상) ② 옵션 판매가 중 범위를 맞추는 가장 싼 값(추가금 0원 옵션이 하나 남는다 —
    0원 옵션 필수 여부는 문서에 없어 안전한 쪽) ③ 계산값(최고가÷1.5 올림, 10원 단위). 다 안 되면 `{base: 0}`.
    """
    ps = sorted({int(p) for p in prices if int(p) > 0})
    if not ps:
        return {"base": 0, "how": ""}
    if _fits(ps[0], ps):
        return {"base": ps[0], "how": "min"}
    for p in ps:
        if _fits(p, ps):
            return {"base": p, "how": "option"}
    for frac in (0.5, 1.0):
        b = _ceil10(ps[-1] / (1.0 + frac))
        if _fits(b, ps):
            return {"base": b, "how": "calc"}
    return {"base": 0, "how": ""}


def split_groups(prices: List[int]) -> List[List[int]]:
    """한 상품에 못 담는 가격 폭 → 싼 쪽부터 묶음마다 `pick_base`가 되는 만큼 담는다(인덱스 묶음)."""
    order = sorted(range(len(prices)), key=lambda i: prices[i])
    groups: List[List[int]] = []
    cur: List[int] = []
    for i in order:
        if cur and not pick_base([prices[j] for j in cur + [i]])["base"]:
            groups.append(cur)
            cur = []
        cur.append(i)
    if cur:
        groups.append(cur)
    return groups


def suffix_label(suffix: str) -> str:
    return f"「…({suffix})」" if suffix else "「상품명 그대로」"


def _suffix(names: List[str], others: List[str]) -> str:
    """분할 상품 이름 꼬리 — 그 묶음 옵션 이름에 다 있고 다른 묶음엔 없는 낱말(「(풀가죽)」), 없으면 가격대."""
    import re as _re
    toks = None
    for n in names:
        t = set(_re.findall(r"[가-힣A-Za-z0-9]+", n))
        toks = t if toks is None else toks & t
    rest = set(_re.findall(r"[가-힣A-Za-z0-9]+", " ".join(others)))
    pick = sorted((t for t in (toks or set()) if t not in rest and len(t) >= 2), key=lambda t: (-len(t), t))
    return pick[0] if pick else ""


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
    long_names = [n for _k, names, _sp in rows for n in names if len(n) > OPTION_NAME_MAX]
    if long_names:
        long_names = list(dict.fromkeys(long_names))
        return {**out, "mode": "hold", "reason_code": REASON_NAME_LEN, "long_names": long_names,
                "why": (f"보류: 네이버 옵션값은 {OPTION_NAME_MAX}자까지예요 — 넘는 값 {len(long_names)}개"
                        f"(「{long_names[0]}」 {len(long_names[0])}자). 옵션 탭에서 줄이거나 AI 축약을 기다려 주세요")}
    seen, dup = set(), []
    for _k, names, _sp in rows:
        key = tuple(names)
        if key in seen:
            dup.append(" / ".join(names))
        seen.add(key)
    if dup:
        return {**out, "mode": "hold", "reason_code": REASON_DUPLICATE,
                "why": f"보류: 한국어로 옮기니 같은 옵션이 겹쳐요({dup[0]}) — 옵션 탭에서 이름을 나눠 주세요"}

    prices = [_ceil10(sp) for _k, _n, sp in rows]
    pb = pick_base(prices)
    if not pb["base"]:
        groups = split_groups(prices)
        lo, hi = min(prices), max(prices)
        plan_rows = []
        for gi, g in enumerate(groups):
            gnames = [" / ".join(rows[i][1]) for i in g]
            others = [" / ".join(rows[j][1]) for j in range(len(rows)) if j not in g]
            gp = [prices[i] for i in g]
            # 꼬리: 그 묶음만의 낱말 → 없으면 가장 싼 묶음은 상품명 그대로(""), 나머지는 「구성 n」(지어낸 말 대신 순번)
            plan_rows.append({"skus": [str(rows[i][0].get("sku_id") or rows[i][0].get("skuId") or rows[i][0].get("id") or i) for i in g],
                              "names": gnames, "base": pick_base(gp)["base"], "min": min(gp), "max": max(gp),
                              "suffix": _suffix(gnames, others) or ("" if gi == 0 else f"구성 {gi + 1}")})
        return {**out, "mode": "hold", "reason_code": REASON_SPLIT, "split": plan_rows,
                "why": (f"보류: 옵션 가격 폭이 커서({lo:,}~{hi:,}원) 네이버 한 상품에 못 담아요(옵션가는 판매가의 ±50%) — "
                        f"가격대별 {len(groups)}개 상품으로 나눠 등록할까요? "
                        + " · ".join(f"{suffix_label(r['suffix'])} {len(r['names'])}개 "
                                     + (f"{r['min']:,}원" if r['min'] == r['max'] else f"{r['min']:,}~{r['max']:,}원") for r in plan_rows))}
    base = pb["base"]
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
    return {**out, "mode": "combo", "option_info": info, "sale_price": base, "stock": total,
            "base_how": pb["how"], "base_min": min(prices), "price_range": price_range(base)}


def base_note(op: Dict) -> str:
    """판매가 기준을 옮겼으면 카드 한 줄(보류 아님) — 옵션마다 판매가(마진)는 그대로."""
    if (op or {}).get("mode") != "combo" or op.get("base_how") in ("", "min", None):
        return ""
    lo, hi = op.get("price_range") or (0, 0)
    return (f"네이버 판매가 기준 {int(op['sale_price']):,}원으로 맞췄어요(가장 싼 옵션 {int(op.get('base_min') or 0):,}원) — "
            f"옵션가 범위 {lo:,}~{hi:,}원(판매가 ±50%) 안 · 옵션마다 판매가는 그대로")


# ── Y11-P 분할 등록(오너 확인 뒤에만) ─────────────────────────────────────────────────────────────

def split_sig(groups: List[Dict]) -> str:
    """분할 묶음의 서명 — 오너가 확인한 그 묶음과 지금 계산이 같은지(환율·원가가 바뀌면 다시 묻는다)."""
    return "|".join(",".join(sorted(str(s) for s in (g.get("skus") or []))) for g in groups or [])


def split_approved(product: Dict, op: Dict) -> bool:
    """`plan`이 분할 보류를 냈고, 저장된 오너 확인(`naver_split_ok`)이 지금 묶음과 같은가."""
    ok = (product or {}).get("naver_split_ok")
    return bool(isinstance(ok, dict) and (op or {}).get("reason_code") == REASON_SPLIT
                and ok.get("sig") and ok.get("sig") == split_sig(op.get("split") or []))


def split_products(product: Dict, op: Dict) -> List[Dict]:
    """확인된 분할 → 묶음마다 상품 사본(SKU는 그 묶음만 · 상품명 끝에 「(꼬리)」 · 옵션 값 목록도 그 묶음만)."""
    out: List[Dict] = []
    skus = _skus(product or {})
    by_id = {str(k.get("sku_id") or k.get("skuId") or k.get("id") or i): k for i, k in enumerate(skus)}
    for g in (op or {}).get("split") or []:
        sub_skus = [by_id[s] for s in g.get("skus") or [] if s in by_id]
        if not sub_skus:
            continue
        used = {str(x) for k in sub_skus for x in (k.get("spec") or [])}
        opts = []
        for o in (product.get("options") or []):
            if not isinstance(o, dict):
                opts.append(o)
                continue
            vals = o.get("values") or []
            keep = [i for i, v in enumerate(vals) if str(v.get("name") if isinstance(v, dict) else v) in used]
            o2 = dict(o, values=[vals[i] for i in keep])
            if isinstance(o.get("values_ko"), list) and o["values_ko"]:
                o2["values_ko"] = [o["values_ko"][i] for i in keep if i < len(o["values_ko"])]
            opts.append(o2)
        suffix = str(g.get("suffix") or "").strip()
        title = str(product.get("title_ko") or product.get("title") or "").strip()
        new_title = f"{title} ({suffix})" if suffix else title
        out.append({**product, "skus": sub_skus, "options": opts, "title": new_title, "title_ko": new_title,
                    "naver_split_part": {"suffix": suffix, "skus": list(g.get("skus") or [])}})
    return out
