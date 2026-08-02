"""src/pricing/policy.py — 가격 정책 단일 소스 (v87-S3).

왜: 마진율·수수료·배송비·환율 기준이 지금은 `calculator.py` 안의 env 기본값으로 흩어져 있어서,
셀러가 바꿀 수 없고 **코드를 고쳐야만** 값이 바뀐다. 이걸 셀러별 정책(settings.policy jsonb)으로 옮긴다.

마이그레이션 계약(중요): **디폴트 정책 = 현행 상수**다. 즉 정책을 한 번도 저장하지 않은 셀러의 계산
결과는 이관 전과 **완전히 같아야** 한다. 그래서 디폴트를 새로 적지 않고 현행과 같은 env 조회
(`_env_float`)로 만든다 — 값이 두 군데로 갈라지면 그게 곧 회귀다.

블랙박스 금지(우리 차별점): 판매가가 어떻게 나왔는지 셀러가 **식과 중간값을 다 볼 수 있어야** 한다.
그래서 `compute_sell_price`는 결과 숫자만이 아니라 단계별 내역(`steps`)과 식 문자열을 함께 돌려준다.
"""
from __future__ import annotations

import copy
import math
import os
from typing import Any

# ── 소싱국별 기본 해외배송비(원). 오너 지정 범위 11,000~15,000 안에서 거리·요율 순.
_DEFAULT_INTL_SHIP_KRW = {"US": 15000, "JP": 11000, "CN": 11000, "EU": 15000}

# 마켓 수수료 기본값 = 각 마켓 공표 수수료(현행 calculator._market_fee와 동일 소스).
_MARKET_FEE_ENV = {
    "coupang": ("PRICING_FEE_COUPANG", 0.108),
    "smartstore": ("PRICING_FEE_SMARTSTORE", 0.0585),
    "11st": ("PRICING_FEE_11ST", 0.12),
    "gmarket": ("PRICING_FEE_GMARKET", 0.12),
}

# 화면에 그대로 노출하는 식(블랙박스 금지). 코드와 표기가 갈라지지 않게 여기 한 곳에서만 쓴다.
FORMULA_TEXT = (
    "판매가 = (매입가 × 환율 + 해외배송비 + 더하기마진) "
    "÷ (1 − 퍼센트마진 − 마켓수수료 − 카드수수료)"
)

ROUND_UNITS = (1, 10, 100)
REP_PRICE_BASES = ("min", "max", "representative")
CUSTOMS_MODES = ("not_applicable", "included")
FX_MODES = ("auto", "fixed")


def _env_float(name: str, default: float) -> float:
    """현행 calculator와 **같은 방식**으로 읽는다(디폴트가 갈라지면 이관이 곧 회귀)."""
    try:
        return float(os.getenv(name, default))
    except Exception:
        return float(default)


def default_policy() -> dict:
    """현행 동작과 동일한 시드 디폴트. 저장된 정책이 없을 때 이 값이 쓰인다."""
    return {
        "version": 1,
        "margin": {
            "percent_margin": _env_float("PRICING_DEFAULT_TARGET_MARGIN_PCT", 30.0),
            "plus_margin_krw": 0.0,
            "min_margin_guard_pct": _env_float("PRICING_MIN_MARGIN_GUARD_PCT", 15.0),
            "ad_budget_pct": _env_float("PRICING_DEFAULT_AD_BUDGET_PCT", 5.0),
        },
        "shipping": {
            # 소싱국별 해외배송비(원). 무게 기준 요율은 현행 값을 그대로 승계한다.
            "intl_ship_krw": dict(_DEFAULT_INTL_SHIP_KRW),
            "intl_ship_per_kg_krw": _env_float("PRICING_INTL_SHIPPING_PER_KG_KRW", 18000.0),
            "default_weight_kg": _env_float("PRICING_DEFAULT_WEIGHT_KG", 0.5),
            "domestic_kind": "paid",        # free | paid
            "return_fee_krw": 0.0,
            "exchange_fee_krw": 0.0,
            "initial_ship_fee_krw": 0.0,    # 쿠팡 초도배송비
        },
        "fees": {
            "card_pct": _env_float("PRICING_PAYMENT_FEE", 0.033) * 100.0,
            "market_pct": {k: _env_float(env, d) * 100.0 for k, (env, d) in _MARKET_FEE_ENV.items()},
        },
        "display": {
            "discount_pct": 0.0,            # 마켓 표기 할인율
            "round_unit": 100,              # 100원 / 10원 올림
            "rep_price_base": "representative",
        },
        "customs": {
            # PCC(통관고유부호) 파이프라인 연동 지점 — 이 화면은 모드만 정한다.
            "mode": "not_applicable",
            "vat_pct": _env_float("PRICING_VAT", 0.10) * 100.0,
        },
        "fx": {
            "mode": "auto",                 # auto(실시간) | fixed(고정값)
            "fixed_rates": {},              # {"USD": 1380.0, ...} mode=fixed일 때만 사용
        },
    }


