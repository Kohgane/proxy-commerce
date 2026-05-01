"""pricing/engine.py — Pricing engine.

Covers issue #89: calculate_sell_price and calculate_margin_rate.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

MARGIN_COMPARISON_TOLERANCE = 5e-4


@dataclass
class PricingConfig:
    """Configuration for the pricing engine."""

    markup_rate: float = 1.3          # multiplier applied to cost_price
    platform_fee_rate: float = 0.05   # e.g. 5% platform fee
    shipping_fee: float = 0.0         # flat shipping fee in the same currency
    exchange_rate: float = 1.0        # cost currency → sell currency conversion
    target_margin_rate: Optional[float] = None
    min_margin_rate: float = 0.10     # minimum acceptable margin (10%)


class MarginBelowThresholdError(ValueError):
    """Raised when calculated margin is below minimum threshold."""


DEFAULT_PRESETS: dict[str, PricingConfig] = {
    "entry": PricingConfig(
        markup_rate=1.266667,
        platform_fee_rate=0.05,
        shipping_fee=0.0,
        exchange_rate=1.0,
        target_margin_rate=0.20,
        min_margin_rate=0.20,
    ),
    "standard": PricingConfig(
        markup_rate=1.41791,
        platform_fee_rate=0.05,
        shipping_fee=0.0,
        exchange_rate=1.0,
        target_margin_rate=0.28,
        min_margin_rate=0.28,
    ),
    "aggressive": PricingConfig(
        markup_rate=1.583333,
        platform_fee_rate=0.05,
        shipping_fee=0.0,
        exchange_rate=1.0,
        target_margin_rate=0.35,
        min_margin_rate=0.35,
    ),
}


def _load_presets_from_yaml(config_path: Path) -> dict[str, PricingConfig]:
    if not config_path.exists():
        return {}

    with config_path.open("r", encoding="utf-8") as fp:
        parsed = yaml.safe_load(fp) or {}

    presets = parsed.get("presets", {})
    loaded: dict[str, PricingConfig] = {}
    for name, values in presets.items():
        if not isinstance(values, dict):
            continue
        loaded[name] = PricingConfig(
            markup_rate=float(values.get("markup_rate", 1.3)),
            platform_fee_rate=float(values.get("platform_fee_rate", 0.05)),
            shipping_fee=float(values.get("shipping_fee", 0.0)),
            exchange_rate=float(values.get("exchange_rate", 1.0)),
            target_margin_rate=(
                float(values["target_margin_rate"])
                if values.get("target_margin_rate") is not None
                else None
            ),
            min_margin_rate=float(values.get("min_margin_rate", 0.10)),
        )
    return loaded


def _resolve_config(
    config: Optional[PricingConfig],
    *,
    exchange_rate: Optional[float],
    shipping_fee: Optional[float],
    fee_rate: Optional[float],
    target_margin_rate: Optional[float],
    min_margin_rate: Optional[float],
) -> PricingConfig:
    resolved = config or PRESETS["standard"]
    return PricingConfig(
        markup_rate=resolved.markup_rate,
        platform_fee_rate=(
            resolved.platform_fee_rate if fee_rate is None else float(fee_rate)
        ),
        shipping_fee=resolved.shipping_fee if shipping_fee is None else float(shipping_fee),
        exchange_rate=resolved.exchange_rate if exchange_rate is None else float(exchange_rate),
        target_margin_rate=(
            resolved.target_margin_rate
            if target_margin_rate is None
            else float(target_margin_rate)
        ),
        min_margin_rate=(
            resolved.min_margin_rate
            if min_margin_rate is None
            else float(min_margin_rate)
        ),
    )


PRESETS = _load_presets_from_yaml(
    Path(__file__).resolve().parents[1] / "config" / "pricing.yaml"
) or DEFAULT_PRESETS


def calculate_sell_price(
    cost_price: float,
    config: Optional[PricingConfig] = None,
    *,
    exchange_rate: Optional[float] = None,
    shipping_fee: Optional[float] = None,
    fee_rate: Optional[float] = None,
    target_margin_rate: Optional[float] = None,
    target_margin_pct: Optional[float] = None,
    min_margin_rate: Optional[float] = None,
) -> float:
    """Calculate the sell price from a cost price.

    Formula:
        base = cost_price * exchange_rate * markup_rate
        sell = (base + shipping_fee) / (1 - platform_fee_rate)

    Raises ValueError if the resulting margin is below min_margin_rate.
    """
    if target_margin_rate is None and target_margin_pct is not None:
        target_margin_rate = float(target_margin_pct) / 100.0

    if cost_price < 0:
        raise ValueError(f"cost_price must be non-negative, got {cost_price}")

    resolved = _resolve_config(
        config,
        exchange_rate=exchange_rate,
        shipping_fee=shipping_fee,
        fee_rate=fee_rate,
        target_margin_rate=target_margin_rate,
        min_margin_rate=min_margin_rate,
    )

    if resolved.target_margin_rate is not None:
        denominator = 1.0 - resolved.platform_fee_rate - resolved.target_margin_rate
        if denominator <= 0:
            raise ValueError("target margin is too high for the given fee_rate")
        cost_component = (cost_price * resolved.exchange_rate) + resolved.shipping_fee
        sell = cost_component / denominator
    else:
        base = cost_price * resolved.exchange_rate * resolved.markup_rate
        sell = (base + resolved.shipping_fee) / (1.0 - resolved.platform_fee_rate)

    sell = round(sell, 2)

    margin = calculate_margin_rate(cost_price=cost_price, sell_price=sell, config=resolved)
    if margin + MARGIN_COMPARISON_TOLERANCE < resolved.min_margin_rate:
        raise MarginBelowThresholdError(
            f"Margin {margin:.2%} is below minimum {resolved.min_margin_rate:.2%}"
        )

    return sell


def calculate_margin_rate(
    cost_price: float,
    sell_price: float,
    config: Optional[PricingConfig] = None,
    *,
    exchange_rate: Optional[float] = None,
    shipping_fee: Optional[float] = None,
    fee_rate: Optional[float] = None,
) -> float:
    """Return the net margin rate after platform fees and shipping.

    margin_rate = (sell_price * (1 - platform_fee_rate) - shipping_fee - cost * exchange_rate)
                  / sell_price
    """
    if cost_price < 0:
        raise ValueError(f"cost_price must be non-negative, got {cost_price}")

    if sell_price < 0:
        raise ValueError(f"sell_price must be non-negative, got {sell_price}")
    if sell_price == 0:
        raise ValueError("sell_price must not be zero (division by zero)")

    resolved = _resolve_config(
        config,
        exchange_rate=exchange_rate,
        shipping_fee=shipping_fee,
        fee_rate=fee_rate,
        target_margin_rate=None,
        min_margin_rate=None,
    )

    revenue_after_fee = sell_price * (1.0 - resolved.platform_fee_rate)
    net = revenue_after_fee - resolved.shipping_fee - (cost_price * resolved.exchange_rate)
    return round(net / sell_price, 6)
