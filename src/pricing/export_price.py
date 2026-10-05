"""R2·R3(오너 2026-10-05 역직구) — 수출 마켓 판매가 엔진(Qoo10 재팬 · 쇼피 공용 틀).

    판매가(원) = (국내 소싱가 + 물류비) ÷ (1 − 마켓 수수료율 − 마진율)
    판매가(현지 통화) = 판매가(원) ÷ 환율(원/현지 1단위), 올림

- 마진율 `EXPORT_MARGIN_PCT`(기본 27 — 오너 지정). 마켓 수수료율 `QOO10_FEE_PCT` / `SHOPEE_FEE_PCT` — **기본값 없음**
  (모르는 수수료로 매긴 값은 빈칸보다 나쁘다 → 「수수료 미설정 — 가격 산정 보류」).
- 물류비 = 청구 무게(kg) × `EXPORT_SHIP_KRW_PER_KG_<국가>`(JP·SG·…) — **기본값 없음**. 무게를 못 읽으면 보류(추정 0).
- 일본: 판매가 ≤ 10,000엔이면 「1만 엔 이하 — 소액 면세 대상 가능」 플래그(과세가격 판정은 세관 — 플래그만).
- 환율은 `data_aggregator.get_fx_rates()`(원/외화 1단위) — 못 받으면 보류(임의 환산 금지).
"""
from __future__ import annotations

import math
import os
from typing import Any, Dict, Optional

MARKET_FEE_ENV = {"qoo10": "QOO10_FEE_PCT", "shopee": "SHOPEE_FEE_PCT"}
MARKET_COUNTRY = {"qoo10": ("JP", "JPY"), "shopee": ("SG", "SGD")}
DUTY_FREE_JPY = 10000


def _env_pct(name: str) -> Optional[float]:
    raw = os.getenv(name, "").strip()
    try:
        return float(raw) if raw else None
    except ValueError:
        return None


def margin_pct() -> float:
    v = _env_pct("EXPORT_MARGIN_PCT")
    return 27.0 if v is None else v


def ship_env(country: str) -> str:
    return f"EXPORT_SHIP_KRW_PER_KG_{country}"


def _fx(cur: str, fx_rates: Optional[dict]) -> Optional[float]:
    rates = fx_rates
    if rates is None:
        try:
            from src.seller_console.data_aggregator import get_fx_rates
            rates = get_fx_rates()
        except Exception:
            rates = {}
    v = (rates or {}).get(cur)
    try:
        return float(v) if v else None
    except (TypeError, ValueError):
        return None


def quote(cost_krw: Any, *, market: str, weight_kg: Optional[float], fx_rates: Optional[dict] = None) -> Dict[str, Any]:
    """`{state: ok|unknown, price, currency, krw, breakdown, why, duty_free, line}` — 못 내면 state=unknown + why."""
    country, cur = MARKET_COUNTRY.get(market, ("", ""))
    fee_env = MARKET_FEE_ENV.get(market, "")
    try:
        cost = float(str(cost_krw).replace(",", "")) if cost_krw not in (None, "") else 0.0
    except ValueError:
        cost = 0.0
    if not country:
        return {"state": "unknown", "why": f"수출 마켓이 아니에요({market})"}
    if cost <= 0:
        return {"state": "unknown", "why": "국내 소싱가(원)가 없어요"}
    fee = _env_pct(fee_env)
    if fee is None:
        return {"state": "unknown", "why": f"수수료 미설정 — 가격 산정 보류({fee_env})"}
    rate = _env_pct(ship_env(country))
    if rate is None:
        return {"state": "unknown", "why": f"물류 요율 미설정 — 가격 산정 보류({ship_env(country)})"}
    if not weight_kg or weight_kg <= 0:
        return {"state": "unknown", "why": "무게 미확인 — 물류비를 못 내 가격 산정 보류(치수·무게를 읽거나 직접 입력)"}
    m = margin_pct()
    denom = 1 - fee / 100 - m / 100
    if denom <= 0:
        return {"state": "unknown", "why": f"수수료 {fee:g}% + 마진 {m:g}%가 100%를 넘어요"}
    fx = _fx(cur, fx_rates)
    if not fx:
        return {"state": "unknown", "why": f"환율 없음({cur}) — 임의 환산 안 함"}
    ship = round(weight_kg * rate)
    krw = (cost + ship) / denom
    price = math.ceil(krw / fx)
    out = {"state": "ok", "price": price, "currency": cur, "krw": round(krw),
           "breakdown": {"cost_krw": round(cost), "ship_krw": ship, "weight_kg": weight_kg, "ship_rate": rate,
                         "fee_pct": fee, "margin_pct": m, "fx": fx},
           "why": "", "duty_free": None}
    if cur == "JPY":
        out["duty_free"] = price <= DUTY_FREE_JPY
    out["line"] = (f"{price:,} {cur} — 소싱가 {round(cost):,}원 + 물류 {ship:,}원({weight_kg:g}kg × {rate:,.0f}원) · "
                   f"수수료 {fee:g}% · 마진 {m:g}% · 환율 {fx:g}"
                   + (" · 1만 엔 이하(소액 면세 대상 가능)" if out["duty_free"] else
                      (" · 1만 엔 초과(면세 아님)" if out["duty_free"] is False else "")))
    return out