def merge_policy(stored: dict | None) -> dict:
    """저장 정책을 디폴트 위에 얹는다. 없는 키는 디폴트 유지(부분 저장 안전)."""
    base = default_policy()
    if not isinstance(stored, dict):
        return base

    def _deep(dst: dict, src: dict) -> dict:
        for k, v in src.items():
            if isinstance(v, dict) and isinstance(dst.get(k), dict):
                _deep(dst[k], v)
            else:
                dst[k] = v
        return dst

    return _deep(base, copy.deepcopy(stored))


def market_fee_pct(policy: dict, market: str) -> float:
    """마켓 수수료(%). 모르는 마켓은 쿠팡 기준 — 현행 _market_fee와 같은 폴백."""
    table = ((policy or {}).get("fees") or {}).get("market_pct") or {}
    m = (market or "").strip().lower()
    if m in table:
        return float(table[m])
    return float(table.get("coupang", default_policy()["fees"]["market_pct"]["coupang"]))


def intl_ship_krw(policy: dict, country: str) -> float:
    """소싱국 해외배송비(원). 미지정 국가는 0 — **추측해서 얹지 않는다**(정직)."""
    table = ((policy or {}).get("shipping") or {}).get("intl_ship_krw") or {}
    return float(table.get((country or "").strip().upper(), 0.0))


def round_up(value: float, unit: int) -> int:
    """표기 단위 올림.

    정수용 `(v + u - 1) // u` 트릭을 float에 쓰면 안 된다 — 88550.98을 10원 단위로 올리면
    (88550.98+9)//10*10 = 88550으로 **내려간다**(판매가가 실제로 틀리는 값). math.ceil로 간다.
    """
    u = int(unit or 1)
    if u <= 1:
        return int(math.ceil(value))
    return int(math.ceil(value / u) * u)


