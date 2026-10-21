"""Z5(오너 2026-10-04) — 사전검증 「배송비 비율 초과」: 추정 해외배송비 > 원가의 N%면 보류(「그래도 등록」으로 풀 수 있음).

- 배송비 = `ship_cost()` 한 숫자(Z6 배송비 엔진 — 카드·사전검증·마진 계산기·가격 계산기 공용).
- 청구 무게 = max(실무게, 부피무게) · 부피무게 = 가로×세로×높이(cm) ÷ divisor(기본 6000).
- 치수·무게는 제목·옵션 값·상세에서 **읽은 것만** 쓴다. 못 읽으면 크기 표(`shipping_size_rules.json`, 관리자 덮어쓰기
  `app_state shipping_size:rules`)의 키워드(소파·의자·매트리스·캐리어·유모차 = 대형 기본값)로 **추정**,
  표에도 없으면 「부피 미확인」 — 보류하지 않는다(재지 못한 것을 막지 않는다).
- 임계값 `SHIPPING_RATIO_MAX`(기본 35 · 옛 이름 `SHIPPING_RATIO_HOLD_PCT`도 읽음).
- Y13-C c(오너 결정 2026-10-18): 분모 = **판매가**(등록이 매기는 그 값 — `UploadDispatcher._landed_krw`, 마켓별 수수료 반영).
  예전 분모(원가)는 싸고 부피 큰 물건(피샹리 1인 소파 원가 215,766 · 운임 94,500 = 44%)을 영원히 막았다 — 판매가 589,400 대비 16%.

Z6(오너 2026-10-08): 중국발 배송비는 **배송비 엔진**(`shipping_engine` — 퍼센티 배대지 요율표 데이터)이 정한다.
  카드·사전검증·마진 계산기가 같은 결과를 쓴다. 폐기: `SHIPPING_RATE_KRW_PER_KG_CN[_경로]`(있으면 무시+경고 로그).
  「요율 미설정」은 요율표 파일이 없을 때만. 미국발(몰테일 kg당)은 예전 그대로.
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
    """Y13-C c: `SHIPPING_RATIO_MAX`(숫자만 · 기본 35). 옛 이름 `SHIPPING_RATIO_HOLD_PCT`는 새 이름이 없을 때만."""
    raw = os.getenv("SHIPPING_RATIO_MAX") or os.getenv("SHIPPING_RATIO_HOLD_PCT") or "35"
    try:
        return float(raw)
    except ValueError:
        return 35.0


def sell_krw(pd: dict, market: str = "") -> float:
    """Y13-C c — 비율의 분모: **등록이 매기는 원화 판매가**(`UploadDispatcher._landed_krw` — 사전검증·등록 같은 함수,
    마켓별 수수료가 달라 마켓을 받는다 · 비우면 기준 마켓). 못 내면 0(비율 판정 생략 — 지어내지 않는다)."""
    try:
        from .upload_dispatcher import UploadDispatcher
        v, _why = UploadDispatcher._landed_krw(pd or {}, market)
        return float(v or 0)
    except Exception:                                            # noqa: BLE001
        return 0.0


def _texts(pd: dict) -> str:
    parts = [str(pd.get(k) or "") for k in ("title_src", "title", "title_ko", "description")]
    for o in pd.get("options") or []:
        if isinstance(o, dict):
            parts += [str(v.get("name") if isinstance(v, dict) else v) for v in (o.get("values") or [])]
    for s in pd.get("detail_specs") or []:
        parts.append(json.dumps(s, ensure_ascii=False) if not isinstance(s, str) else s)
    # Y13-C 3(오너 2026-10-18 피샹리): 사진 글자 — 대표 「尺寸 100x114x74」 · 상세 「左右宽100cm 前后长114cm 总高74cm」
    parts.append(str(pd.get("photo_text") or ""))
    return " ".join(parts)


# Y13-C 3: 「가로·세로·높이」가 이름표와 함께 적힌 치수(상세 사진 규격표 · 상세 글). 단위(cm·mm)가 붙은 것만 —
#   축마다 가장 큰 값(좌석 깊이 55 · 등받이 폭 80보다 전체 114 · 100). 셋 다 있어야 치수로 쓴다.
_AXIS = {"w": ("宽", "가로", "폭", "너비", "width", "W"), "l": ("长", "深", "세로", "길이", "깊이", "length", "depth", "D", "L"),
         "h": ("高", "높이", "height", "H")}
_LAB_RE = re.compile(r"(宽|长|深|高|가로|세로|길이|깊이|높이|폭|너비|width|length|depth|height)\s*(?:度)?\s*[:：/=]?\s*"
                     r"(\d{1,3}(?:\.\d+)?)\s*(cm|CM|厘米|公分|mm|MM|毫米)", re.I)


#: Y15(운영 10-21 치수 수집 5건 0건 — 읽는 규칙 구멍): 숫자마다 단위가 붙은 `60cm×50cm×45cm` · 이름표 뒤에 단위가 한 번만
#:   있는 `长60 宽55 高70（cm）` · 둥근 물건 `直径35cm 高45cm`(지름 × 지름 × 높이 = 둘레 상자). 단위가 아예 없으면 읽지 않는다.
_UNIT_MID_RE = re.compile(r"(\d)\s*(?:cm|CM|厘米|公分|mm|MM|毫米)\s*(?=[x×*X]\s*\d)")
_UNIT_TAIL_RE = re.compile(r"[（(]\s*(?:单位\s*[:：]?\s*)?(cm|CM|厘米|公分)\s*[)）]|单位\s*[:：]?\s*(cm|CM|厘米|公分)")
_LAB_NOUNIT_RE = re.compile(r"(宽|长|深|高|가로|세로|길이|깊이|높이|폭|너비)\s*(?:度)?\s*[:：/=]?\s*(\d{1,3}(?:\.\d+)?)(?!\s*(?:\.\d|\d|cm|CM|厘米|公分|mm|MM|毫米))")
_DIAM_RE = re.compile(r"(?:直径|直徑|지름|Φ|φ|ø|Ø)\s*[:：/=]?\s*(\d{1,3}(?:\.\d+)?)\s*(cm|CM|厘米|公分|mm|MM|毫米)")
_HEIGHT_RE = re.compile(r"(?:高度|高|높이|height)\s*[:：/=]?\s*(\d{1,3}(?:\.\d+)?)\s*(cm|CM|厘米|公分|mm|MM|毫米)", re.I)


def normalize_dim_text(text: str) -> str:
    """치수 읽기 전 정리 — 곱셈 사이 단위 떼기(`60cm×50cm×45cm` → `60×50×45cm`), 한 번만 적힌 단위를 이름표 숫자에 붙이기."""
    t = _UNIT_MID_RE.sub(r"\1", str(text or ""))
    m = _UNIT_TAIL_RE.search(t)
    if m:
        unit = m.group(1) or m.group(2)
        t = _LAB_NOUNIT_RE.sub(lambda x: f"{x.group(1)}{x.group(2)}{unit}", t)
    return t


def _cm(val: str, unit: str) -> float:
    return float(val) / 10 if unit.lower() in ("mm", "毫米") else float(val)


def round_dims(text: str) -> Optional[Dict[str, Any]]:
    """둥근 물건 — 지름과 높이가 둘 다 있으면 `[지름, 지름, 높이]`(둘레 상자). 하나라도 없으면 None."""
    t = normalize_dim_text(text)
    d = [_cm(m.group(1), m.group(2)) for m in _DIAM_RE.finditer(t)]
    h = [_cm(m.group(1), m.group(2)) for m in _HEIGHT_RE.finditer(t)]
    d, h = [x for x in d if 5 <= x <= 400], [x for x in h if 5 <= x <= 400]
    if not (d and h):
        return None
    return {"dims_cm": [max(d), max(d), max(h)], "seen": f"지름 {max(d):g} · 높이 {max(h):g}cm"}


def labeled_dims(text: str) -> Optional[Dict[str, Any]]:
    """`{dims_cm:[가로, 세로, 높이], seen:"宽100·长114·高74"}` 또는 None."""
    best: Dict[str, float] = {}
    text = normalize_dim_text(text)
    for m in _LAB_RE.finditer(str(text or "")):
        lab, val, unit = m.group(1), float(m.group(2)), m.group(3).lower()
        if unit in ("mm", "毫米"):
            val = val / 10
        if not 5 <= val <= 400:                                  # 1-3cm 오차 안내·받침 높이 같은 조각은 뺀다
            continue
        ax = next((a for a, names in _AXIS.items() if lab.lower() in (n.lower() for n in names)), "")
        if ax and val > best.get(ax, 0):
            best[ax] = val
    if len(best) < 3:
        return round_dims(text)
    dims = [best["w"], best["l"], best["h"]]
    return {"dims_cm": dims, "seen": f"가로 {dims[0]:g} · 세로 {dims[1]:g} · 높이 {dims[2]:g}cm"}


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
    text = normalize_dim_text(_texts(pd))
    dims = None
    for m in _DIM_RE.finditer(text):
        vals = [float(m.group(i)) for i in (1, 2, 3)]
        if (m.group(4) or "").lower() == "mm":
            vals = [v / 10 for v in vals]
        if all(v > 0 for v in vals) and (dims is None or vals[0] * vals[1] * vals[2] > dims[0] * dims[1] * dims[2]):
            dims = vals
    kg = max((float(m.group(1)) for m in _KG_RE.finditer(text)), default=0.0)
    basis = "상품 글·사진에서 읽은 " + ("치수" if dims else "무게")
    if not dims:
        lab = labeled_dims(text)
        if lab:
            dims, basis = lab["dims_cm"], f"상품 글·사진 규격에서 읽은 치수({lab['seen']})"
    if dims or kg:
        return {"dims_cm": dims, "weight_kg": kg, "basis": basis}
    low = str(_texts_no_photo(pd)).lower()
    for e in rules().get("size_defaults") or []:
        if any(str(k).lower() in low for k in e.get("keywords") or []):
            if e.get("furniture"):
                # Y13-C 3(오너 2026-10-18): 가구는 기본 크기로 추정하지 않는다 — 실측이 없으면 「치수 확인 필요」로 막는다
                return {"dims_cm": None, "weight_kg": 0.0, "basis": "", "need_dims": e["label"]}
            return {"dims_cm": [float(x) for x in e["dims_cm"]], "weight_kg": float(e.get("weight_kg") or 0),
                    "basis": f"크기 표 추정({e['label']} 기본값)"}
    return {"dims_cm": None, "weight_kg": 0.0, "basis": ""}


def _texts_no_photo(pd: dict) -> str:
    """크기 표 키워드는 상품 글에서만 본다(사진 속 「椅」 광고 글자로 상품 종류를 정하지 않는다)."""
    return _texts({k: v for k, v in (pd or {}).items() if k != "photo_text"})


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


_SHARED_SCOPE = "shared"


def _session_shared() -> bool:
    """Y6-C E1: 지금 요청의 사람이 공유 마켓 사용자(관리자·`FAMILY_EMAILS`)인가 — 요청 밖(크론)·비로그인은 아니오."""
    try:
        from flask import has_request_context, session
        if not has_request_context() or not (session.get("user_id") or session.get("user_email") or session.get("email")):
            return False
        from .market_pick import session_is_shared
        return session_is_shared()
    except Exception:
        return False


def _read_route(key: str) -> str:
    try:
        from src.db import image_translate_queue_pg as st
        v = str((st.state_get(_ROUTE_KEY + key) or {}).get("route") or "")
        return v if v in ROUTES else ""
    except Exception:
        return ""


def account_route(seller_id: str, shared: Optional[bool] = None) -> str:
    """계정 기본 발주 경로. Y6-C E1(오너 2026-10-07): 공유 마켓 사용자(오너·가족)는 **한 벌**(`ship_route:shared`)을
    읽는다 — 가족이 자기 셀러 키로 읽어 「계정 기본 (미설정)」이 뜨던 자리. 한 벌이 비면 예전 자기 키(옛 저장값) 폴백."""
    if shared is None:
        shared = _session_shared()
    if shared:
        return _read_route(_SHARED_SCOPE) or _read_route(str(seller_id or ""))
    return _read_route(str(seller_id or ""))


def save_account_route(seller_id: str, route: str, shared: Optional[bool] = None) -> str:
    if route not in ROUTES and route != "":
        raise ValueError("발주 경로는 direct(중국 현지 직접 발송) 또는 forwarder(배대지 경유)")
    if shared is None:
        shared = _session_shared()
    from src.db import image_translate_queue_pg as st
    st.state_set(_ROUTE_KEY + (_SHARED_SCOPE if shared else str(seller_id or "")), {"route": route})
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


def _size_for(pd: dict) -> Dict[str, Any]:
    """읽은 크기(毛重·包装体积·치수·크기 표) — 카드에서 직접 넣은 값(`ship_input`)이 있으면 그게 이긴다."""
    size = read_size(pd)
    # Y14(오너 2026-10-21): 글·사진에서 못 읽었으면 서버가 모은 치수(`dims_auto` — 온바운드 규격·사진 OCR·규격 블록 대조)를 쓴다.
    #   「추정」이면 근거에 그대로 적힌다(숨기지 않음). 오너가 넣은 값(`ship_input`)은 아래에서 여전히 이긴다.
    da = pd.get("dims_auto") if isinstance(pd.get("dims_auto"), dict) else {}
    if not size.get("dims_cm") and isinstance(da.get("dims_cm"), list) and len(da["dims_cm"]) == 3:
        size = dict(size, dims_cm=[float(x) for x in da["dims_cm"]], need_dims="",
                    basis=f"서버 수집 치수 — {da.get('label') or da.get('confidence') or ''}")
    mi = pd.get("ship_input") if isinstance(pd.get("ship_input"), dict) else {}
    try:
        w = float(mi.get("weight_kg") or 0)
        d = [float(mi.get(k) or 0) for k in ("l", "w", "h")]
    except (TypeError, ValueError):
        w, d = 0.0, [0, 0, 0]
    if w > 0 or all(x > 0 for x in d):
        size = dict(size, weight_kg=w if w > 0 else size["weight_kg"],
                    dims_cm=d if all(x > 0 for x in d) else size["dims_cm"], basis="직접 입력한 무게·치수")
    return size


def _won(n) -> str:
    return f"{int(round(n)):,}원"


def estimate(pd: dict, seller_id: str = "", market: str = "") -> Dict[str, Any]:
    """`{state: ok|unknown|bulky|need_dims, ratio_pct, ship_krw, sell_krw, cost_krw, chargeable_kg, basis, line, ...}`.
    비율 = 운임 ÷ 판매가(`sell_krw` — 그 마켓 판매가, 마켓을 모르면 기준 마켓)."""
    size = _size_for(pd)
    try:
        price = float(str(pd.get("price") or pd.get("price_original") or 0).replace(",", ""))
    except ValueError:
        price = 0.0
    fx = _fx(pd.get("currency"))
    if not (size["dims_cm"] or size["weight_kg"] or size["pkg_m3"]):
        # 가구 치수 게이트는 운임을 잴 수 있는 출발국(중국·미국)에서만 — 출발국 요율이 없으면 예전처럼 통과
        if size.get("need_dims") and origin_of(pd) in ("cn", "us"):
            return {"state": "need_dims", "need_input": True, "label": size["need_dims"],
                    "line": (f"치수 확인 필요 — 가구({size['need_dims']})는 기본 크기로 추정하지 않아요. 상품 글·사진 규격에서 "
                             "가로·세로·높이를 못 찾았어요 → 「무게·크기 직접 넣기」에 넣으면 실측으로 다시 계산해요")}
        return {"state": "unknown", "need_input": True,
                "line": "부피 미확인 — 무게·가로·세로·높이를 넣으면 계산해요(통과)"}
    origin = origin_of(pd)
    if origin == "cn":
        return _estimate_cn(pd, size, price, fx, seller_id, market)
    rd = rate_and_divisor(origin, "")
    if rd["rate"] is None:
        return {"state": "unknown", "origin": origin, "line": rd["why"]}
    if price <= 0 or not fx:
        return {"state": "unknown", "line": "부피는 읽었지만 원가(가격·환율)가 없어 배송비 비율을 재지 못했어요(통과)"}
    vol = (size["dims_cm"][0] * size["dims_cm"][1] * size["dims_cm"][2] / rd["divisor"]) if size["dims_cm"] else 0.0
    pkg_kg = size["pkg_m3"] * 1_000_000 / rd["divisor"] if size["pkg_m3"] else 0.0
    kg = round(max(vol, pkg_kg, size["weight_kg"], 0.5), 1)
    ship = round(kg * rd["rate"])
    cost = round(price * fx)
    sell = round(sell_krw(pd, market))
    dims_txt = ("×".join(f"{d:g}" for d in size["dims_cm"]) + "cm") if size["dims_cm"] else ""
    detail = f"(미국발 {rd['rate']:,.0f}원/kg · 청구 무게 {kg:g}kg{' · ' + dims_txt if dims_txt else ''} · {size['basis']})"
    if not sell:
        return {"state": "unknown", "ship_krw": ship, "cost_krw": cost, "chargeable_kg": kg, "origin": origin,
                "line": f"운임 {ship:,}원{detail} — 판매가를 못 내 비율을 재지 못했어요(통과)"}
    ratio = round(ship / sell * 100)
    return {"state": "ok", "ratio_pct": ratio, "ship_krw": ship, "sell_krw": sell, "cost_krw": cost, "chargeable_kg": kg,
            "basis": size["basis"], "origin": origin, "rate_env": rd["rate_env"], "pkg_m3": size["pkg_m3"],
            "line": _ratio_line(ship, sell, ratio, detail)}


def _ratio_line(ship: int, sell: int, ratio: int, detail: str = "") -> str:
    """Y13-C c(오너): 「운임 n원 · 판매가 대비 n%」."""
    return f"운임 {ship:,}원 · 판매가 {sell:,}원 대비 {ratio}% (기준 {threshold_pct():g}%){(' ' + detail) if detail else ''}"


def _ship_from_quote(q: Dict[str, Any]) -> Optional[int]:
    """엔진 결과 → 배송비 한 숫자. 대형화물은 LCL 추정, 그 밖은 적용 배송비 + 부가서비스. 모르면 None."""
    if q.get("bulky"):
        return int(q["lcl"]["krw"]) if q.get("lcl") else None
    if not q.get("ok"):
        return None
    return int(q["applied"]["krw"] + q["addons"]["krw"])


def ship_cost(size: Dict[str, Any], *, origin: str = "cn", seller_id: str = "", mode: str = "") -> Dict[str, Any]:
    """Z6 후속(오너 2026-10-08): **시스템의 배송비 한 숫자** — 카드·사전검증·마진 계산기·가격 계산기가 모두 이것을 쓴다.
    `size = {weight_kg, dims_cm, pkg_m3}`. → `{krw(None=모름), estimated, source, why, bulky}`.
    중국발 = 배송비 엔진(요율표) · 미국발 = 몰테일 kg당(예전 그대로) · 그 밖 = 요율 없음(None — 지어내지 않는다)."""
    size = {"weight_kg": float(size.get("weight_kg") or 0), "dims_cm": size.get("dims_cm") or None,
            "pkg_m3": float(size.get("pkg_m3") or 0)}
    if not (size["weight_kg"] or size["dims_cm"] or size["pkg_m3"]):
        return {"krw": None, "estimated": False, "source": "none", "why": "무게·부피 모름", "bulky": []}
    if origin == "cn":
        from . import shipping_engine as E
        E.warn_legacy_env()
        st = E.get_settings(seller_id)
        q = E.quote(size, mode=mode if mode in E.MODES else st["default_mode"], divisor=E.divisor(st),
                    provider=st["provider"], addons=st["addons"], lcl=bool(st["business"]))
        if not q["ok"] and "요율표" in str(q.get("why") or ""):
            return {"krw": None, "estimated": False, "source": "none", "why": str(q["why"]), "bulky": []}
        krw = _ship_from_quote(q)
        est = bool(q["lcl"]["estimated"]) if (q["bulky"] and q.get("lcl")) else bool(q["estimated"])
        return {"krw": krw, "estimated": est, "source": "engine_lcl" if q["bulky"] else "engine",
                "why": "" if krw is not None else "대형화물 — LCL 부피를 몰라요", "bulky": q["bulky"], "quote": q}
    if origin == "us":
        rd = rate_and_divisor("us", "")
        vol = (size["dims_cm"][0] * size["dims_cm"][1] * size["dims_cm"][2] / rd["divisor"]) if size["dims_cm"] else 0.0
        pkg_kg = size["pkg_m3"] * 1_000_000 / rd["divisor"] if size["pkg_m3"] else 0.0
        kg = round(max(vol, pkg_kg, size["weight_kg"], 0.5), 1)
        return {"krw": round(kg * rd["rate"]), "estimated": False, "source": "us_per_kg", "why": "", "bulky": [], "kg": kg,
                "rate": rd["rate"]}
    return {"krw": None, "estimated": False, "source": "none", "why": "출발국 요율 없음", "bulky": []}


def ship_cost_for(pd: dict, seller_id: str = "") -> Dict[str, Any]:
    """상품 한 건의 배송비 한 숫자 — 등록 판매가(`price.calc_sell_price`)가 이것을 국제배송비로 쓴다.
    출발국: 상품 주소(타오바오·티몰·1688 → 중국발 · 아마존 미국 → 미국발) → 없으면 통화(USD → 미국발 · CNY → 중국발)."""
    origin = origin_of(pd or {})
    if not origin:
        cur = str((pd or {}).get("currency") or "").upper()
        origin = {"USD": "us", "CNY": "cn"}.get(cur, "")
    return ship_cost(_size_for(pd or {}), origin=origin, seller_id=seller_id or str((pd or {}).get("seller_id") or ""),
                     mode=str((pd or {}).get("ship_mode") or ""))


def _estimate_cn(pd: dict, size: Dict[str, Any], price: float, fx, seller_id: str, market: str = "") -> Dict[str, Any]:
    from . import shipping_engine as E
    E.warn_legacy_env()
    st = E.get_settings(seller_id or str(pd.get("seller_id") or ""))
    sc = ship_cost(size, origin="cn", seller_id=seller_id or str(pd.get("seller_id") or ""), mode=str(pd.get("ship_mode") or ""))
    if sc["source"] == "none":
        return {"state": "unknown", "origin": "cn", "line": f"요율 미설정 — 비율 판정 생략({sc['why']})"}
    q = sc["quote"]
    base = {"origin": "cn", "mode": q["mode"], "mode_label": q["mode_label"], "basis": size["basis"],
            "pkg_m3": size["pkg_m3"], "provider_label": q["provider_label"], "version": q["version"],
            "table_date": q.get("table_date") or "",
            "divisor": q["divisor"], "estimated": q["estimated"], "addons": q["addons"], "bulky": q["bulky"],
            "lines": _three_lines(q), "lcl": q["lcl"], "lcl_line": "", "jeju_line": ""}
    lcl = q["lcl"]
    show_lcl = bool(lcl) and (bool(q["bulky"]) or (st["business"] and lcl["cbm"] >= float(st["lcl_threshold_cbm"] or 0.5)))
    if show_lcl:
        billed = f"(청구 {lcl['qty']:g}cbm)" if lcl["qty"] != lcl["cbm"] else ""
        base["lcl_line"] = (f"LCL 견적 {lcl['cbm']:g}cbm{billed} → {_won(lcl['krw'])}{' (표 밖 추정)' if lcl['estimated'] else ''}"
                            f" — {lcl['notice']}")
    cost = round(price * fx) if (price > 0 and fx) else 0
    sell = round(sell_krw(pd, market)) if cost else 0
    if q["bulky"]:
        base.update(code="bulky_carrier", jeju_line="제주·도서산간은 추가 운임이 붙어요.")
        head = f"대형화물 — 국내 배송비 별도(경동택배 표준운임) · {' · '.join(q['bulky'])} · {size['basis']}"
        if lcl and sell:
            ratio = round(sc["krw"] / sell * 100)
            return dict(base, state="ok", ratio_pct=ratio, ship_krw=sc["krw"], sell_krw=sell, cost_krw=cost, chargeable_kg=None,
                        line=f"{_ratio_line(sc['krw'], sell, ratio)} — LCL 추정 · {head}")
        if lcl and lcl.get("krw"):
            return dict(base, state="unknown", ship_krw=sc["krw"], cost_krw=cost,
                        line=f"운임 {_won(lcl['krw'])}(LCL 추정) · {head} — 판매가를 못 내 비율을 재지 못했어요(통과)")
        return dict(base, state="bulky", line=f"{head} — 비율 판정 생략(LCL 부피를 몰라요)")
    if not q["ok"]:
        return dict(base, state="unknown", line="부피 미확인 — 무게·가로·세로·높이를 넣으면 계산해요(통과)", need_input=True)
    ship = sc["krw"]
    if not sell:
        return dict(base, state="unknown", ship_krw=ship, chargeable_kg=q["applied"]["qty"],
                    line=f"운임 {_won(ship)} — 판매가를 못 내 비율을 재지 못했어요(원가·환율 확인 · 통과)")
    ratio = round(ship / sell * 100)
    ad = q["addons"]
    ad_txt = f" + 부가서비스 {_won(ad['krw'])}{'~' if ad['at_least'] else ''}" if ad["items"] else ""
    detail = (f"({q['provider_label']} {q['mode_label']} · 청구 무게 {q['applied']['qty']:g}kg({q['applied']['basis']} · 0.5kg 올림)"
              f"{ad_txt}{' · 표 밖 추정' if q['estimated'] else ''} · {size['basis']})")
    return dict(base, state="ok", ratio_pct=ratio, ship_krw=ship, sell_krw=sell, cost_krw=cost,
                chargeable_kg=q["applied"]["qty"], line=_ratio_line(ship, sell, ratio, detail))


def _three_lines(q: Dict[str, Any]) -> List[str]:
    """퍼센티 계산기와 같은 세 줄 — 실제 무게 비용 / 부피 무게 비용 / 적용 배송비."""
    out = []
    a, v, ap = q.get("actual"), q.get("volume"), q.get("applied")
    est = lambda x: " (표 밖 추정)" if x and x.get("estimated") else ""
    out.append(f"실제 무게 비용: {a['kg']:g}kg → {a['qty']:g}kg {_won(a['krw'])}{est(a)}" if a else "실제 무게 비용: 무게 모름")
    out.append(f"부피 무게 비용: {v['kg']:g}kg(÷{q['divisor']:g}) → {v['qty']:g}kg {_won(v['krw'])}{est(v)}" if v
               else "부피 무게 비용: 치수 모름")
    out.append(f"적용 배송비: {_won(ap['krw'])}({ap['basis']} · {q['mode_label']}){est(ap)}" if ap else "적용 배송비: 계산 못 함")
    return out


def hold(pd: dict, seller_id: str = "", market: str = "") -> Optional[Dict[str, str]]:
    """보류 줄(없으면 None). 「그래도 등록」(`ship_ratio_override`)이 있으면 보류하지 않는다. 비율 분모 = 그 마켓 판매가."""
    est = estimate(pd, seller_id, market)
    if est["state"] == "need_dims":
        return {"short": "치수 확인 필요", "fix": "ship_dims", "line": est["line"]}
    if est["state"] != "ok" or est["ratio_pct"] <= threshold_pct():
        return None
    if pd.get("ship_ratio_override"):
        return None
    tag = " (LCL 추정)" if est.get("code") == "bulky_carrier" else ""
    return {"short": f"운임 {est['ship_krw']:,}원 · 판매가 대비 {est['ratio_pct']}%{tag}", "fix": "ship_ratio", "line": est["line"]}
