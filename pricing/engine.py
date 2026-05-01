"""pricing/engine.py — Pricing engine.

Covers issue #89: calculate_sell_price and calculate_margin_rate.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PricingConfig:
    """Configuration for the pricing engine."""

    markup_rate: float = 1.3          # multiplier applied to cost_price
    platform_fee_rate: float = 0.05   # e.g. 5% platform fee
    shipping_fee: float = 0.0         # flat shipping fee in the same currency
    exchange_rate: float = 1.0        # cost currency → sell currency conversion
    min_margin_rate: float = 0.10     # minimum acceptable margin (10%)


# Preset configurations
PRESETS: dict[str, PricingConfig] = {
    "standard": PricingConfig(
        markup_rate=1.3,
        platform_fee_rate=0.05,
        shipping_fee=0.0,
        exchange_rate=1.0,
        min_margin_rate=0.10,
    ),
    "premium": PricingConfig(
        markup_rate=1.5,
        platform_fee_rate=0.05,
        shipping_fee=0.0,
        exchange_rate=1.0,
        min_margin_rate=0.20,
    ),
    "budget": PricingConfig(
        markup_rate=1.15,
        platform_fee_rate=0.03,
        shipping_fee=0.0,
        exchange_rate=1.0,
        min_margin_rate=0.05,
    ),
}


def calculate_sell_price(
    cost_price: float,
    config: Optional[PricingConfig] = None,
) -> float:
    """Calculate the sell price from a cost price.

    Formula:
        base = cost_price * exchange_rate * markup_rate
        sell = (base + shipping_fee) / (1 - platform_fee_rate)

    Raises ValueError if the resulting margin is below min_margin_rate.
    """
    if config is None:
        config = PRESETS["standard"]

    if cost_price < 0:
        raise ValueError(f"cost_price must be non-negative, got {cost_price}")

    base = cost_price * config.exchange_rate * config.markup_rate
    sell = (base + config.shipping_fee) / (1.0 - config.platform_fee_rate)
    sell = round(sell, 2)

    margin = calculate_margin_rate(cost_price=cost_price, sell_price=sell, config=config)
    if margin < config.min_margin_rate:
        raise ValueError(
            f"Margin {margin:.2%} is below minimum {config.min_margin_rate:.2%}"
        )

    return sell


def calculate_margin_rate(
    cost_price: float,
    sell_price: float,
    config: Optional[PricingConfig] = None,
) -> float:
    """Return the net margin rate after platform fees and shipping.

    margin_rate = (sell_price * (1 - platform_fee_rate) - shipping_fee - cost * exchange_rate)
                  / sell_price
    """
    if config is None:
        config = PRESETS["standard"]

    if sell_price < 0:
        raise ValueError(f"sell_price must be non-negative, got {sell_price}")
    if sell_price == 0:
        raise ValueError("sell_price must not be zero (division by zero)")

    revenue_after_fee = sell_price * (1.0 - config.platform_fee_rate)
    net = revenue_after_fee - config.shipping_fee - (cost_price * config.exchange_rate)
    return round(net / sell_price, 6)
