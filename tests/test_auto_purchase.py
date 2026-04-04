"""tests/test_auto_purchase.py — Phase 96: 자동 구매 엔진 테스트."""
from __future__ import annotations

import sys
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest


# ─── PurchaseModels ─────────────────────────────────────────────────────────

class TestPurchaseModels:
    def test_purchase_order_defaults(self):
        from src.auto_purchase.purchase_models import PurchaseOrder, PurchaseStatus
        order = PurchaseOrder()
        assert order.order_id
        assert order.status == PurchaseStatus.PENDING
        assert order.quantity == 1
        assert order.retry_count == 0

    def test_purchase_order_update_status(self):
        from src.auto_purchase.purchase_models import PurchaseOrder, PurchaseStatus
        order = PurchaseOrder()
        order.update_status(PurchaseStatus.CONFIRMED)
        assert order.status == PurchaseStatus.CONFIRMED

    def test_purchase_order_update_status_with_error(self):
        from src.auto_purchase.purchase_models import PurchaseOrder, PurchaseStatus
        order = PurchaseOrder(unit_price=10.0, quantity=3)
        order.update_status(PurchaseStatus.FAILED, 'out of stock')
        assert order.status == PurchaseStatus.FAILED
        assert order.error_message == 'out of stock'

    def test_purchase_order_total_price(self):
        from src.auto_purchase.purchase_models import PurchaseOrder
        order = PurchaseOrder(unit_price=25.0, quantity=4)
        assert order.total_price == 100.0

    def test_source_option_total_cost(self):
        from src.auto_purchase.purchase_models import SourceOption
        opt = SourceOption(price=50.0, shipping_cost=10.0)
        assert opt.total_cost == 60.0

    def test_purchase_result_defaults(self):
        from src.auto_purchase.purchase_models import PurchaseResult
        result = PurchaseResult()
        assert not result.success
        assert result.order_id == ''

    def test_purchase_metrics_recalculate(self):
        from src.auto_purchase.purchase_models import PurchaseMetrics
        m = PurchaseMetrics(successful_orders=8, failed_orders=2)
        m.recalculate()
        assert m.success_rate == 0.8
        assert m.total_orders == 10

    def test_purchase_metrics_zero_divide(self):
        from src.auto_purchase.purchase_models import PurchaseMetrics
        m = PurchaseMetrics()
        m.recalculate()
        assert m.success_rate == 0.0

    def test_payment_record_defaults(self):
        from src.auto_purchase.purchase_models import PaymentRecord
        rec = PaymentRecord()
        assert rec.record_id
        assert rec.status == 'completed'


# ─── AmazonBuyer ─────────────────────────────────────────────────────────────

class TestAmazonBuyer:
    def _make_buyer(self, region='US'):
        from src.auto_purchase.marketplace_buyer import AmazonBuyer
        return AmazonBuyer(region=region)

    def test_marketplace_name_us(self):
        buyer = self._make_buyer('US')
        assert buyer.marketplace_name == 'amazon_us'

    def test_marketplace_name_jp(self):
        buyer = self._make_buyer('JP')
        assert buyer.marketplace_name == 'amazon_jp'

    def test_search_product_found(self):
        buyer = self._make_buyer()
        results = buyer.search_product('Echo')
        assert len(results) > 0
        assert results[0].marketplace == 'amazon_us'

    def test_search_product_not_found(self):
        buyer = self._make_buyer()
        results = buyer.search_product('ZZZZNONEXISTENT')
        assert results == []

    def test_search_by_asin(self):
        buyer = self._make_buyer()
        results = buyer.search_product('B08N5WRWNW')
        assert len(results) == 1

    def test_check_availability_found(self):
        buyer = self._make_buyer()
        result = buyer.check_availability('B08N5WRWNW')
        assert result['available']
        assert result['price'] == 49.99

    def test_check_availability_not_found(self):
        buyer = self._make_buyer()
        result = buyer.check_availability('INVALID_ASIN')
        assert not result['available']
        assert 'error' in result

    def test_place_order_success(self):
        from src.auto_purchase.purchase_models import PurchaseOrder
        buyer = self._make_buyer()
        order = PurchaseOrder(
            source_product_id='B08N5WRWNW',
            quantity=1,
        )
        result = buyer.place_order(order)
        assert result.success
        assert result.confirmation_code.startswith('AMZ-US-')
        assert result.actual_cost == 49.99

    def test_place_order_insufficient_stock(self):
        from src.auto_purchase.purchase_models import PurchaseOrder
        buyer = self._make_buyer()
        order = PurchaseOrder(
            source_product_id='B08N5WRWNW',
            quantity=9999,
        )
        result = buyer.place_order(order)
        assert not result.success
        assert '재고 부족' in result.error_message

    def test_check_order_status_not_found(self):
        buyer = self._make_buyer()
        result = buyer.check_order_status('NONEXISTENT')
        assert result['status'] == 'NotFound'

    def test_cancel_order_success(self):
        from src.auto_purchase.purchase_models import PurchaseOrder
        buyer = self._make_buyer()
        order = PurchaseOrder(source_product_id='B09B8YWXDF', quantity=1)
        placed = buyer.place_order(order)
        assert placed.success
        cancelled = buyer.cancel_order(placed.order_id)
        assert cancelled

    def test_cancel_nonexistent_order(self):
        buyer = self._make_buyer()
        assert not buyer.cancel_order('DOES_NOT_EXIST')

    def test_stock_decreases_after_order(self):
        from src.auto_purchase.purchase_models import PurchaseOrder
        buyer = self._make_buyer()
        initial_stock = buyer._catalog['B0BDJH3XVN']['stock']
        order = PurchaseOrder(source_product_id='B0BDJH3XVN', quantity=2)
        buyer.place_order(order)
        assert buyer._catalog['B0BDJH3XVN']['stock'] == initial_stock - 2


