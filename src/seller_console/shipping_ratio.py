"""Z5(오너 2026-10-04) — 사전검증 「배송비 비율 초과」: 추정 해외배송비 > 원가의 N%면 보류(「그래도 등록」으로 풀 수 있음).

- 배송비 = 청구 무게(kg) × 가격 정책의 배대지 요율 `shipping.intl_ship_per_kg_krw`(기본 18,000원/kg — 마진 계산과 같은 값).
- 청구 무게 = max(실무게, 부피무게) · 부피무게 = 가로×세로×높이(cm) ÷ divisor(기본 6000).
- 치수·무게는 제목·옵션 값·상세에서 **읽은 것만** 쓴다. 못 읽으면 크기 표(`shipping_size_rules.json`, 관리자 덮어쓰기
  `app_state shipping_size:rules`)의 키워드(소파·의자·매트리스·캐리어·유모차 = 대형 기본값)로 **추정**,
  표에도 없으면 「부피 미확인」 — 보류하지 않는다(재지 못한 것을 막지 않는다).
- 임계값 `SHIPPING_RATIO_HOLD_PCT`(기본 35). 원가 = 매입가 × 환율(원).
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

_RULES_FILE = Path(__file__).with_name("shipping_size_rules.json")
_STATE_KEY = "shipping_size:rules"
_cache: dict = {"at": 0.0, "rules": None}

_DIM_RE = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*[x×*X]\s*(\d{1,3}(?:\.\d+)?)\s*[x×*X]\s*(\d{1,3}(?:\.\d+)?)\s*(mm|cm|厘米|公分)?")
_KG_RE = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*(kg|KG|Kg|公斤|千克)")


def rules() -> dict:
    now = time.monotonic()
    if _cache["rules"] is not None and now - _cache["at"] < 60:
        return _cache["rules"]
    r = json.loads(_RULES_FILE.read_text(encoding="utf-8"))
    try:
        from src.db import image_translate_queue_pg as st
        over = (st.state_get(_STATE_KEY) or {}).get("rules")
        if isinstance(over, dict) and over:
            r = dict(r, **over)
    except Exception:
        pass
    _cache.update(at=now, rules=r)
    return r


def save_rules(r: Optional[dict]) -> None:
    if r:
        for e in r.get("size_defaults") or []:
            if not (isinstance(e, dict) and e.get("label") and isinstance(e.get("keywords"), list)
                    and isinstance(e.get("dims_cm"), list) and len(e["dims_cm"]) == 3):
                raise ValueError("size_defaults 줄은 {label, keywords[], dims_cm[가로,세로,높이], weight_kg} 모양이어야 합니다")
    from src.db import image_translate_queue_pg as st
    st.state_set(_STATE_KEY, {"rules": r or {}})
    _cache.update(at=0.0, rules=None)


def threshold_pct() -> float:
    try:
        return float(os.getenv("SHIPPING_RATIO_HOLD_PCT", "35") or 35)
    except ValueError:
        return 35.0


def _texts(pd: dict) -> str:
    parts = [str(pd.get(k) or "") for k in ("title_src", "title", "title_ko", "description")]
    for o in pd.get("options") or []:
        if isinstance(o, dict):
            parts += [str(v.get("name") if isinstance(v, dict) else v) for v in (o.get("values") or [])]
    for s in pd.get("detail_specs") or []:
        parts.append(json.dumps(s, ensure_ascii=False) if not isinstance(s, str) else s)
    return " ".join(parts)


def read_size(pd: dict) -> Dict[str, Any]:
    """`{dims_cm, weight_kg, basis}` — 읽은 것 → 표 추정 → 없음 순."""
    text = _texts(pd)
    dims = None
    for m in _DIM_RE.finditer(text):
        vals = [float(m.group(i)) for i in (1, 2, 3)]
        if (m.group(4) or "").lower() == "mm":
            vals = [v / 10 for v in vals]
        if all(v > 0 for v in vals) and (dims is None or vals[0] * vals[1] * vals[2] > dims[0] * dims[1] * dims[2]):
            dims = vals
    kg = max((float(m.group(1)) for m in _KG_RE.finditer(text)), default=0.0)
    if dims or kg:
        return {"dims_cm": dims, "weight_kg": kg, "basis": "상품 글에서 읽은 " + ("치수" if dims else "무게")}
    low = text.lower()
    for e in rules().get("size_defaults") or []:
        if any(str(k).lower() in low for k in e.get("keywords") or []):
            return {"dims_cm": [float(x) for x in e["dims_cm"]], "weight_kg": float(e.get("weight_kg") or 0),
                    "basis": f"크기 표 추정({e['label']} 기본값)"}
    return {"dims_cm": None, "weight_kg": 0.0, "basis": ""}


def _per_kg(seller_id: str = "") -> float:
    try:
        from src.db import settings_pg
        from src.pricing.policy import merge_policy
        stored = settings_pg.get_policy(seller_id)["policy"] if seller_id else {}
        return float(merge_policy(stored)["shipping"]["intl_ship_per_kg_krw"])
    except Exception:
        return 18000.0


def _fx(currency: str) -> Optional[float]:
    c = str(currency or "").upper()
    if c == "KRW":
        return 1.0
    try:
        from .data_aggregator import get_fx_rates
        v = get_fx_rates().get(c)
        return float(v) if v else None
    except Exception:
        return None


def estimate(pd: dict, seller_id: str = "") -> Dict[str, Any]:
    """`{state: ok|unknown, ratio_pct, ship_krw, cost_krw, chargeable_kg, basis, line}`."""
    size = read_size(pd)
    try:
        price = float(str(pd.get("price") or pd.get("price_original") or 0).replace(",", ""))
    except ValueError:
        price = 0.0
    fx = _fx(pd.get("currency"))
    if not (size["dims_cm"] or size["weight_kg"]):
        return {"state": "unknown", "line": "부피 미확인 — 치수·무게를 못 읽어 배송비 비율을 재지 못했어요(통과)"}
    if price <= 0 or not fx:
        return {"state": "unknown", "line": "부피는 읽었지만 원가(가격·환율)가 없어 배송비 비율을 재지 못했어요(통과)"}
    vol = (size["dims_cm"][0] * size["dims_cm"][1] * size["dims_cm"][2] / float(rules().get("divisor") or 6000)) \
        if size["dims_cm"] else 0.0
    kg = round(max(vol, size["weight_kg"], 0.5), 1)
    ship = round(kg * _per_kg(seller_id))
    cost = round(price * fx)
    ratio = round(ship / cost * 100) if cost else 0
    dims_txt = ("×".join(f"{d:g}" for d in size["dims_cm"]) + "cm") if size["dims_cm"] else ""
    return {"state": "ok", "ratio_pct": ratio, "ship_krw": ship, "cost_krw": cost, "chargeable_kg": kg,
            "basis": size["basis"],
            "line": (f"추정 배송비 {ship:,}원(청구 무게 {kg:g}kg{' · ' + dims_txt if dims_txt else ''} · {size['basis']}) "
                     f"— 원가 {cost:,}원의 {ratio}% (기준 {threshold_pct():g}%)")}


def hold(pd: dict, seller_id: str = "") -> Optional[Dict[str, str]]:
    """보류 줄(없으면 None). 「그래도 등록」(`ship_ratio_override`)이 있으면 보류하지 않는다."""
    est = estimate(pd, seller_id)
    if est["state"] != "ok" or est["ratio_pct"] <= threshold_pct():
        return None
    if pd.get("ship_ratio_override"):
        return None
    return {"short": f"배송비 비율 초과 {est['ratio_pct']}%", "fix": "ship_ratio", "line": est["line"]}
