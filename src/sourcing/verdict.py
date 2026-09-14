"""src/sourcing/verdict.py — 소싱 원칙 자동 판정(F24).

## 원칙은 사람이 정하고 봇은 재서 말한다 — **판정은 사장님**

여기서 하는 일은 **재는 것**이다. 「등록 후보」라고 적어도 그건 「원칙에 안 걸렸다」는 뜻이지
「팔린다」는 뜻이 아니다. 그 구분이 흐려지면 봇이 사업 결정을 대신하게 된다.

## 잴 수 없는 것은 「수동 확인」이라고 쓴다

국내 갭(국내 판매처 수)·국내 수요는 **우리에게 자동 실측 수단이 없다.**
그럴듯한 숫자를 만들어 넣으면 그 숫자로 결정이 내려진다 — 있는 척하지 않는다.
부피무게도 치수를 보강하기 전엔 **「미측정」**이다(0으로 두면 통과로 읽힌다).

## 재는 재료는 검수표 행 그대로

`build_source_review_row`가 만든 행을 받는다 — **새로 계산하지 않는다.**
실마진·판매가·금칙어·배송은 콘솔 검수표가 쓰는 바로 그 값이다(두 벌 금지).
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Optional

logger = logging.getLogger(__name__)

# 판정 세 갈래. 봇 답장에 그대로 쓰이는 기호라 여기 한 곳에 둔다.
OK, HOLD, NO = "ok", "hold", "no"
MARK = {OK: "✅", HOLD: "⚠️", NO: "❌"}

VERDICT_KO = {OK: "등록 후보", HOLD: "보류", NO: "반려"}


def load_kr_distributor_brands() -> set:
    """국내 총판이 있는 브랜드 목록 — env `KR_DISTRIBUTOR_BRANDS` + `data/kr_distributor_brands.json`.

    **기본은 비어 있다.** 그리고 비어 있으면 「없음」이 아니라 **「확인 필요」**로 낸다 —
    목록이 없는 것과 총판이 없는 것은 다른 말이다. 하드코딩하지 않는다(오너가 볼트에서 관리).
    기존 `load_ipr_watch_brands`와 **같은 관례**다(새 규약 0).
    """
    brands = set()
    for b in re.split(r"[,|]", os.getenv("KR_DISTRIBUTOR_BRANDS", "") or ""):
        b = b.strip().lower()
        if b:
            brands.add(b)
    try:
        if os.path.isfile("data/kr_distributor_brands.json"):
            data = json.load(open("data/kr_distributor_brands.json", encoding="utf-8"))
            seq = data if isinstance(data, list) else (data.get("brands") or [])
            for b in seq:
                b = str(b or "").strip().lower()
                if b:
                    brands.add(b)
    except Exception as exc:
        logger.warning("[소싱판정] 총판 목록 읽기 실패(확인 필요로 처리): %s", exc)
    return brands


def _item(name: str, state: str, text: str) -> dict:
    return {"name": name, "state": state, "text": text}


def _cost_usd(row: dict, fx_rates: Optional[dict]) -> Optional[float]:
    """원가를 달러로. **환산할 수 없으면 None**(임의 환산 금지)."""
    cur = str(row.get("currency") or "").upper()
    price = row.get("price_original")
    if not price:
        return None
    if cur == "USD":
        return float(price)
    fx = fx_rates or {}
    krw = row.get("cost_krw")
    usd_krw = fx.get("USD")
    if krw and usd_krw:
        try:
            return round(float(krw) / float(usd_krw), 2)
        except (TypeError, ValueError, ZeroDivisionError):
            return None
    return None


def evaluate(row: dict, rules: dict, *, fx_rates: Optional[dict] = None,
             extra: Optional[dict] = None, distributors=None) -> dict:
    """검수표 행 + 원칙 → 항목별 판정 + 종합.

    반환 `{verdict, verdict_ko, items: [{name, state, text}], reasons: [...]}`.
    `state`는 `ok`/`hold`/`no` 셋뿐이다 — 「아마도」를 두면 읽는 쪽이 제각기 해석한다.
    """
    row = row or {}
    rules = rules or {}
    extra = extra or {}
    items = []

    # ① 원가 — 공유 시점 가격·환율 반영. 환산 못 하면 그렇게 쓴다.
    cmin = rules.get("cost_min_usd")
    usd = _cost_usd(row, fx_rates)
    if usd is None:
        items.append(_item("원가", HOLD,
                           f"{row.get('cost_basis') or '원가 미상'} — 달러 환산 불가"))
    elif cmin is None:
        items.append(_item("원가", OK, f"${usd}"))
    elif usd < float(cmin):
        items.append(_item("원가", NO, f"${usd} — 하한 ${cmin} 미만"))
    else:
        items.append(_item("원가", OK, f"${usd} (하한 ${cmin})"))

    # ② 예상 판매가 — 가격 자동 규칙이 낸 값 그대로.
    sale = row.get("sale_krw")
    items.append(_item("예상 판매가", OK, f"{int(sale):,}원") if sale
                 else _item("예상 판매가", HOLD,
                            row.get("price_reason") or "원가가 없어 산출 불가"))

    # ③ 마진율 — 실마진(채널 수수료·배송비 반영) vs 목표.
    margin = row.get("margin_pct")
    target = rules.get("target_margin_pct")
    if margin is None:
        items.append(_item("마진율", HOLD, "산출 불가(원가·판매가 미상)"))
    elif target is not None and float(margin) < float(target):
        items.append(_item("마진율", NO, f"{margin}% — 목표 {target}% 미달"))
    else:
        items.append(_item("마진율", OK, f"{margin}%"
                           + (f" (목표 {target}%)" if target is not None else "")))

    # ④ 배송비율 — 부피무게는 치수가 있어야 잰다. 없으면 **미측정**(0으로 두지 않는다).
    ship_cost, cost_krw = row.get("ship_cost_krw"), row.get("cost_krw")
    ship_max = rules.get("ship_cost_max_pct")
    if not (ship_cost and cost_krw):
        vol = extra.get("volumetric_kg")
        items.append(_item("배송비율", HOLD,
                           f"미측정 — 부피무게 {vol}kg(치수 확인)" if vol else
                           "미측정 — 옵션·상세 보강 전이라 치수가 없습니다"))
    else:
        pct = round(float(ship_cost) / float(cost_krw) * 100, 1)
        if ship_max is not None and pct > float(ship_max):
            items.append(_item("배송비율", NO, f"{pct}% — 상한 {ship_max}% 초과"))
        else:
            items.append(_item("배송비율", OK, f"{pct}%"
                               + (f" (상한 {ship_max}%)" if ship_max is not None else "")))

    # ⑤ 금칙어 — 검수표의 취급판정 그대로(여기서 다시 판정하지 않는다).
    fd = row.get("forbidden_detail") or {}
    if row.get("excluded"):
        term = f"{fd.get('kind_ko', '')} '{fd.get('term', '')}'".strip()
        items.append(_item("금칙어", NO, term or "취급 제외"))
    else:
        items.append(_item("금칙어", OK, "걸린 말 없음"))

    # ⑥ 상표권 — 국내 총판 목록 대조. **목록이 없으면 「없음」이 아니라 「확인 필요」**.
    brand = str(row.get("brand") or "").strip()
    dist = load_kr_distributor_brands() if distributors is None else set(distributors)
    warn_labels = [w.get("label", "") for w in (row.get("warnings") or [])]
    if not dist:
        items.append(_item("상표권", HOLD,
                           (f"확인 필요 — 총판 목록 미등록"
                            + (f" · {' · '.join(warn_labels)}" if warn_labels else ""))))
    elif brand and brand.lower() in dist:
        state = NO if rules.get("trademark_block") else HOLD
        items.append(_item("상표권", state, f"{brand} — 국내 총판 있음"))
    else:
        items.append(_item("상표권", OK,
                           (f"총판 목록에 없음"
                            + (f" · {' · '.join(warn_labels)}" if warn_labels else ""))))

    # ⑦⑧ 국내 갭·국내 수요 — **자동 실측 수단이 없다.** 원칙을 켠 경우에만 물어본다.
    if rules.get("domestic_gap_max") is not None:
        items.append(_item("국내 갭", HOLD,
                           f"수동 확인 — 상한 {rules['domestic_gap_max']}건"))
    if rules.get("domestic_demand_required"):
        items.append(_item("국내 수요", HOLD, "수동 확인"))
    if rules.get("niche_brand_required"):
        items.append(_item("니치 브랜드", HOLD,
                           f"수동 확인 — {brand or '브랜드 미확인'}"))

    # ── 종합 ───────────────────────────────────────────────────────────────
    #   하나라도 ❌면 반려. 아니면 ⚠️ 하나라도 있으면 보류. 그 외 등록 후보.
    #   「보류」는 **아직 모른다**는 뜻이지 「나쁘다」가 아니다 — 그래서 사유를 함께 적는다.
    if any(i["state"] == NO for i in items):
        verdict = NO
    elif any(i["state"] == HOLD for i in items):
        verdict = HOLD
    else:
        verdict = OK
    reasons = [f"{i['name']} {i['text']}" for i in items if i["state"] == verdict] \
        if verdict != OK else []
    return {"verdict": verdict, "verdict_ko": VERDICT_KO[verdict],
            "mark": MARK[verdict], "items": items, "reasons": reasons}


def badge(verdict: dict) -> Optional[dict]:
    """목록 뱃지 — `{label, kind}`. 판정이 없으면 `None`(없는 뱃지를 만들지 않는다).

    화면 쪽 기호는 **이모지가 아니라 토큰 색**이다(콘솔 규율) — 답장의 ✅/⚠️/❌와 다른 이유다.
    """
    v = (verdict or {}).get("verdict")
    if v not in MARK:
        return None
    kind = {OK: "on", HOLD: "off", NO: "danger"}[v]
    return {"label": VERDICT_KO[v], "kind": kind}