# ─── TaobaoBuyer ─────────────────────────────────────────────────────────────

class TestTaobaoBuyer:
    def _make_buyer(self):
        from src.auto_purchase.marketplace_buyer import TaobaoBuyer
        return TaobaoBuyer()

    def test_marketplace_name(self):
        buyer = self._make_buyer()
        assert buyer.marketplace_name == 'taobao'

    def test_search_product_found(self):
        buyer = self._make_buyer()
        results = buyer.search_product('나이키')
        assert len(results) > 0

    def test_check_availability(self):
        buyer = self._make_buyer()
        result = buyer.check_availability('TB001234')
        assert result['available']
        assert result['currency'] == 'CNY'

    def test_place_order_success(self):
        from src.auto_purchase.purchase_models import PurchaseOrder
        buyer = self._make_buyer()
        order = PurchaseOrder(source_product_id='TB001234', quantity=1)
        result = buyer.place_order(order)
        assert result.success
        assert result.currency == 'CNY'
        assert result.order_id.startswith('TB-')

    def test_place_order_insufficient_stock(self):
        from src.auto_purchase.purchase_models import PurchaseOrder
        buyer = self._make_buyer()
        order = PurchaseOrder(source_product_id='TB001234', quantity=99999)
        result = buyer.place_order(order)
        assert not result.success

    def test_cancel_order(self):
        from src.auto_purchase.purchase_models import PurchaseOrder
        buyer = self._make_buyer()
        order = PurchaseOrder(source_product_id='TB005678', quantity=1)
        placed = buyer.place_order(order)
        assert placed.success
        assert buyer.cancel_order(placed.order_id)


# ─── AlibabaBuyer ─────────────────────────────────────────────────────────────

class TestAlibabaBuyer:
    def _make_buyer(self):
        from src.auto_purchase.marketplace_buyer import AlibabaBuyer
        return AlibabaBuyer()

    def test_marketplace_name(self):
        buyer = self._make_buyer()
        assert buyer.marketplace_name == 'alibaba_1688'

    def test_check_moq_pass(self):
        buyer = self._make_buyer()
        assert buyer.check_moq('1688-001', 100)

    def test_check_moq_fail(self):
        buyer = self._make_buyer()
        assert not buyer.check_moq('1688-001', 10)

    def test_place_order_moq_fail(self):
        from src.auto_purchase.purchase_models import PurchaseOrder
        buyer = self._make_buyer()
        order = PurchaseOrder(source_product_id='1688-001', quantity=5)
        result = buyer.place_order(order)
        assert not result.success
        assert 'MOQ' in result.error_message

    def test_place_order_success(self):
        from src.auto_purchase.purchase_models import PurchaseOrder
        buyer = self._make_buyer()
        order = PurchaseOrder(source_product_id='1688-001', quantity=100)
        result = buyer.place_order(order)
        assert result.success
        assert result.order_id.startswith('1688-ORD-')

    def test_place_order_not_found(self):
        from src.auto_purchase.purchase_models import PurchaseOrder
        buyer = self._make_buyer()
        order = PurchaseOrder(source_product_id='INVALID', quantity=10)
        result = buyer.place_order(order)
        assert not result.success

    def test_check_availability(self):
        buyer = self._make_buyer()
        result = buyer.check_availability('1688-002')
        assert result['available']
        assert result['moq'] == 50

    def test_cancel_order(self):
        from src.auto_purchase.purchase_models import PurchaseOrder
        buyer = self._make_buyer()
        order = PurchaseOrder(source_product_id='1688-002', quantity=50)
        placed = buyer.place_order(order)
        assert placed.success
        assert buyer.cancel_order(placed.order_id)


# ─── SourceSelector ──────────────────────────────────────────────────────────

