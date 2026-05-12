from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from statistics import mean, median
from typing import Iterable


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except Exception:
        return float(default)


def _to_krw_rate(currency: str) -> float:
    cur = (currency or "USD").upper()
    if cur == "KRW":
        return 1.0
    fallback = {
        "USD": _env_float("FALLBACK_USD_KRW", 1350.0),
        "JPY": _env_float("FALLBACK_JPY_KRW", 9.2),
        "EUR": _env_float("FALLBACK_EUR_KRW", 1450.0),
        "CNY": _env_float("FALLBACK_CNY_KRW", 187.0),
    }
    try:
        from src.utils.exchange_rate import get_exchange_rates

        rates = get_exchange_rates() or {}
        if f"{cur}KRW" in rates:
            return float(rates[f"{cur}KRW"])
        if cur in rates:
            return float(rates[cur])
    except Exception:
        pass
    return float(fallback.get(cur, fallback["USD"]))


def _customs_pct(category: str) -> float:
    c = (category or "").strip().lower()
    fashion = {"의류", "패션", "fashion", "hoodie", "후드티"}
    electronics = {"전자", "electronics"}
    food = {"식품", "food"}
    beauty = {"뷰티", "beauty", "cosmetics"}
    if c in fashion:
        return _env_float("PRICING_CUSTOMS_FASHION", 0.13)
    if c in electronics:
        return _env_float("PRICING_CUSTOMS_ELECTRONICS", 0.08)
    if c in food:
        return _env_float("PRICING_CUSTOMS_FOOD", 0.30)
    if c in beauty:
        return _env_float("PRICING_CUSTOMS_BEAUTY", 0.08)
    return _env_float("PRICING_CUSTOMS_DEFAULT", 0.08)


def _market_fee(market: str) -> float:
    m = (market or "").strip().lower()
    defaults = {
        "coupang": _env_float("PRICING_FEE_COUPANG", 0.108),
        "smartstore": _env_float("PRICING_FEE_SMARTSTORE", 0.0585),
        "11st": _env_float("PRICING_FEE_11ST", 0.12),
        "gmarket": _env_float("PRICING_FEE_GMARKET", 0.12),
    }
    return float(defaults.get(m, defaults["coupang"]))


@dataclass
class PriceBreakdown:
    cost_krw: float
    shipping_krw: float
    customs_krw: float
    vat_krw: float
    total_landed: float
    market_fee_pct: float
    payment_fee_pct: float
    ad_budget_pct: float
    target_margin_pct: float
    calculated_price: float
    competitor_min: float | None
    competitor_avg: float | None
    actual_market_min: float | None
    actual_market_median: float | None
    actual_market_max: float | None
    decision_source: str
    decision_detail: str
    minimum_margin_price: int
    loss_warning: bool
    suggested_price: int
    margin_actual_pct: float

    def to_dict(self) -> dict:
        return asdict(self)


def calculate_listing_price(
    *,
    source_price: float,
    source_currency: str,
    weight_kg: float,
    market: str,
    category: str,
    target_margin_pct: float | None = None,
    ad_budget_pct: float | None = None,
    competitor_prices_krw: Iterable[float] | None = None,
    actual_market_prices_krw: Iterable[float] | None = None,
) -> PriceBreakdown:
    target_margin_pct = float(
        target_margin_pct
        if target_margin_pct is not None
        else _env_float("PRICING_DEFAULT_TARGET_MARGIN_PCT", 30.0)
    )
    ad_budget_pct = float(
        ad_budget_pct
        if ad_budget_pct is not None
        else _env_float("PRICING_DEFAULT_AD_BUDGET_PCT", 5.0)
    )
    weight_kg = float(weight_kg if weight_kg is not None else _env_float("PRICING_DEFAULT_WEIGHT_KG", 0.5))
    payment_fee_pct = _env_float("PRICING_PAYMENT_FEE", 0.033)
    vat_pct = _env_float("PRICING_VAT", 0.10)
    intl_shipping_per_kg = _env_float("PRICING_INTL_SHIPPING_PER_KG_KRW", 18000.0)
    competitor_discount = _env_float("PRICING_COMPETITOR_DISCOUNT", 0.97)
    min_margin_guard_pct = _env_float("PRICING_MIN_MARGIN_GUARD_PCT", 15.0)
    actual_discount = _env_float("PRICING_ACTUAL_DISCOUNT", 0.97)

    cost_krw = float(source_price) * _to_krw_rate(source_currency)
    shipping_krw = max(weight_kg, 0.0) * intl_shipping_per_kg
    customs_krw = (cost_krw + shipping_krw) * _customs_pct(category)
    landed_cost = cost_krw + shipping_krw + customs_krw
    vat_krw = landed_cost * vat_pct
    total_landed = landed_cost + vat_krw

    market_fee_pct = _market_fee(market)
    deduction = market_fee_pct + payment_fee_pct + (ad_budget_pct / 100.0)
    denominator = max(1.0 - deduction, 0.01)
    calculated_price = total_landed * (1.0 + target_margin_pct / 100.0) / denominator

    prices = [float(p) for p in (competitor_prices_krw or []) if p]
    competitor_min = min(prices) if prices else None
    competitor_avg = mean(prices) if prices else None
    actual_prices = [float(p) for p in (actual_market_prices_krw or []) if p]
    actual_market_min = min(actual_prices) if actual_prices else None
    actual_market_median = median(actual_prices) if actual_prices else None
    actual_market_max = max(actual_prices) if actual_prices else None

    minimum_margin_price = total_landed * (1.0 + min_margin_guard_pct / 100.0)
    suggested = calculated_price
    decision_source = "calculated"
    decision_detail = "원가+비용+목표마진 계산값"

    if actual_market_median:
        candidate = actual_market_median * actual_discount
        suggested = candidate
        decision_source = "actual_market_median"
        decision_detail = f"실측 시장가 중앙값의 {int(actual_discount * 100)}%"
    elif competitor_min:
        candidate = competitor_min * competitor_discount
        if candidate >= minimum_margin_price:
            suggested = candidate
            decision_source = "competitor_distribution"
            decision_detail = "경쟁사 최저가 기반 할인 적용"

    net_revenue = suggested * (1.0 - deduction)
    margin_actual_pct = ((net_revenue - total_landed) / max(net_revenue, 1.0)) * 100.0
    loss_warning = bool(os.getenv("PRICING_LOSS_WARNING_ENABLED", "1") == "1" and margin_actual_pct < 0)

    return PriceBreakdown(
        cost_krw=cost_krw,
        shipping_krw=shipping_krw,
        customs_krw=customs_krw,
        vat_krw=vat_krw,
        total_landed=total_landed,
        market_fee_pct=market_fee_pct,
        payment_fee_pct=payment_fee_pct,
        ad_budget_pct=ad_budget_pct,
        target_margin_pct=target_margin_pct,
        calculated_price=calculated_price,
        competitor_min=competitor_min,
        competitor_avg=competitor_avg,
        actual_market_min=actual_market_min,
        actual_market_median=actual_market_median,
        actual_market_max=actual_market_max,
        decision_source=decision_source,
        decision_detail=decision_detail,
        minimum_margin_price=int(round(minimum_margin_price / 100.0) * 100),
        loss_warning=loss_warning,
        suggested_price=int(round(suggested / 100.0) * 100),
        margin_actual_pct=round(margin_actual_pct, 2),
    )
