"""Z6(오너 2026-10-08) — 배송비 엔진: 퍼센티 배대지 「해외배송비 계산기」와 같은 판정.

요율표는 **데이터**(`data/shipping/<provider>_<캡처일>.json` — 버전·출처·캡처일 기록)다. 식으로 근사하지 않는다:
- 표에 있는 무게(부피)는 표 값 그대로.
- 표 밖(마지막 행보다 무거움)은 **마지막 두 행 기울기로 외삽** — `estimated=True`.
- `over`(예: 40kg 이상 0.5kg당 N원 추가)는 그 지점부터 단위당 N원으로 이어 간다 — 역시 표 밖이라 `estimated=True`.
- 표 최소보다 작으면(LCL 1cbm 미만) 표 첫 행 — 표가 말하지 않은 것이라 `estimated=True`.

청구 무게 = max(실중량, 부피무게)를 0.5kg 단위로 **올림**(1.72 → 2.0). 부피무게 = 가로×세로×높이(cm) ÷ 제수
(`SHIPPING_VOL_DIVISOR`, 기본 6000 — 퍼센티 표에 미기재, 오너 실측 후 확정. 셀러 설정이 있으면 그 값).
LCL cbm = 가로×세로×높이(m) — 소수 셋째 자리에서 올려 둘째 자리.

대형화물(실중량 ≥20kg · 세 변 합 ≥150cm · 한 변 ≥100cm) = 경동택배/기타화물 이관(`bulky_carrier`).
이 모듈은 **계산만** 한다(화면 문구·보류 판정은 `shipping_ratio`).
"""
from __future__ import annotations

import json
import logging
import math
import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "shipping"
DEFAULT_PROVIDER = "percenty"
DEFAULT_DIVISOR = 6000.0
MODES = ("sea", "air")
BULKY_KG = 20.0
BULKY_SUM_CM = 150.0
BULKY_SIDE_CM = 100.0
LEGACY_ENVS = ("SHIPPING_RATE_KRW_PER_KG_CN", "SHIPPING_RATE_KRW_PER_KG_CN_DIRECT", "SHIPPING_RATE_KRW_PER_KG_CN_FORWARDER")

_lock = threading.Lock()
_cache: Dict[str, Any] = {"sig": None, "tables": {}}
_warned: set = set()


def _signature() -> tuple:
    try:
        return tuple(sorted((p.name, p.stat().st_mtime) for p in DATA_DIR.glob("*.json")))
    except Exception:
        return ()


def tables() -> Dict[str, Dict[str, Any]]:
    """`{provider: {version, source, captured_at, label, modes, addons}}` — provider마다 캡처일이 가장 늦은 파일."""
    sig = _signature()
    with _lock:
        if _cache["sig"] == sig:
            return _cache["tables"]
    out: Dict[str, Dict[str, Any]] = {}
    for p in sorted(DATA_DIR.glob("*.json")) if DATA_DIR.exists() else []:
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("[배송비 엔진] 요율표 읽기 실패 %s: %s", p.name, exc)
            continue
        for name, prov in (raw.get("providers") or {}).items():
            cur = out.get(name)
            if cur and str(cur.get("captured_at") or "") >= str(raw.get("captured_at") or ""):
                continue
            out[name] = dict(prov, version=raw.get("version") or p.stem, source=raw.get("source") or "",
                             captured_at=raw.get("captured_at") or "", file=p.name)
    with _lock:
        _cache.update(sig=sig, tables=out)
    return out


def table(provider: str = DEFAULT_PROVIDER) -> Optional[Dict[str, Any]]:
    return tables().get(provider or DEFAULT_PROVIDER)


def warn_legacy_env() -> List[str]:
    """폐기된 kg당 요율 env가 남아 있으면 경고 로그(한 번) — 값은 쓰지 않는다."""
    hit = [n for n in LEGACY_ENVS if os.getenv(n, "").strip()]
    for n in hit:
        if n not in _warned:
            _warned.add(n)
            logger.warning("[배송비 엔진] %s는 폐기됐어요 — 무시합니다(요율은 data/shipping 요율표).", n)
    return hit


def ceil_step(x: float, step: float) -> float:
    """step 단위 올림, 최소 한 단위(1.72 → 2.0 · 2.0 → 2.0 · 0.2 → 0.5)."""
    units = max(1, math.ceil(round(float(x) / step, 9)))
    return round(units * step, 3)


def cbm(dims_cm: Optional[List[float]]) -> float:
    """가로×세로×높이(m) — 소수 셋째 자리에서 올려 둘째 자리(0.3125 → 0.32)."""
    if not dims_cm:
        return 0.0
    v = dims_cm[0] * dims_cm[1] * dims_cm[2] / 1_000_000
    return math.ceil(round(v * 100, 6)) / 100