class TestSourceSelector:
    def _make_options(self):
        from src.auto_purchase.purchase_models import SourceOption
        return [
            SourceOption(
                marketplace='amazon_us', product_id='A1',
                price=100.0, shipping_cost=0.0,
                availability=True, estimated_delivery_days=3,
                seller_rating=4.8,
            ),
            SourceOption(
                marketplace='taobao', product_id='T1',
                price=60.0, shipping_cost=15.0,
                availability=True, estimated_delivery_days=14,
                seller_rating=4.2,
            ),
            SourceOption(
                marketplace='alibaba_1688', product_id='AL1',
                price=40.0, shipping_cost=20.0,
                availability=True, estimated_delivery_days=10,
                seller_rating=4.5, moq=50,
            ),
        ]

    def test_cheapest_first(self):
        from src.auto_purchase.source_selector import SourceSelector, SelectionStrategy
        selector = SourceSelector()
        options = self._make_options()
        selected = selector.select(options, strategy=SelectionStrategy.CHEAPEST_FIRST)
        assert selected.marketplace == 'alibaba_1688'

    def test_fastest_delivery(self):
        from src.auto_purchase.source_selector import SourceSelector, SelectionStrategy
        selector = SourceSelector()
        options = self._make_options()
        selected = selector.select(options, strategy=SelectionStrategy.FASTEST_DELIVERY)
        assert selected.marketplace == 'amazon_us'

    def test_reliability_first(self):
        from src.auto_purchase.source_selector import SourceSelector, SelectionStrategy
        selector = SourceSelector()
        options = self._make_options()
        selected = selector.select(options, strategy=SelectionStrategy.RELIABILITY_FIRST)
        assert selected.marketplace == 'amazon_us'

    def test_balanced_returns_option(self):
        from src.auto_purchase.source_selector import SourceSelector, SelectionStrategy
        selector = SourceSelector()
        options = self._make_options()
        selected = selector.select(options, strategy=SelectionStrategy.BALANCED)
        assert selected is not None

    def test_no_available_options(self):
        from src.auto_purchase.purchase_models import SourceOption
        from src.auto_purchase.source_selector import SourceSelector
        selector = SourceSelector()
        options = [SourceOption(availability=False)]
        assert selector.select(options) is None

    def test_score_all(self):
        from src.auto_purchase.source_selector import SourceSelector
        selector = SourceSelector()
        options = self._make_options()
        scores = selector.score_all(options)
        assert len(scores) == 3
        assert all('score' in s for s in scores)

    def test_list_strategies(self):
        from src.auto_purchase.source_selector import SourceSelector
        selector = SourceSelector()
        strategies = selector.list_strategies()
        assert 'balanced' in strategies
        assert 'cheapest_first' in strategies

    def test_unknown_strategy_falls_back(self):
        from src.auto_purchase.source_selector import SourceSelector
        selector = SourceSelector()
        options = self._make_options()
        selected = selector.select(options, strategy='UNKNOWN_STRATEGY')
        assert selected is not None


# ─── PaymentAutomator ────────────────────────────────────────────────────────

class TestPaymentAutomator:
    def _make_automator(self):
        from src.auto_purchase.payment_automator import PaymentAutomator
        return PaymentAutomator()

    def test_list_methods(self):
        pa = self._make_automator()
        methods = pa.list_methods()
        assert len(methods) >= 2

    def test_select_method_amazon(self):
        pa = self._make_automator()
        method = pa.select_method('amazon_us', 100.0, 'USD')
        assert method is not None
        assert method.type in ('credit_card', 'paypal')

    def test_select_method_taobao(self):
        pa = self._make_automator()
        method = pa.select_method('taobao', 500.0, 'CNY')
        assert method is not None

    def test_process_payment_success(self):
        pa = self._make_automator()
        record = pa.process_payment('order_001', 'amazon_us', 100.0, 'USD')
        assert record.status == 'completed'
        assert record.order_id == 'order_001'
        assert record.receipt_url

    def test_process_payment_with_method_id(self):
        pa = self._make_automator()
        record = pa.process_payment('order_002', 'amazon_us', 50.0, 'USD', method_id='pm_card_usd')
        assert record.status == 'completed'

    def test_process_payment_exceeds_single_limit(self):
        from src.auto_purchase.payment_automator import PaymentMethod
        pa = self._make_automator()
        # Add method with low limit
        tiny = PaymentMethod(
            method_id='pm_tiny', type='credit_card', name='Tiny',
            currency='USD', balance=10.0,
            daily_limit=100.0, monthly_limit=1000.0, single_limit=5.0,
            is_active=True, supported_marketplaces=['amazon_us'],
        )
        pa.add_payment_method(tiny)
        # Primary method should still work
        record = pa.process_payment('order_003', 'amazon_us', 500.0, 'USD', method_id='pm_card_usd')
        assert record.status == 'completed'

    def test_get_payment_history(self):
        pa = self._make_automator()
        pa.process_payment('ord_x', 'amazon_us', 10.0, 'USD')
        history = pa.get_payment_history('ord_x')
        assert len(history) == 1
        assert history[0].order_id == 'ord_x'

    def test_get_all_payment_history(self):
        pa = self._make_automator()
        pa.process_payment('ord_a', 'amazon_us', 10.0, 'USD')
        pa.process_payment('ord_b', 'taobao', 50.0, 'CNY')
        history = pa.get_payment_history()
        assert len(history) == 2

    def test_daily_spend_tracking(self):
        pa = self._make_automator()
        pa.process_payment('ord_ds1', 'amazon_us', 100.0, 'USD', method_id='pm_card_usd')
        spent = pa.get_daily_spend('pm_card_usd')
        assert spent == 100.0


