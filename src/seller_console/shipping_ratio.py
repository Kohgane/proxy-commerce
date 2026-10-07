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


_PKG_KEYS = ("包装体积", "包装尺寸体积", "外箱体积")
_PKG_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(m³|m3|立方米|立方|方)?\s*$", re.I)


def package_m3(pd: dict) -> float:
    """규격표 「包装体积」(포장 부피, 타오바오 단위 ㎥) — 0 < v < 20일 때만(그 밖은 단위를 몰라 안 씀)."""
    for sp in pd.get("detail_specs") or []:
        if isinstance(sp, (list, tuple)) and len(sp) >= 2 and any(k in str(sp[0]) for k in _PKG_KEYS):
            m = _PKG_RE.match(str(sp[1]))
            if m and 0 < float(m.group(1)) < 20:
                return float(m.group(1))
    return 0.0


def read_size(pd: dict) -> Dict[str, Any]:
    """`{dims_cm, weight_kg, basis, pkg_m3}` — 읽은 것 → 표 추정 → 없음 순. 포장 부피(包装体积 ㎥)는 따로 싣는다."""
    out = _read_size(pd)
    out["pkg_m3"] = package_m3(pd)
    if out["pkg_m3"] and not out["basis"]:
        out["basis"] = "규격표에서 읽은 포장 부피"
    return out


def _read_size(pd: dict) -> Dict[str, Any]:
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


# Z5 후속(오너 2026-10-04 20:30): 요율은 **출발국·발주 경로별** env. 기본값을 지어내지 않는다 —
#   중국발은 오너가 값을 줄 때까지 「요율 미설정 — 비율 판정 생략」, 미국발(몰테일)만 18,000원/kg 기본.
#   발주 경로(중국발): direct = 중국 현지 직접 발송 · forwarder = 배대지 경유. 상품 > 계정 설정 순.
ROUTES = {"direct": "중국 현지 직접 발송", "forwarder": "배대지 경유"}
_ROUTE_KEY = "ship_route:"


def origin_of(pd: dict) -> str:
    """출발국 — cn(타오바오·티몰·1688) · us(아마존 미국·USD 가게) · 그 밖은 빈 문자열(요율 없음)."""
    url = str(pd.get("url") or pd.get("source_url") or "")
    try:
        from src.collectors.share_text import is_taobao_family
        if is_taobao_family(url) or "1688.com" in url:
            return "cn"
    except Exception:
        pass
    if re.search(r"(^|//|\.)amazon\.com/", url) or str(pd.get("currency") or "").upper() == "USD":
        return "us"
    return ""


def account_route(seller_id: str) -> str:
    try:
        from src.db import image_translate_queue_pg as st
        v = str((st.state_get(_ROUTE_KEY + str(seller_id or "")) or {}).get("route") or "")
        return v if v in ROUTES else ""
    except Exception:
        return ""


def save_account_route(seller_id: str, route: str) -> str:
    if route not in ROUTES and route != "":
        raise ValueError("발주 경로는 direct(중국 현지 직접 발송) 또는 forwarder(배대지 경유)")
    from src.db import image_translate_queue_pg as st
    st.state_set(_ROUTE_KEY + str(seller_id or ""), {"route": route})
    return route


def route_of(pd: dict, seller_id: str = "") -> str:
    r = str(pd.get("ship_route") or "")
    return r if r in ROUTES else account_route(seller_id or str(pd.get("seller_id") or ""))


def _env_float(name: str):
    raw = os.getenv(name, "").strip()
    try:
        return float(raw) if raw else None
    except ValueError:
        return None