def price(mode_tbl: Dict[str, Any], qty: float) -> Dict[str, Any]:
    """`{qty, krw, estimated, why}` — qty는 step 단위로 올린 청구 단위(kg·cbm)."""
    step = float(mode_tbl.get("step") or 0.5)
    rows = sorted((float(q), float(k)) for q, k in mode_tbl["rows"])
    q = ceil_step(qty, step)
    table_map = {r[0]: r[1] for r in rows}
    if q in table_map:
        return {"qty": q, "krw": round(table_map[q]), "estimated": False, "why": ""}
    if q < rows[0][0]:
        return {"qty": rows[0][0], "krw": round(rows[0][1]), "estimated": True,
                "why": f"표 최소 {rows[0][0]:g}{mode_tbl.get('unit', '')} 요금 적용"}
    (q1, k1), (q2, k2) = rows[-2], rows[-1]
    slope = (k2 - k1) / (q2 - q1)                      # 단위(kg·cbm)당
    over = mode_tbl.get("over") or {}
    top = float(over.get("from") or 0) or None
    if top and q > top:
        base = k2 + slope * (top - q2)
        krw = base + float(over["add_krw"]) * (q - top) / float(over.get("step") or step)
        why = f"표 밖 — {q2:g}까지 표 · {top:g}까지 기울기 외삽 · 이후 {over.get('note', '')}"
    else:
        krw = k2 + slope * (q - q2)
        why = f"표 밖 — 마지막 두 행 기울기(0.5당 {slope * 0.5:,.0f}원)로 외삽"
    return {"qty": q, "krw": round(krw), "estimated": True, "why": why}


def bulky_reasons(weight_kg: float, dims_cm: Optional[List[float]], pkg_m3: float = 0.0) -> List[str]:
    """경동택배/기타화물 이관 사유(없으면 빈 목록). 포장 부피(㎥)만 있으면 정육면체로 본 한 변으로 세 변 합을 잰다."""
    why = []
    if weight_kg and weight_kg >= BULKY_KG:
        why.append(f"실중량 {weight_kg:g}kg ≥ {BULKY_KG:g}kg")
    if dims_cm:
        if sum(dims_cm) >= BULKY_SUM_CM:
            why.append(f"세 변 합 {sum(dims_cm):g}cm ≥ {BULKY_SUM_CM:g}cm")
        if max(dims_cm) >= BULKY_SIDE_CM:
            why.append(f"한 변 {max(dims_cm):g}cm ≥ {BULKY_SIDE_CM:g}cm")
    if pkg_m3:
        side = (pkg_m3 * 1_000_000) ** (1 / 3)
        if side * 3 >= BULKY_SUM_CM:
            why.append(f"포장 부피 {pkg_m3:g}㎥(정육면체 한 변 {side:.0f}cm · 세 변 합 {side * 3:.0f}cm) ≥ {BULKY_SUM_CM:g}cm")
    return why


def addons_total(prov: Dict[str, Any], keys: List[str]) -> Dict[str, Any]:
    """부가서비스 합계 — 「~」(하한 `min_krw`)이 섞이면 at_least=True."""
    by = {a["key"]: a for a in prov.get("addons") or []}
    krw, at_least, picked = 0, False, []
    for k in keys or []:
        a = by.get(k)
        if not a:
            continue
        if "min_krw" in a:
            krw += int(a["min_krw"])
            at_least = True
            picked.append(f"{a['label']} {int(a['min_krw']):,}원~")
        else:
            krw += int(a.get("krw") or 0)
            picked.append(f"{a['label']} {int(a.get('krw') or 0):,}원")
    return {"krw": krw, "at_least": at_least, "items": picked}


def quote(size: Dict[str, Any], *, mode: str = "sea", divisor: float = DEFAULT_DIVISOR,
          provider: str = DEFAULT_PROVIDER, addons: Optional[List[str]] = None,
          lcl: bool = False) -> Dict[str, Any]:
    """한 상품의 배대지 운임. `size = {weight_kg, dims_cm, pkg_m3}`.

    → `{ok, mode, actual:{kg, krw}, volume:{kg, krw}, applied:{kg, krw, basis}, estimated, addons, bulky, lcl}`.
    표가 없으면 `{ok: False, why}`.
    """
    prov = table(provider)
    if not prov:
        return {"ok": False, "why": f"요율표 파일 없음(data/shipping — {provider})"}
    mode = mode if mode in MODES else "sea"
    mt = prov["modes"][mode]
    w = float(size.get("weight_kg") or 0)
    dims = size.get("dims_cm")
    pkg = float(size.get("pkg_m3") or 0)
    vol_kg = (dims[0] * dims[1] * dims[2] / divisor) if dims else (pkg * 1_000_000 / divisor if pkg else 0.0)
    actual = price(mt, w) if w else None
    volume = price(mt, vol_kg) if vol_kg else None
    use_vol = bool(volume and (not actual or volume["krw"] > actual["krw"]))
    applied = dict(volume if use_vol else actual) if (actual or volume) else None
    if applied:
        applied["basis"] = "부피 무게" if use_vol else "실제 무게"
    ad = addons_total(prov, addons or [])
    out: Dict[str, Any] = {
        "ok": bool(applied), "mode": mode, "mode_label": mt.get("label") or mode, "provider": provider,
        # 셀러 화면엔 display_name만(「기본 배대지」) — label·source는 내부 기록(경쟁 서비스명 노출 금지)
        "provider_label": prov.get("display_name") or "기본 배대지", "version": prov.get("version"),
        "table_date": prov.get("captured_at") or "",                       # 셀러 화면용(버전 이름엔 배대지 키가 들어 있다)
        "actual": {"kg": w, **actual} if actual else None,
        "volume": {"kg": round(vol_kg, 2), **volume} if volume else None,
        "applied": applied, "estimated": bool(applied and applied["estimated"]),
        "addons": ad, "bulky": bulky_reasons(w, dims, pkg), "lcl": None, "divisor": divisor,
    }
    if not applied:
        out["why"] = "무게·부피를 몰라 계산하지 못했어요"
    if lcl or out["bulky"]:
        out["lcl"] = lcl_quote(prov, dims, pkg)
    return out