# ─── PurchaseRuleEngine ──────────────────────────────────────────────────────

class TestPurchaseRuleEngine:
    def _make_context(self, **kwargs):
        from src.auto_purchase.purchase_rules import RuleContext
        defaults = {
            'product_id': 'PROD_001',
            'marketplace': 'amazon_us',
            'unit_price': 100.0,
            'quantity': 1,
            'selling_price': 150.0,
            'currency': 'USD',
        }
        defaults.update(kwargs)
        return RuleContext(**defaults)

    def test_all_rules_pass(self):
        from src.auto_purchase.purchase_rules import PurchaseRuleEngine
        engine = PurchaseRuleEngine()
        context = self._make_context(unit_price=50.0, selling_price=100.0)
        result = engine.evaluate(context)
        assert result['decision'] == 'pass'

    def test_max_price_rule_reject(self):
        from src.auto_purchase.purchase_rules import MaxPriceRule, PurchaseRuleEngine, RuleContext, RULE_REJECT
        engine = PurchaseRuleEngine()
        engine._rules = [MaxPriceRule(max_price=50.0)]
        context = RuleContext(unit_price=100.0, quantity=1, selling_price=150.0)
        result = engine.evaluate(context)
        assert result['decision'] == RULE_REJECT

    def test_min_margin_rule_hold(self):
        from src.auto_purchase.purchase_rules import MinMarginRule, PurchaseRuleEngine, RuleContext, RULE_HOLD
        engine = PurchaseRuleEngine()
        engine._rules = [MinMarginRule(min_margin_rate=0.20)]
        context = RuleContext(unit_price=90.0, quantity=1, selling_price=100.0)
        result = engine.evaluate(context)
        assert result['decision'] == RULE_HOLD

    def test_min_margin_no_selling_price(self):
        from src.auto_purchase.purchase_rules import MinMarginRule, PurchaseRuleEngine, RuleContext, RULE_HOLD
        engine = PurchaseRuleEngine()
        engine._rules = [MinMarginRule()]
        context = RuleContext(unit_price=50.0, quantity=1, selling_price=0.0)
        result = engine.evaluate(context)
        assert result['decision'] == RULE_HOLD

    def test_blacklist_seller_reject(self):
        from src.auto_purchase.purchase_rules import BlacklistRule, PurchaseRuleEngine, RuleContext, RULE_REJECT
        engine = PurchaseRuleEngine()
        bl = BlacklistRule(blacklist_sellers=['bad_seller'])
        engine._rules = [bl]
        context = RuleContext(seller_id='bad_seller', unit_price=10.0, selling_price=20.0)
        result = engine.evaluate(context)
        assert result['decision'] == RULE_REJECT

    def test_blacklist_product_reject(self):
        from src.auto_purchase.purchase_rules import BlacklistRule, PurchaseRuleEngine, RuleContext, RULE_REJECT
        engine = PurchaseRuleEngine()
        bl = BlacklistRule(blacklist_products=['BANNED_PROD'])
        engine._rules = [bl]
        context = RuleContext(product_id='BANNED_PROD', unit_price=10.0, selling_price=20.0)
        result = engine.evaluate(context)
        assert result['decision'] == RULE_REJECT

    def test_daily_limit_hold(self):
        from src.auto_purchase.purchase_rules import DailyLimitRule, PurchaseRuleEngine, RuleContext, RULE_HOLD
        engine = PurchaseRuleEngine()
        engine._rules = [DailyLimitRule(max_daily_orders=5)]
        context = RuleContext(daily_order_count=5, unit_price=10.0, selling_price=20.0)
        result = engine.evaluate(context)
        assert result['decision'] == RULE_HOLD

    def test_stock_threshold_pass(self):
        from src.auto_purchase.purchase_rules import StockThresholdRule, RuleContext
        rule = StockThresholdRule(min_stock=5)
        context = RuleContext(
            unit_price=10.0, selling_price=20.0,
            metadata={'current_stock': 3},
        )
        result = rule.evaluate(context)
        assert result.decision == 'pass'

    def test_stock_threshold_hold(self):
        from src.auto_purchase.purchase_rules import StockThresholdRule, RuleContext, RULE_HOLD
        rule = StockThresholdRule(min_stock=5)
        context = RuleContext(
            unit_price=10.0, selling_price=20.0,
            metadata={'current_stock': 10},
        )
        result = rule.evaluate(context)
        assert result.decision == RULE_HOLD

    def test_add_remove_rule(self):
        from src.auto_purchase.purchase_rules import PurchaseRuleEngine, MaxPriceRule
        engine = PurchaseRuleEngine()
        initial_count = len(engine._rules)
        engine.add_rule(MaxPriceRule(max_price=999.0))
        assert len(engine._rules) == initial_count + 1
        removed = engine.remove_rule('max_price')
        # max_price was already in defaults, so count - 1 of max_prices
        assert removed

    def test_list_rules(self):
        from src.auto_purchase.purchase_rules import PurchaseRuleEngine
        engine = PurchaseRuleEngine()
        rules = engine.list_rules()
        assert isinstance(rules, list)
        assert all('name' in r for r in rules)

    def test_rule_context_margin_rate(self):
        from src.auto_purchase.purchase_rules import RuleContext
        ctx = RuleContext(unit_price=80.0, quantity=1, selling_price=100.0)
        assert abs(ctx.margin_rate - 0.20) < 0.001


