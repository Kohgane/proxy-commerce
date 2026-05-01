import pytest

from pricing.engine import (
    MarginBelowThresholdError,
    PRESETS,
    calculate_margin_rate,
    calculate_sell_price,
)


def test_presets_have_three_required_policies():
    assert set(PRESETS.keys()) == {"entry", "standard", "aggressive"}


def test_calculate_sell_price_supports_explicit_inputs():
    sell_price = calculate_sell_price(
        cost_price=100,
        exchange_rate=1300,
        shipping_fee=5000,
        fee_rate=0.05,
        target_margin_rate=0.28,
    )
    assert sell_price == pytest.approx(201492.54)


def test_calculate_margin_rate_supports_explicit_inputs():
    margin = calculate_margin_rate(
        cost_price=100,
        sell_price=201492.54,
        exchange_rate=1300,
        shipping_fee=5000,
        fee_rate=0.05,
    )
    assert margin == pytest.approx(0.28, abs=1e-6)


def test_calculate_sell_price_blocks_below_minimum_margin():
    with pytest.raises(MarginBelowThresholdError):
        calculate_sell_price(
            cost_price=100,
            exchange_rate=1300,
            shipping_fee=5000,
            fee_rate=0.05,
            target_margin_rate=0.20,
            min_margin_rate=0.25,
        )


def test_presets_produce_margin_at_or_above_threshold():
    for config in PRESETS.values():
        sell = calculate_sell_price(cost_price=100.0, config=config)
        margin = calculate_margin_rate(cost_price=100.0, sell_price=sell, config=config)
        assert margin + 5e-4 >= config.min_margin_rate
