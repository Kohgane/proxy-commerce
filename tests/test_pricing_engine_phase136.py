"""tests/test_pricing_engine_phase136.py — 가격 엔진 Phase 136 테스트."""
from __future__ import annotations

import os
import sys
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestPricingEngineTriggers:
    def _make_engine(self):
        from src.pricing.engine import PricingEngine
        return PricingEngine()

    def test_min_margin_pct_trigger_pass(self):
        engine = self._make_engine()
        trigger = {"kind": "min_margin_pct", "op": "<", "value": 15}
        assert engine._eval_trigger(trigger, {"margin_pct": "10.5"}, {}) is True

    def test_min_margin_pct_trigger_fail(self):
        engine = self._make_engine()
        trigger = {"kind": "min_margin_pct", "op": "<", "value": 15}
        assert engine._eval_trigger(trigger, {"margin_pct": "20.0"}, {}) is False

    def test_stock_qty_trigger_pass(self):
        engine = self._make_engine()
        trigger = {"kind": "stock_qty", "op": "<=", "value": 5}
        assert engine._eval_trigger(trigger, {"stock": "3"}, {}) is True

    def test_stock_qty_trigger_fail(self):
        engine = self._make_engine()
        trigger = {"kind": "stock_qty", "op": "<=", "value": 5}
        assert engine._eval_trigger(trigger, {"stock": "10"}, {}) is False

    def test_weekday_trigger_today(self):
        engine = self._make_engine()
        from datetime import datetime
        all_days = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
        today = all_days[datetime.now().weekday()]
        assert engine._eval_trigger({"kind": "weekday", "in": [today]}, {}, {}) is True

    def test_unknown_trigger_returns_false(self):
        engine = self._make_engine()
        assert engine._eval_trigger({"kind": "unknown_xyz"}, {}, {}) is False

    def test_empty_triggers_all_pass(self):
        from src.pricing.rule import PricingRule
        from src.pricing.engine import PricingEngine
        rule = PricingRule(name="t", triggers=[])
        assert PricingEngine()._triggers_pass(rule, {}, {}) is True


class TestPricingEngineActions:
    def _make_engine(self):
        from src.pricing.engine import PricingEngine
        return PricingEngine()

    def test_multiply_action(self):
        from src.pricing.rule import PricingRule
        engine = self._make_engine()
        rule = PricingRule(action_kind="multiply", action_value=Decimal("1.05"))
        assert engine._apply_action(rule, {}, Decimal("100000"), {}) == Decimal("105000")

    def test_add_action_positive(self):
        from src.pricing.rule import PricingRule
        engine = self._make_engine()
        rule = PricingRule(action_kind="add", action_value=Decimal("5000"))
        assert engine._apply_action(rule, {}, Decimal("100000"), {}) == Decimal("105000")

    def test_add_action_negative(self):
        from src.pricing.rule import PricingRule
        engine = self._make_engine()
        rule = PricingRule(action_kind="add", action_value=Decimal("-10000"))
        assert engine._apply_action(rule, {}, Decimal("100000"), {}) == Decimal("90000")

    def test_notify_only_no_change(self):
        from src.pricing.rule import PricingRule
        engine = self._make_engine()
        rule = PricingRule(action_kind="notify_only")
        assert engine._apply_action(rule, {}, Decimal("50000"), {}) == Decimal("50000")


class TestPricingEngineClamp:
    def _make_engine(self):
        from src.pricing.engine import PricingEngine
        return PricingEngine()

    def test_clamp_below_floor(self):
        e = self._make_engine()
        assert e._clamp(Decimal("5000"), 10000, None) == Decimal("10000")

    def test_clamp_above_ceiling(self):
        e = self._make_engine()
        assert e._clamp(Decimal("600000"), None, 500000) == Decimal("500000")

    def test_clamp_within_range(self):
        e = self._make_engine()
        assert e._clamp(Decimal("300000"), 10000, 500000) == Decimal("300000")


class TestPricingEngineScope:
    def _make_engine(self):
        from src.pricing.engine import PricingEngine
        return PricingEngine()

    def test_scope_all_matches_any(self):
        from src.pricing.rule import PricingRule
        e = self._make_engine()
        rule = PricingRule(scope_type="all")
        assert e._scope_matches(rule, {"sku": "ANY"}) is True

    def test_scope_domain_match(self):
        from src.pricing.rule import PricingRule
        e = self._make_engine()
        rule = PricingRule(scope_type="domain", scope_value="yoshidakaban.com")
        assert e._scope_matches(rule, {"src_url": "https://www.yoshidakaban.com/p/1"}) is True

    def test_scope_domain_no_match(self):
        from src.pricing.rule import PricingRule
        e = self._make_engine()
        rule = PricingRule(scope_type="domain", scope_value="yoshidakaban.com")
        assert e._scope_matches(rule, {"src_url": "https://other.com/p/1"}) is False

    def test_scope_sku_list_match(self):
        from src.pricing.rule import PricingRule
        e = self._make_engine()
        rule = PricingRule(scope_type="sku_list", scope_value="A,B,C")
        assert e._scope_matches(rule, {"sku": "B"}) is True

    def test_scope_sku_list_no_match(self):
        from src.pricing.rule import PricingRule
        e = self._make_engine()
        rule = PricingRule(scope_type="sku_list", scope_value="A,B,C")
        assert e._scope_matches(rule, {"sku": "X"}) is False


class TestPricingEngineDryRun:
    def _make_engine(self):
        from src.pricing.engine import PricingEngine
        return PricingEngine()

    def test_default_dry_run_is_true(self, monkeypatch):
        e = self._make_engine()
        monkeypatch.delenv("PRICING_DRY_RUN", raising=False)
        assert e._env_dry_run() is True

    def test_dry_run_explicit_0(self, monkeypatch):
        e = self._make_engine()
        monkeypatch.setenv("PRICING_DRY_RUN", "0")
        assert e._env_dry_run() is False

    def test_evaluate_dry_run_skips_market_calls(self, monkeypatch):
        from src.pricing.engine import PricingEngine
        from src.pricing.rule import PricingRule
        engine = PricingEngine()

        mock_catalog = [{"sku": "X-001", "sell_price_krw": 100000, "status": "active",
                         "buy_price": 80000, "buy_currency": "KRW"}]
        mock_rule = PricingRule(
            name="10% up", enabled=True, priority=10, triggers=[],
            action_kind="multiply", action_value=Decimal("1.1"),
        )

        with patch.object(engine, "_get_catalog_rows", return_value=mock_catalog), \
             patch.object(engine, "_get_fx_rates", return_value={}), \
             patch("src.pricing.rule.PricingRuleStore") as cls_mock:
            store_mock = MagicMock()
            store_mock.active_sorted.return_value = [mock_rule]
            cls_mock.return_value = store_mock

            apply_mock = MagicMock()
            with patch.object(engine, "_apply_to_markets", apply_mock):
                results = engine.evaluate(dry_run=True)

        apply_mock.assert_not_called()
        assert results["dry_run"] is True