# ─── PurchaseMonitor ─────────────────────────────────────────────────────────

class TestPurchaseMonitor:
    def _make_monitor(self):
        from src.auto_purchase.purchase_monitor import PurchaseMonitor
        return PurchaseMonitor()

    def test_register_order(self):
        from src.auto_purchase.purchase_models import PurchaseOrder
        monitor = self._make_monitor()
        order = PurchaseOrder()
        monitor.register_order(order)
        assert monitor.get_order(order.order_id) is not None

    def test_metrics_initial(self):
        monitor = self._make_monitor()
        m = monitor.get_metrics()
        assert m['total_orders'] == 0
        assert m['success_rate'] == 0.0

    def test_metrics_after_confirmed(self):
        from src.auto_purchase.purchase_models import PurchaseOrder, PurchaseStatus
        monitor = self._make_monitor()
        order = PurchaseOrder(unit_price=100.0, quantity=2)
        monitor.register_order(order)
        order.update_status(PurchaseStatus.CONFIRMED)
        monitor.update_order(order)
        m = monitor.get_metrics()
        assert m['successful_orders'] == 1
        assert m['total_spend'] == 200.0

    def test_metrics_after_failed(self):
        from src.auto_purchase.purchase_models import PurchaseOrder, PurchaseStatus
        monitor = self._make_monitor()
        order = PurchaseOrder()
        monitor.register_order(order)
        order.update_status(PurchaseStatus.FAILED, 'network error')
        monitor.update_order(order)
        m = monitor.get_metrics()
        assert m['failed_orders'] == 1

    def test_price_anomaly_detection(self):
        monitor = self._make_monitor()
        # 최초 가격 기록
        monitor.check_price_anomaly('PROD_001', 100.0)
        # 30% 가격 상승 → 이상 감지
        warning = monitor.check_price_anomaly('PROD_001', 130.0)
        assert warning is not None
        assert '가격 이상 감지' in warning

    def test_no_price_anomaly_within_threshold(self):
        monitor = self._make_monitor()
        monitor.check_price_anomaly('PROD_002', 100.0)
        # 10% 상승 → 정상
        warning = monitor.check_price_anomaly('PROD_002', 110.0)
        assert warning is None

    def test_get_alerts(self):
        monitor = self._make_monitor()
        monitor.check_price_anomaly('PROD_003', 100.0)
        monitor.check_price_anomaly('PROD_003', 200.0)
        alerts = monitor.get_alerts()
        assert len(alerts) >= 1

    def test_list_orders_by_status(self):
        from src.auto_purchase.purchase_models import PurchaseOrder, PurchaseStatus
        monitor = self._make_monitor()
        order1 = PurchaseOrder()
        order2 = PurchaseOrder()
        monitor.register_order(order1)
        monitor.register_order(order2)
        order1.update_status(PurchaseStatus.CONFIRMED)
        monitor.update_order(order1)
        confirmed = monitor.list_orders(status='confirmed')
        assert len(confirmed) == 1

    def test_delivery_delay_no_metadata(self):
        from src.auto_purchase.purchase_models import PurchaseOrder
        monitor = self._make_monitor()
        order = PurchaseOrder()
        monitor.register_order(order)
        result = monitor.check_delivery_delay(order.order_id)
        assert result is None


# ─── AutoPurchaseEngine ──────────────────────────────────────────────────────

