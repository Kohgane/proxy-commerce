"""tests/test_shipping_calculator.py — Phase 80: 배송비 계산기 테스트."""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.shipping_calculator import (
    ShippingCalculator,
    ShippingZone,
    WeightBasedRule,
    PriceBasedRule,
    DimensionalWeight,
    FreeShippingPromotion,
    ShippingEstimator,
)


class TestWeightBasedRule:
    def test_tier_1(self):
        rule = WeightBasedRule()
        assert rule.calculate(200) == 3000.0

    def test_tier_2(self):
        rule = WeightBasedRule()
        assert rule.calculate(1000) == 4000.0

    def test_tier_3(self):
        rule = WeightBasedRule()
        assert rule.calculate(3000) == 6000.0

    def test_tier_4(self):
        rule = WeightBasedRule()
        assert rule.calculate(6000) == 10000.0


class TestPriceBasedRule:
    def test_free_threshold(self):
        rule = PriceBasedRule(free_threshold=50000)
        assert rule.calculate(50000, 3000) == 0.0

    def test_below_threshold(self):
        rule = PriceBasedRule(free_threshold=50000)
        assert rule.calculate(10000, 3000) == 3000.0


class TestShippingZone:
    def test_list_zones(self):
        zone = ShippingZone()
        zones = zone.list_zones()
        assert len(zones) >= 4

    def test_classify_domestic(self):
        zone = ShippingZone()
        assert zone.classify('KR') == 'domestic'

    def test_classify_east_asia(self):
        zone = ShippingZone()
        assert zone.classify('JP') == 'east_asia'

    def test_classify_international(self):
        zone = ShippingZone()
        assert zone.classify('AU') == 'international'

    def test_get_zone(self):
        zone = ShippingZone()
        z = zone.get_zone('domestic')
        assert z is not None
        assert z['zone_id'] == 'domestic'


class TestDimensionalWeight:
    def test_calculate(self):
        dw = DimensionalWeight()
        result = dw.calculate(10, 10, 10)
        assert result == 0.2

    def test_effective_weight_actual_heavier(self):
        dw = DimensionalWeight()
        result = dw.effective_weight(500, 10, 10, 10)
        assert result == 500

    def test_effective_weight_dim_heavier(self):
        dw = DimensionalWeight()
        # 50*50*50/5000 = 25kg = 25000g > 1000g
        result = dw.effective_weight(1000, 50, 50, 50)
        assert result > 1000


class TestFreeShippingPromotion:
    def test_qualifies(self):
        promo = FreeShippingPromotion(50000)
        assert promo.qualifies(50000) is True
        assert promo.qualifies(49999) is False


class TestShippingEstimator:
    def test_estimate_domestic(self):
        est = ShippingEstimator()
        result = est.estimate('CJ', 'domestic')
        assert result['min_days'] == 1
        assert result['max_days'] == 2

    def test_estimate_unknown(self):
        est = ShippingEstimator()
        result = est.estimate('UNKNOWN', 'unknown_zone')
        assert 'min_days' in result
        assert 'max_days' in result


class TestShippingCalculator:
    def test_calculate_basic(self):
        calc = ShippingCalculator()
        result = calc.calculate(weight_g=500, zone='domestic')
        assert result['price'] == 3000.0
        assert result['zone'] == 'domestic'

    def test_calculate_free_shipping(self):
        calc = ShippingCalculator()
        result = calc.calculate(weight_g=500, zone='domestic', order_price=50000)
        assert result['price'] == 0.0
