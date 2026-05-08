"""src/pricing/margin_guard.py — Phase 140 마진 가드."""
from __future__ import annotations

import logging
import os
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

logger = logging.getLogger(__name__)


class MarginGuard:
    """후보 가격의 최소 마진율을 검증한다."""

    def __init__(self, min_margin_pct: Optional[Decimal] = None):
        self.min_margin_pct = Decimal(
            str(min_margin_pct if min_margin_pct is not None else os.getenv("PRICING_MIN_MARGIN_PCT", "15"))
        )

    def evaluate(self, product_row: dict, candidate_price_krw: Decimal) -> dict:
        candidate = Decimal(str(candidate_price_krw)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        fee_pct = Decimal(str(product_row.get("fee_pct") or product_row.get("marketplace_fee_pct") or "10"))
        shipping_cost = Decimal(str(product_row.get("shipping_cost_krw") or product_row.get("domestic_shipping") or "0"))
        ad_cost = Decimal(str(product_row.get("ad_cost_krw") or product_row.get("ad_cost_estimate_krw") or "0"))

        sourcing_krw = self._sourcing_cost_krw(product_row)
        fee_cost = (candidate * fee_pct / Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        total_cost = sourcing_krw + fee_cost + shipping_cost + ad_cost

        if candidate <= 0:
            margin_pct = Decimal("-100")
        else:
            margin_pct = ((candidate - total_cost) / candidate * Decimal("100")).quantize(Decimal("0.01"))

        allowed = margin_pct >= self.min_margin_pct
        reason = "ok" if allowed else f"마진율 {margin_pct}% < 최소 {self.min_margin_pct}%"

        if not allowed:
            self._notify_rejected(product_row, candidate, margin_pct)

        return {
            "allowed": allowed,
            "reason": reason,
            "candidate_price_krw": int(candidate),
            "margin_pct": float(margin_pct),
            "min_margin_pct": float(self.min_margin_pct),
            "cost_breakdown": {
                "sourcing_cost_krw": int(sourcing_krw),
                "fee_cost_krw": int(fee_cost),
                "shipping_cost_krw": int(shipping_cost),
                "ad_cost_krw": int(ad_cost),
                "total_cost_krw": int(total_cost),
            },
        }

    def required_price_for_margin(self, product_row: dict, target_margin_pct: Decimal) -> Decimal:
        pct = Decimal(str(target_margin_pct))
        fee_pct = Decimal(str(product_row.get("fee_pct") or product_row.get("marketplace_fee_pct") or "10"))
        shipping_cost = Decimal(str(product_row.get("shipping_cost_krw") or product_row.get("domestic_shipping") or "0"))
        ad_cost = Decimal(str(product_row.get("ad_cost_krw") or product_row.get("ad_cost_estimate_krw") or "0"))
        sourcing_krw = self._sourcing_cost_krw(product_row)

        denominator = Decimal("1") - (fee_pct / Decimal("100")) - (pct / Decimal("100"))
        if denominator <= 0:
            denominator = Decimal("0.01")
        required = (sourcing_krw + shipping_cost + ad_cost) / denominator
        return required.quantize(Decimal("1"), rounding=ROUND_HALF_UP)

    def _sourcing_cost_krw(self, product_row: dict) -> Decimal:
        buy_price = Decimal(str(product_row.get("buy_price") or product_row.get("sourcing_price") or "0"))
        currency = str(product_row.get("buy_currency") or product_row.get("currency") or "KRW").upper()
        if currency == "KRW":
            return buy_price

        fx_rate = product_row.get("fx_rate")
        if fx_rate in (None, ""):
            fx_rate = self._fallback_fx_rate(currency)
        try:
            return (buy_price * Decimal(str(fx_rate))).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        except Exception:
            return buy_price

    @staticmethod
    def _fallback_fx_rate(currency: str) -> Decimal:
        key = f"{currency}KRW"
        try:
            from src.fx.updater import FXUpdater

            rates = FXUpdater().get_current_rates()
            if key in rates:
                return Decimal(str(rates[key]))
        except Exception:
            pass
        defaults = {"USD": Decimal("1350"), "JPY": Decimal("9"), "CNY": Decimal("185")}
        return defaults.get(currency, Decimal("1"))

    @staticmethod
    def _notify_rejected(product_row: dict, candidate: Decimal, margin_pct: Decimal) -> None:
        try:
            from src.notifications.telegram import send_telegram

            send_telegram(
                "⛔ 마진 가드로 가격 조정 거부\n"
                f"- SKU: {product_row.get('sku') or product_row.get('product_id') or '-'}\n"
                f"- 후보가: {int(candidate):,}원\n"
                f"- 예상 마진율: {float(margin_pct):.2f}%",
                urgency="warning",
            )
        except Exception as exc:
            logger.debug("마진 거부 알림 실패: %s", exc)