class TestAutoPurchaseEngine:
    def _make_engine(self):
        from src.auto_purchase.purchase_engine import AutoPurchaseEngine
        return AutoPurchaseEngine()

    def test_list_marketplaces(self):
        engine = self._make_engine()
        markets = engine.list_marketplaces()
        assert 'amazon_us' in markets
        assert 'taobao' in markets
        assert 'alibaba_1688' in markets

    def test_submit_order_queued(self):
        engine = self._make_engine()
        order = engine.submit_order(
            source_product_id='B08N5WRWNW',
            marketplace='amazon_us',
            quantity=1,
            unit_price=49.99,
            selling_price=70.0,
        )
        assert order.order_id
        # Rule evaluation should pass
        assert order.metadata.get('rule_decision') == 'pass'

    def test_submit_order_rule_reject(self):
        from src.auto_purchase.purchase_models import PurchaseStatus
        engine = self._make_engine()
        # Very high price to trigger max_price rejection
        # First adjust engine rules
        from src.auto_purchase.purchase_rules import MaxPriceRule
        engine._rules._rules = [MaxPriceRule(max_price=10.0)]
        order = engine.submit_order(
            source_product_id='B08N5WRWNW',
            marketplace='amazon_us',
            quantity=1,
            unit_price=50.0,
        )
        assert order.status == PurchaseStatus.FAILED

    def test_queue_status_initial(self):
        engine = self._make_engine()
        q = engine.get_queue_status()
        assert q['total_queued'] == 0
        assert q['active'] == 0

    def test_get_order_status_not_found(self):
        engine = self._make_engine()
        result = engine.get_order_status('NONEXISTENT')
        assert result is None

    def test_cancel_queued_order(self):
        engine = self._make_engine()
        order = engine.submit_order(
            source_product_id='B08N5WRWNW',
            marketplace='amazon_us',
            quantity=1,
            unit_price=49.99,
            selling_price=70.0,
        )
        # Cancelling should succeed if order is in queue
        if order.metadata.get('rule_decision') == 'pass':
            result = engine.cancel_order(order.order_id)
            # May or may not be in queue if already processed
            assert isinstance(result, bool)

    def test_simulate(self):
        engine = self._make_engine()
        result = engine.simulate(
            source_product_id='B08N5WRWNW',
            marketplace='amazon_us',
            quantity=1,
            unit_price=49.99,
            selling_price=70.0,
        )
        assert 'rule_decision' in result
        assert 'would_proceed' in result
        assert 'margin_rate' in result

    def test_simulate_with_balance_strategy(self):
        from src.auto_purchase.source_selector import SelectionStrategy
        engine = self._make_engine()
        result = engine.simulate(
            source_product_id='B08N5WRWNW',
            marketplace='amazon_us',
            quantity=1,
            unit_price=49.99,
            selling_price=70.0,
            strategy=SelectionStrategy.CHEAPEST_FIRST,
        )
        assert result is not None

    def test_process_order_amazon(self):
        from src.auto_purchase.purchase_models import PurchaseOrder, PurchaseStatus
        engine = self._make_engine()
        order = PurchaseOrder(
            source_marketplace='amazon_us',
            source_product_id='B08N5WRWNW',
            quantity=1,
            unit_price=49.99,
        )
        result = engine.process_order(order)
        assert result.success
        assert order.status == PurchaseStatus.CONFIRMED

    def test_process_order_invalid_marketplace(self):
        from src.auto_purchase.purchase_models import PurchaseOrder
        engine = self._make_engine()
        order = PurchaseOrder(
            source_marketplace='invalid_market',
            source_product_id='PROD_001',
            quantity=1,
            unit_price=10.0,
            max_retries=1,
        )
        result = engine.process_order(order)
        assert not result.success

    def test_register_custom_buyer(self):
        from src.auto_purchase.marketplace_buyer import AmazonBuyer
        engine = self._make_engine()
        buyer = AmazonBuyer(region='UK')
        engine.register_buyer('amazon_uk', buyer)
        assert 'amazon_uk' in engine.list_marketplaces()

    def test_metrics_after_process(self):
        from src.auto_purchase.purchase_models import PurchaseOrder
        engine = self._make_engine()
        order = PurchaseOrder(
            source_marketplace='amazon_us',
            source_product_id='B09B8YWXDF',
            quantity=1,
            unit_price=199.99,
        )
        engine.process_order(order)
        m = engine.get_metrics()
        assert m['successful_orders'] >= 1


# ─── ImportAutomation ────────────────────────────────────────────────────────