def rate_and_divisor(origin: str, route: str) -> Dict[str, Any]:
    """`{rate, divisor, rate_env, why}` — rate None이면 판정 생략(why가 사유)."""
    base_div = float(rules().get("divisor") or 6000)
    if origin == "cn":
        names = ([f"SHIPPING_RATE_KRW_PER_KG_CN_{route.upper()}"] if route else []) + ["SHIPPING_RATE_KRW_PER_KG_CN"]
        rate, used = None, ""
        for n in names:
            v = _env_float(n)
            if v:
                rate, used = v, n
                break
        div = next((d for d in ([_env_float(f"SHIPPING_VOL_DIVISOR_CN_{route.upper()}")] if route else [])
                    + [_env_float("SHIPPING_VOL_DIVISOR_CN")] if d), base_div)
        if rate is None:
            want = names[0] if route else "SHIPPING_RATE_KRW_PER_KG_CN"
            why = (f"요율 미설정 — 비율 판정 생략({want})" if route or _route_envs_absent()
                   else "발주 경로 미설정 — 비율 판정 생략(상품 또는 계정 설정에서 「중국 현지 직접 발송/배대지 경유」)")
            return {"rate": None, "divisor": div, "rate_env": want, "why": why}
        return {"rate": rate, "divisor": div, "rate_env": used, "why": ""}
    if origin == "us":
        return {"rate": _env_float("SHIPPING_RATE_KRW_PER_KG_US") or 18000.0,
                "divisor": _env_float("SHIPPING_VOL_DIVISOR_US") or base_div,
                "rate_env": "SHIPPING_RATE_KRW_PER_KG_US", "why": ""}
    return {"rate": None, "divisor": base_div, "rate_env": "", "why": "출발국 요율 없음 — 비율 판정 생략"}


def _route_envs_absent() -> bool:
    return not any(_env_float(f"SHIPPING_RATE_KRW_PER_KG_CN_{r.upper()}") for r in ROUTES)


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
    if not (size["dims_cm"] or size["weight_kg"] or size["pkg_m3"]):
        return {"state": "unknown", "line": "부피 미확인 — 치수·무게를 못 읽어 배송비 비율을 재지 못했어요(통과)"}
    origin = origin_of(pd)
    route = route_of(pd, seller_id) if origin == "cn" else ""
    rd = rate_and_divisor(origin, route)
    if rd["rate"] is None:
        return {"state": "unknown", "origin": origin, "route": route, "line": rd["why"]}
    if price <= 0 or not fx:
        return {"state": "unknown", "line": "부피는 읽었지만 원가(가격·환율)가 없어 배송비 비율을 재지 못했어요(통과)"}
    vol = (size["dims_cm"][0] * size["dims_cm"][1] * size["dims_cm"][2] / rd["divisor"]) if size["dims_cm"] else 0.0
    # 픽스처 3호(오너 2026-10-07): 包装体积 0.36㎥ = 상자 부피 → 부피무게(㎥×1,000,000 ÷ 나눗수). 상품 치수보다 배송에 가깝다.
    pkg_kg = size["pkg_m3"] * 1_000_000 / rd["divisor"] if size["pkg_m3"] else 0.0
    kg = round(max(vol, pkg_kg, size["weight_kg"], 0.5), 1)
    ship = round(kg * rd["rate"])
    cost = round(price * fx)
    ratio = round(ship / cost * 100) if cost else 0
    dims_txt = ("×".join(f"{d:g}" for d in size["dims_cm"]) + "cm") if size["dims_cm"] else ""
    where = ("중국발 · " + ROUTES.get(route, "경로 미설정")) if origin == "cn" else ("미국발" if origin == "us" else "")
    read = [x for x in (f"무게 {size['weight_kg']:g}kg" if size["weight_kg"] else "",
                        f"포장 부피 {size['pkg_m3']:g}㎥(부피무게 {pkg_kg:.1f}kg)" if size["pkg_m3"] else "") if x]
    return {"state": "ok", "ratio_pct": ratio, "ship_krw": ship, "cost_krw": cost, "chargeable_kg": kg,
            "basis": size["basis"], "origin": origin, "route": route, "rate_env": rd["rate_env"], "pkg_m3": size["pkg_m3"],
            "line": (f"추정 배송비 {ship:,}원({where} {rd['rate']:,.0f}원/kg · 청구 무게 {kg:g}kg"
                     f"{' · ' + dims_txt if dims_txt else ''}{' · ' + ' · '.join(read) if read else ''} · {size['basis']}) "
                     f"— 원가 {cost:,}원의 {ratio}% (기준 {threshold_pct():g}%)")}


def hold(pd: dict, seller_id: str = "") -> Optional[Dict[str, str]]:
    """보류 줄(없으면 None). 「그래도 등록」(`ship_ratio_override`)이 있으면 보류하지 않는다."""
    est = estimate(pd, seller_id)
    if est["state"] != "ok" or est["ratio_pct"] <= threshold_pct():
        return None
    if pd.get("ship_ratio_override"):
        return None
    return {"short": f"배송비 비율 초과 {est['ratio_pct']}%", "fix": "ship_ratio", "line": est["line"]}