def validate_policy(policy: dict) -> list[str]:
    """저장 전 검증. 반환이 비어 있어야 저장 가능(조용한 잘못된 값 금지)."""
    errs: list[str] = []
    p = policy or {}
    mg = p.get("margin") or {}
    fe = p.get("fees") or {}
    dp = p.get("display") or {}

    pm = float(mg.get("percent_margin", 0) or 0)
    card = float(fe.get("card_pct", 0) or 0)
    if not (0 <= pm < 100):
        errs.append("퍼센트 마진은 0 이상 100 미만이어야 합니다.")
    if float(mg.get("plus_margin_krw", 0) or 0) < 0:
        errs.append("더하기 마진은 0 이상이어야 합니다.")
    if not (0 <= card < 100):
        errs.append("카드 수수료는 0 이상 100 미만이어야 합니다.")
    for k, v in (fe.get("market_pct") or {}).items():
        if not (0 <= float(v or 0) < 100):
            errs.append(f"{k} 마켓 수수료는 0 이상 100 미만이어야 합니다.")
        # 분모가 0 이하가 되면 판매가가 무한대로 튄다 — 저장 자체를 막는다.
        if pm + card + float(v or 0) >= 100:
            errs.append(f"{k}: 퍼센트마진+카드+마켓 수수료 합이 100%를 넘어 판매가를 계산할 수 없습니다.")
    if int(dp.get("round_unit", 100) or 100) not in ROUND_UNITS:
        errs.append("올림 단위는 1 / 10 / 100원 중 하나여야 합니다.")
    if (dp.get("rep_price_base") or "representative") not in REP_PRICE_BASES:
        errs.append("옵션 대표가 기준 값이 올바르지 않습니다.")
    if ((p.get("customs") or {}).get("mode") or "not_applicable") not in CUSTOMS_MODES:
        errs.append("관부가세 모드 값이 올바르지 않습니다.")
    if ((p.get("fx") or {}).get("mode") or "auto") not in FX_MODES:
        errs.append("환율 모드 값이 올바르지 않습니다.")
    return errs


def compute_sell_price(policy: dict, *, source_price: float, fx_rate: float,
                       market: str, country: str = "") -> dict:
    """정책대로 판매가를 계산하고 **중간값까지 전부** 돌려준다(블랙박스 금지).

    식: (매입가 × 환율 + 해외배송비 + 더하기마진) ÷ (1 − 퍼센트마진 − 마켓수수료 − 카드수수료)
    """
    p = merge_policy(policy)
    mg, fe, dp = p["margin"], p["fees"], p["display"]

    cost_krw = float(source_price or 0) * float(fx_rate or 0)
    ship = intl_ship_krw(p, country)
    plus = float(mg.get("plus_margin_krw", 0) or 0)
    numerator = cost_krw + ship + plus

    pct = float(mg.get("percent_margin", 0) or 0) / 100.0
    mfee = market_fee_pct(p, market) / 100.0
    card = float(fe.get("card_pct", 0) or 0) / 100.0
    denominator = 1.0 - pct - mfee - card

    if denominator <= 0:
        # 저장 검증에서 막지만, 옛 정책이 남아 있을 수 있으니 계산부에서도 정직하게 실패한다.
        return {"ok": False, "reason": "수수료 합이 100%를 넘어 판매가를 계산할 수 없습니다.",
                "formula": FORMULA_TEXT, "steps": [], "sell_price": None}

    raw = numerator / denominator
    unit = int(dp.get("round_unit", 100) or 100)
    sell = round_up(raw, unit)
    discount = float(dp.get("discount_pct", 0) or 0)
    # 마켓 표기 할인율: 할인 후가 sell이 되도록 표기가를 역산한다(고객이 보는 '정가').
    listed = round_up(sell / (1.0 - discount / 100.0), unit) if 0 < discount < 100 else sell

    return {
        "ok": True,
        "formula": FORMULA_TEXT,
        "steps": [
            {"label": "매입가 × 환율", "value": round(cost_krw, 2)},
            {"label": f"해외배송비({country or '미지정'})", "value": ship},
            {"label": "더하기 마진", "value": plus},
            {"label": "분자 합", "value": round(numerator, 2)},
            {"label": "퍼센트 마진", "value": f"{pct * 100:.2f}%"},
            {"label": f"마켓 수수료({market or '-'})", "value": f"{mfee * 100:.2f}%"},
            {"label": "카드 수수료", "value": f"{card * 100:.2f}%"},
            {"label": "분모 (1 − 합)", "value": round(denominator, 4)},
            {"label": f"올림({unit}원)", "value": sell},
        ],
        "cost_krw": round(cost_krw, 2),
        "shipping_krw": ship,
        "plus_margin_krw": plus,
        "denominator": round(denominator, 6),
        "raw_price": round(raw, 2),
        "sell_price": sell,
        "listed_price": listed,
        "discount_pct": discount,
    }