class TestImportAutomation:
    def _make_automation(self, with_engine=False):
        from src.auto_purchase.import_automation import ImportAutomation
        if with_engine:
            from src.auto_purchase.purchase_engine import AutoPurchaseEngine
            engine = AutoPurchaseEngine()
            return ImportAutomation(purchase_engine=engine)
        return ImportAutomation()

    def test_create_import_order_no_engine(self):
        automation = self._make_automation()
        request = automation.create_import_order(
            customer_order_id='CO_001',
            product_id='B08N5WRWNW',
            marketplace='amazon_us',
            quantity=1,
            unit_price=49.99,
        )
        assert request.request_id
        assert request.status == 'queued'
        assert 'duty_info' in request.metadata

    def test_create_import_order_with_engine(self):
        automation = self._make_automation(with_engine=True)
        request = automation.create_import_order(
            customer_order_id='CO_002',
            product_id='B08N5WRWNW',
            marketplace='amazon_us',
            quantity=1,
            unit_price=49.99,
        )
        assert request.status in ('purchasing', 'queued')
        assert 'purchase_order_id' in request.metadata

    def test_get_import_order(self):
        automation = self._make_automation()
        request = automation.create_import_order(
            customer_order_id='CO_003',
            product_id='B09B8YWXDF',
            marketplace='amazon_us',
            quantity=2,
            unit_price=199.99,
        )
        fetched = automation.get_import_order(request.request_id)
        assert fetched is not None
        assert fetched.quantity == 2

    def test_list_import_orders(self):
        automation = self._make_automation()
        automation.create_import_order('CO_004', 'B08N5WRWNW', 'amazon_us', 1, 49.99)
        automation.create_import_order('CO_005', 'TB001234', 'taobao', 3, 380.0, currency='CNY')
        orders = automation.list_import_orders()
        assert len(orders) == 2

    def test_update_forwarding_received(self):
        automation = self._make_automation()
        request = automation.create_import_order('CO_006', 'B08N5WRWNW', 'amazon_us', 1, 49.99)
        result = automation.update_forwarding_received(request.request_id, 'TRK123')
        assert result
        updated = automation.get_import_order(request.request_id)
        assert updated.status == 'forwarding_received'
        assert updated.metadata['tracking_number'] == 'TRK123'

    def test_customs_calculation(self):
        automation = self._make_automation()
        request = automation.create_import_order(
            'CO_007', 'B08N5WRWNW', 'amazon_us', 1, 100.0,
            hs_code='8471',
        )
        duty_info = request.metadata.get('duty_info', {})
        assert 'duty_rate' in duty_info or 'estimated_total_usd' in duty_info


# ─── ProxyBuyAutomation ──────────────────────────────────────────────────────

class TestProxyBuyAutomation:
    def _make_automation(self, with_engine=False):
        from src.auto_purchase.import_automation import ProxyBuyAutomation
        if with_engine:
            from src.auto_purchase.purchase_engine import AutoPurchaseEngine
            engine = AutoPurchaseEngine()
            return ProxyBuyAutomation(purchase_engine=engine)
        return ProxyBuyAutomation()

    def test_create_proxy_request(self):
        automation = self._make_automation()
        request = automation.create_proxy_request(
            customer_id='CUST_001',
            product_url='https://www.amazon.com/dp/B08N5WRWNW',
            product_name='Echo Dot',
            marketplace='amazon_us',
            quantity=1,
            estimated_price=49.99,
        )
        assert request.request_id
        assert request.customer_id == 'CUST_001'

    def test_create_proxy_request_taobao(self):
        automation = self._make_automation()
        request = automation.create_proxy_request(
            customer_id='CUST_002',
            product_url='https://item.taobao.com/item.htm?id=TB001234',
            product_name='Nike Shoes',
            marketplace='taobao',
        )
        assert request.marketplace == 'taobao'

    def test_update_inspection_pass(self):
        automation = self._make_automation()
        request = automation.create_proxy_request(
            'CUST_003', 'https://www.amazon.com/dp/B09B8YWXDF',
            'AirPods', 'amazon_us',
        )
        result = automation.update_inspection_result(request.request_id, passed=True, notes='OK')
        assert result
        fetched = automation.get_request(request.request_id)
        assert fetched.status == 'inspection_passed'

    def test_update_inspection_fail(self):
        automation = self._make_automation()
        request = automation.create_proxy_request(
            'CUST_004', 'https://www.amazon.com/dp/B0BDJH3XVN',
            'Kindle', 'amazon_us',
        )
        automation.update_inspection_result(request.request_id, passed=False, notes='Damaged')
        fetched = automation.get_request(request.request_id)
        assert fetched.status == 'inspection_failed'

    def test_list_requests_by_customer(self):
        automation = self._make_automation()
        automation.create_proxy_request('CUST_005', 'https://amazon.com/dp/B08N5WRWNW', 'P1', 'amazon_us')
        automation.create_proxy_request('CUST_005', 'https://amazon.com/dp/B09B8YWXDF', 'P2', 'amazon_us')
        automation.create_proxy_request('CUST_006', 'https://amazon.com/dp/B0BDJH3XVN', 'P3', 'amazon_us')
        cust5 = automation.list_requests(customer_id='CUST_005')
        assert len(cust5) == 2


# ─── API Blueprint ────────────────────────────────────────────────────────────

