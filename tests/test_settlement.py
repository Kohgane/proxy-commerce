"""tests/test_settlement.py — Phase 22 정산 계산기 테스트."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.payments.settlement import SettlementCalculator  # noqa: E402
from src.payments.models import Settlement  # noqa: E402

# ──────────────────────────────────────────────────────────
# 공통 픽스처
# ──────────────────────────────────────────────────────────

SAMPLE_ORDER = {
    'order_id': 'ord-001',
    'sale_price': 150000.0,
    'cost_price': 90000.0,
    'platform': 'COUPANG',
    'shipping_fee': 3000.0,
    'fx_diff': 500.0,
}

BULK_ORDERS = [
    {
        'order_id': 'ord-A',
        'sale_price': 100000.0,
        'cost_price': 60000.0,
        'platform': 'NAVER',
        'shipping_fee': 2500.0,
    },
    {
        'order_id': 'ord-B',
        'sale_price': 200000.0,
        'cost_price': 130000.0,
        'platform': 'SHOPIFY',
        'shipping_fee': 5000.0,
        'fx_diff': 1000.0,
    },
    {
        'order_id': 'ord-C',
        'sale_price': 80000.0,
        'cost_price': 50000.0,
        'platform': 'WOO',
        'shipping_fee': 0.0,
    },
]


# ══════════════════════════════════════════════════════════
# TestSettlementCalculator
# ══════════════════════════════════════════════════════════


class TestSettlementCalculator:
    def setup_method(self):
        self.calc = SettlementCalculator()

    # ── calculate ──────────────────────────────────────────

    def test_calculate_single_order(self):
        s = self.calc.calculate(SAMPLE_ORDER)
        assert isinstance(s, Settlement)
        assert s.order_id == 'ord-001'
        assert s.sale_price == 150000.0
        assert s.cost_price == 90000.0
        # COUPANG fee: 150000 * 0.108 = 16200
        assert s.platform_fee == pytest.approx(16200.0)
        assert s.shipping_fee == 3000.0
        assert s.fx_diff == 500.0
        # net = 150000 - 90000 - 16200 - 3000 - 500 = 40300
        assert s.net_profit == pytest.approx(40300.0)

    def test_calculate_naver_platform(self):
        order = {
            'order_id': 'ord-naver',
            'sale_price': 100000.0,
            'cost_price': 60000.0,
            'platform': 'NAVER',
            'shipping_fee': 2500.0,
        }
        s = self.calc.calculate(order)
        # NAVER fee: 100000 * 0.055 = 5500
        assert s.platform_fee == pytest.approx(5500.0)
        # net = 100000 - 60000 - 5500 - 2500 = 32000
        assert s.net_profit == pytest.approx(32000.0)

    def test_calculate_woo_no_fee(self):
        order = {
            'order_id': 'ord-woo',
            'sale_price': 50000.0,
            'cost_price': 30000.0,
            'platform': 'WOO',
            'shipping_fee': 0.0,
        }
        s = self.calc.calculate(order)
        assert s.platform_fee == 0.0
        assert s.net_profit == pytest.approx(20000.0)

    def test_calculate_optional_fx_diff_defaults_to_zero(self):
        order = {
            'order_id': 'ord-fx',
            'sale_price': 100000.0,
            'cost_price': 70000.0,
            'platform': 'SHOPIFY',
            'shipping_fee': 1000.0,
        }
        s = self.calc.calculate(order)
        assert s.fx_diff == 0.0
        # SHOPIFY fee: 100000 * 0.02 = 2000
        # net = 100000 - 70000 - 2000 - 1000 = 27000
        assert s.net_profit == pytest.approx(27000.0)

    # ── calculate_bulk ─────────────────────────────────────

    def test_calculate_bulk_returns_list(self):
        results = self.calc.calculate_bulk(BULK_ORDERS)
        assert isinstance(results, list)
        assert len(results) == 3

    def test_calculate_bulk_order_ids(self):
        results = self.calc.calculate_bulk(BULK_ORDERS)
        ids = [s.order_id for s in results]
        assert ids == ['ord-A', 'ord-B', 'ord-C']

    def test_calculate_bulk_all_settlements(self):
        results = self.calc.calculate_bulk(BULK_ORDERS)
        for s in results:
            assert isinstance(s, Settlement)
            # net_profit should have been calculated
            assert s.net_profit != 0.0 or (s.sale_price == s.cost_price + s.platform_fee + s.shipping_fee)

    def test_calculate_bulk_empty(self):
        results = self.calc.calculate_bulk([])
        assert results == []

    # ── summarize ──────────────────────────────────────────

    def test_summarize_keys(self):
        settlements = self.calc.calculate_bulk(BULK_ORDERS)
        summary = self.calc.summarize(settlements)
        assert 'total_revenue' in summary
        assert 'total_cost' in summary
        assert 'total_fees' in summary
        assert 'total_shipping' in summary
        assert 'total_net_profit' in summary
        assert 'count' in summary

    def test_summarize_count(self):
        settlements = self.calc.calculate_bulk(BULK_ORDERS)
        summary = self.calc.summarize(settlements)
        assert summary['count'] == 3

    def test_summarize_totals(self):
        settlements = self.calc.calculate_bulk(BULK_ORDERS)
        summary = self.calc.summarize(settlements)
        expected_revenue = 100000.0 + 200000.0 + 80000.0
        assert summary['total_revenue'] == pytest.approx(expected_revenue)
        expected_cost = 60000.0 + 130000.0 + 50000.0
        assert summary['total_cost'] == pytest.approx(expected_cost)

    def test_summarize_net_profit_equals_sum(self):
        settlements = self.calc.calculate_bulk(BULK_ORDERS)
        summary = self.calc.summarize(settlements)
        manual_sum = sum(s.net_profit for s in settlements)
        assert summary['total_net_profit'] == pytest.approx(manual_sum)

    def test_summarize_empty_list(self):
        summary = self.calc.summarize([])
        assert summary['count'] == 0
        assert summary['total_revenue'] == 0
        assert summary['total_net_profit'] == 0

    # ── negative net profit ────────────────────────────────

    def test_negative_net_profit_scenario(self):
        """원가 + 수수료 + 배송비가 판매가를 초과하면 순이익이 음수여야 한다."""
        order = {
            'order_id': 'ord-loss',
            'sale_price': 50000.0,
            'cost_price': 48000.0,   # 높은 원가
            'platform': 'COUPANG',   # 10.8% 수수료 = 5400
            'shipping_fee': 3000.0,
            'fx_diff': 0.0,
        }
        s = self.calc.calculate(order)
        # net = 50000 - 48000 - 5400 - 3000 = -6400
        assert s.net_profit < 0
        assert s.net_profit == pytest.approx(-6400.0)

    def test_summarize_with_negative_profit(self):
        """정산 목록에 손실 주문이 포함되면 total_net_profit이 감소해야 한다."""
        loss_order = {
            'order_id': 'ord-loss',
            'sale_price': 50000.0,
            'cost_price': 48000.0,
            'platform': 'COUPANG',
            'shipping_fee': 3000.0,
        }
        profit_order = {
            'order_id': 'ord-profit',
            'sale_price': 200000.0,
            'cost_price': 100000.0,
            'platform': 'WOO',
            'shipping_fee': 0.0,
        }
        settlements = self.calc.calculate_bulk([loss_order, profit_order])
        summary = self.calc.summarize(settlements)
        loss_net = settlements[0].net_profit   # negative
        profit_net = settlements[1].net_profit  # positive
        assert loss_net < 0
        assert profit_net > 0
        assert summary['total_net_profit'] == pytest.approx(loss_net + profit_net)