def lcl_quote(prov: Dict[str, Any], dims_cm: Optional[List[float]], pkg_m3: float = 0.0) -> Optional[Dict[str, Any]]:
    """해운 LCL(cbm) — 포장 부피(包装体积 ㎥ = 상자)가 있으면 그것, 없으면 치수로. 둘 다 없으면 None."""
    mt = (prov.get("modes") or {}).get("lcl")
    if not mt:
        return None
    v = (math.ceil(round(pkg_m3 * 100, 6)) / 100) if pkg_m3 else cbm(dims_cm)
    if not v:
        return None
    p = price(mt, v)
    return {"cbm": v, **p, "label": mt.get("label") or "LCL", "notice": mt.get("notice") or "",
            "includes": mt.get("includes") or "", "excludes": mt.get("excludes") or ""}


# ── 셀러 설정(/seller/settings/shipping) — 공유 마켓 사용자(오너·가족)는 한 벌, 그 밖은 셀러별 ──────────────────
_SETTINGS_KEY = "ship_settings:"
DEFAULT_SETTINGS = {"provider": DEFAULT_PROVIDER, "default_mode": "sea", "vol_divisor": None,
                    "addons": [], "business": False, "lcl_threshold_cbm": 0.5}


def _scope(seller_id: str, shared: Optional[bool]) -> str:
    if shared is None:
        from .shipping_ratio import _session_shared
        shared = _session_shared()
    return "shared" if shared else str(seller_id or "default")


def get_settings(seller_id: str = "", shared: Optional[bool] = None) -> Dict[str, Any]:
    out = dict(DEFAULT_SETTINGS)
    try:
        from src.db import image_translate_queue_pg as st
        saved = st.state_get(_SETTINGS_KEY + _scope(seller_id, shared)) or {}
        out.update({k: v for k, v in saved.items() if k in DEFAULT_SETTINGS})
    except Exception as exc:
        logger.debug("[배송비 엔진] 설정 읽기 실패(기본값): %s", exc)
    return out


def save_settings(seller_id: str, values: Dict[str, Any], shared: Optional[bool] = None) -> Dict[str, Any]:
    cur = get_settings(seller_id, shared)
    prov = str(values.get("provider") or cur["provider"])
    if prov not in tables():
        raise ValueError(f"배대지 「{prov}」 요율표가 없어요")
    mode = str(values.get("default_mode") or cur["default_mode"])
    if mode not in MODES:
        raise ValueError("기본 모드는 해운(sea) 또는 항공(air)")
    div = values.get("vol_divisor")
    div = float(div) if div not in (None, "") else None
    if div is not None and not (1000 <= div <= 10000):
        raise ValueError("부피 제수는 1000~10000 사이")
    keys = {a["key"] for a in (tables()[prov].get("addons") or [])}
    thr = float(values.get("lcl_threshold_cbm") or cur["lcl_threshold_cbm"] or 0.5)
    new = {"provider": prov, "default_mode": mode, "vol_divisor": div,
           "addons": [k for k in (values.get("addons") or []) if k in keys],
           "business": bool(values.get("business")), "lcl_threshold_cbm": thr}
    from src.db import image_translate_queue_pg as st
    st.state_set(_SETTINGS_KEY + _scope(seller_id, shared), new)
    return new


def divisor(settings: Dict[str, Any]) -> float:
    """부피 제수 — 셀러 설정 > env `SHIPPING_VOL_DIVISOR` > 6000."""
    if settings.get("vol_divisor"):
        return float(settings["vol_divisor"])
    try:
        v = float(os.getenv("SHIPPING_VOL_DIVISOR", "").strip() or 0)
    except ValueError:
        v = 0
    return v if v > 0 else DEFAULT_DIVISOR