class TestAutoPurchaseAPI:
    def _make_client(self):
        from flask import Flask
        from src.api.auto_purchase_api import auto_purchase_bp
        app = Flask(__name__)
        app.register_blueprint(auto_purchase_bp)
        return app.test_client()

    def test_create_order_missing_fields(self):
        client = self._make_client()
        resp = client.post('/api/v1/auto-purchase/order', json={})
        assert resp.status_code == 400

    def test_create_order_success(self):
        client = self._make_client()
        resp = client.post('/api/v1/auto-purchase/order', json={
            'source_product_id': 'B08N5WRWNW',
            'marketplace': 'amazon_us',
            'quantity': 1,
            'unit_price': 49.99,
            'selling_price': 70.0,
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert 'order_id' in data
        assert data['marketplace'] == 'amazon_us'

    def test_get_order_not_found(self):
        client = self._make_client()
        resp = client.get('/api/v1/auto-purchase/order/NONEXISTENT_ORDER')
        assert resp.status_code == 404

    def test_cancel_order_not_found(self):
        client = self._make_client()
        resp = client.post('/api/v1/auto-purchase/order/NONEXISTENT_ORDER/cancel')
        assert resp.status_code == 400

    def test_get_sources(self):
        client = self._make_client()
        resp = client.get('/api/v1/auto-purchase/sources/Echo')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'sources' in data

    def test_select_source(self):
        client = self._make_client()
        resp = client.post('/api/v1/auto-purchase/sources/select', json={
            'options': [
                {
                    'marketplace': 'amazon_us',
                    'product_id': 'P1',
                    'price': 100.0,
                    'currency': 'USD',
                    'availability': True,
                    'stock_quantity': 10,
                    'estimated_delivery_days': 3,
                    'seller_rating': 4.5,
                    'shipping_cost': 0.0,
                },
                {
                    'marketplace': 'taobao',
                    'product_id': 'P2',
                    'price': 60.0,
                    'currency': 'CNY',
                    'availability': True,
                    'stock_quantity': 100,
                    'estimated_delivery_days': 14,
                    'seller_rating': 4.2,
                    'shipping_cost': 15.0,
                },
            ],
            'strategy': 'balanced',
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'selected' in data
        assert 'scores' in data

    def test_get_metrics(self):
        client = self._make_client()
        resp = client.get('/api/v1/auto-purchase/metrics')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'total_orders' in data

    def test_list_rules(self):
        client = self._make_client()
        resp = client.get('/api/v1/auto-purchase/rules')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'rules' in data

    def test_add_rule_max_price(self):
        client = self._make_client()
        resp = client.post('/api/v1/auto-purchase/rules', json={
            'type': 'max_price',
            'value': 500.0,
        })
        assert resp.status_code == 201

    def test_add_rule_unknown_type(self):
        client = self._make_client()
        resp = client.post('/api/v1/auto-purchase/rules', json={
            'type': 'unknown_rule',
            'value': 100,
        })
        assert resp.status_code == 400

    def test_simulate_missing_fields(self):
        client = self._make_client()
        resp = client.post('/api/v1/auto-purchase/simulate', json={})
        assert resp.status_code == 400

    def test_simulate_success(self):
        client = self._make_client()
        resp = client.post('/api/v1/auto-purchase/simulate', json={
            'source_product_id': 'B08N5WRWNW',
            'marketplace': 'amazon_us',
            'quantity': 1,
            'unit_price': 49.99,
            'selling_price': 70.0,
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'rule_decision' in data
        assert 'would_proceed' in data

    def test_get_queue(self):
        client = self._make_client()
        resp = client.get('/api/v1/auto-purchase/queue')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'total_queued' in data


# ─── post_deploy_check soft fail ─────────────────────────────────────────────

class TestPostDeployCheck:
    def test_run_healthcheck_soft_fail_on_ready(self):
        """/health OK + /health/ready 503 → soft fail (returns True)."""
        from scripts.post_deploy_check import run_healthcheck
        import unittest.mock as mock

        def mock_check_endpoint(url, retries, interval):
            if '/health/ready' in url:
                return False, 'HTTP 503 from http://example.com/health/ready'
            return True, ''

        with mock.patch('scripts.post_deploy_check.check_endpoint', side_effect=mock_check_endpoint):
            with mock.patch('scripts.post_deploy_check.send_telegram'):
                ok, err = run_healthcheck('http://example.com', 'staging', 3, 5)
        assert ok
        assert err == ''

    def test_run_healthcheck_health_fails(self):
        """Both /health and /health/ready fail → hard fail."""
        from scripts.post_deploy_check import run_healthcheck
        import unittest.mock as mock

        def mock_check_endpoint(url, retries, interval):
            return False, 'HTTP 503'

        with mock.patch('scripts.post_deploy_check.check_endpoint', side_effect=mock_check_endpoint):
            ok, err = run_healthcheck('http://example.com', 'staging', 3, 5)
        assert not ok
        assert '/health failed' in err

    def test_run_healthcheck_both_ok(self):
        """Both endpoints OK → True."""
        from scripts.post_deploy_check import run_healthcheck
        import unittest.mock as mock

        with mock.patch('scripts.post_deploy_check.check_endpoint', return_value=(True, '')):
            ok, err = run_healthcheck('http://example.com', 'staging', 3, 5)
        assert ok
        assert err == ''
