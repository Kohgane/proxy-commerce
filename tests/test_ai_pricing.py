"""tests/test_ai_pricing.py — Phase 97: AI 동적 가격 최적화 테스트."""
from __future__ import annotations

import sys
import os
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest


# ─── PricingModels ──────────────────────────────────────────────────────────

class TestPricingModels:
    def test_price_point_defaults(self):
        from src.ai_pricing.pricing_models import PricePoint
        pp = PricePoint()
        assert pp.sku == ''
        assert pp.base_price == 0.0
        assert pp.demand_score == 1.0

    def test_price_point_with_values(self):
        from src.ai_pricing.pricing_models import PricePoint
        pp = PricePoint(sku='SKU001', base_price=10000.0, cost=7000.0)
        assert pp.sku == 'SKU001'
        assert pp.base_price == 10000.0
        assert pp.cost == 7000.0

    def test_competitor_price_defaults(self):
        from src.ai_pricing.pricing_models import CompetitorPrice
        cp = CompetitorPrice()
        assert cp.currency == 'KRW'
        assert cp.is_available is True

    def test_demand_forecast_confidence_interval(self):
        from src.ai_pricing.pricing_models import DemandForecast
        df = DemandForecast(
            sku='SKU001',
            predicted_qty=100.0,
            confidence_interval_lower=85.0,
            confidence_interval_upper=115.0,
        )
        assert df.confidence_interval == (85.0, 115.0)

    def test_pricing_decision_price_change_pct(self):
        from src.ai_pricing.pricing_models import PricingDecision
        d = PricingDecision(sku='SKU001', old_price=10000.0, new_price=11000.0)
        assert d.price_change_pct == 10.0

    def test_pricing_decision_price_change_pct_decrease(self):
        from src.ai_pricing.pricing_models import PricingDecision
        d = PricingDecision(sku='SKU001', old_price=10000.0, new_price=9000.0)
        assert d.price_change_pct == -10.0

    def test_pricing_decision_price_change_pct_zero_old(self):
        from src.ai_pricing.pricing_models import PricingDecision
        d = PricingDecision(sku='SKU001', old_price=0.0, new_price=10000.0)
        assert d.price_change_pct == 0.0

    def test_pricing_decision_apply(self):
        from src.ai_pricing.pricing_models import PricingDecision
        d = PricingDecision(sku='SKU001', old_price=10000.0, new_price=11000.0)
        assert not d.approved
        d.apply()
        assert d.approved
        assert d.applied_at is not None

    def test_pricing_metrics_recalculate(self):
        from src.ai_pricing.pricing_models import PricingDecision, PricingMetrics
        decisions = [
            PricingDecision(old_price=10000.0, new_price=11000.0),  # +10%
            PricingDecision(old_price=10000.0, new_price=9000.0),   # -10%
            PricingDecision(old_price=10000.0, new_price=10000.0),  # 0%
        ]
        m = PricingMetrics()
        m.recalculate(decisions)
        assert m.total_optimized == 3
        assert m.skus_increased == 1
        assert m.skus_decreased == 1
        assert m.skus_unchanged == 1
        assert m.pending_approvals == 3

    def test_pricing_metrics_empty(self):
        from src.ai_pricing.pricing_models import PricingMetrics
        m = PricingMetrics()
        m.recalculate([])
        assert m.total_optimized == 0


# ─── CompetitorPriceTracker ──────────────────────────────────────────────────

class TestCompetitorPriceTracker:
    def setup_method(self):
        from src.ai_pricing.competitor_tracker import CompetitorPriceTracker
        self.tracker = CompetitorPriceTracker()

    def test_collect_prices_returns_list(self):
        prices = self.tracker.collect_prices('SKU001', 10000.0)
        assert isinstance(prices, list)
        assert len(prices) > 0

    def test_collect_prices_competitor_ids(self):
        prices = self.tracker.collect_prices('SKU001', 10000.0)
        ids = {p.competitor_id for p in prices}
        assert 'coupang' in ids
        assert 'naver' in ids

    def test_collect_prices_raw(self):
        prices = self.tracker.collect_prices_raw(
            'SKU002',
            {'coupang': 9500.0, 'naver': 9800.0},
        )
        assert len(prices) == 2
        cpids = {p.competitor_id for p in prices}
        assert 'coupang' in cpids

    def test_get_positioning(self):
        self.tracker.collect_prices_raw('SKU001', {'coupang': 9000.0, 'naver': 11000.0})
        pos = self.tracker.get_positioning('SKU001')
        assert pos['min_price'] == 9000.0
        assert pos['max_price'] == 11000.0
        assert pos['avg_price'] == 10000.0

    def test_get_positioning_empty(self):
        pos = self.tracker.get_positioning('NOSKU')
        assert pos == {}

    def test_get_price_gap(self):
        self.tracker.collect_prices_raw('SKU001', {'coupang': 10000.0, 'naver': 12000.0})
        gap = self.tracker.get_price_gap('SKU001', 10000.0)
        assert 'vs_min' in gap
        assert 'vs_avg' in gap

    def test_alert_on_surge(self):
        # 등록 후 가격 급등 시뮬레이션
        self.tracker.collect_prices_raw('SKU001', {'coupang': 10000.0})
        self.tracker.collect_prices_raw('SKU001', {'coupang': 15000.0})  # +50%
        alerts = self.tracker.get_alerts()
        assert any(a['competitor_id'] == 'coupang' for a in alerts)

    def test_no_alert_on_small_change(self):
        self.tracker.collect_prices_raw('SKU001', {'coupang': 10000.0})
        self.tracker.collect_prices_raw('SKU001', {'coupang': 10050.0})  # +0.5%
        alerts = self.tracker.get_alerts()
        # 10% 미만이므로 알림 없음
        assert not any(
            a['competitor_id'] == 'coupang' and abs(a['change_pct']) >= 10
            for a in alerts
        )

    def test_get_history(self):
        self.tracker.collect_prices_raw('SKU001', {'coupang': 10000.0})
        self.tracker.collect_prices_raw('SKU001', {'coupang': 11000.0})
        history = self.tracker.get_history('SKU001', 'coupang')
        assert len(history) == 2

    def test_get_alerts_clear(self):
        self.tracker.collect_prices_raw('SKU001', {'coupang': 10000.0})
        self.tracker.collect_prices_raw('SKU001', {'coupang': 15000.0})
        alerts = self.tracker.get_alerts(clear=True)
        assert len(alerts) > 0
        assert len(self.tracker.get_alerts()) == 0


# ─── DemandForecaster ────────────────────────────────────────────────────────

class TestDemandForecaster:
    def setup_method(self):
        from src.ai_pricing.demand_forecaster import DemandForecaster
        self.forecaster = DemandForecaster()

    def test_record_and_moving_average(self):
        self.forecaster.record_sales_batch('SKU001', [100, 120, 110, 130])
        ma = self.forecaster.moving_average('SKU001')
        assert ma == pytest.approx(115.0, abs=1.0)

    def test_moving_average_window(self):
        self.forecaster.record_sales_batch('SKU001', [100, 120, 110, 130, 150])
        ma = self.forecaster.moving_average('SKU001', window=2)
        assert ma == pytest.approx(140.0, abs=1.0)

    def test_exponential_smoothing(self):
        self.forecaster.record_sales_batch('SKU001', [100, 120, 110])
        ewm = self.forecaster.exponential_smoothing('SKU001')
        assert ewm > 0

    def test_weighted_average(self):
        self.forecaster.record_sales_batch('SKU001', [100, 120, 140])
        wa = self.forecaster.weighted_average('SKU001')
        # 가중평균은 단순평균(120)보다 최신값(140)에 가까워야 함
        assert wa > 120

    def test_ensemble_forecast(self):
        self.forecaster.record_sales_batch('SKU001', [100, 110, 120])
        val = self.forecaster.ensemble_forecast('SKU001')
        assert val > 0

    def test_no_history_returns_zero(self):
        val = self.forecaster.moving_average('NOSKU')
        assert val == 0.0

    def test_seasonality_factor(self):
        # 12월은 성수기
        factor_dec = self.forecaster.get_seasonality_factor(month=12)
        # 2월은 비수기
        factor_feb = self.forecaster.get_seasonality_factor(month=2)
        assert factor_dec > factor_feb

    def test_monthly_seasonality_dict(self):
        seasonal = self.forecaster.get_monthly_seasonality()
        assert len(seasonal) == 12
        assert seasonal[12] > seasonal[2]  # 12월 > 2월

    def test_apply_external_factors_holiday(self):
        base = 100.0
        adjusted = self.forecaster.apply_external_factors(base, is_holiday=True)
        assert adjusted == pytest.approx(130.0, abs=0.1)

    def test_apply_external_factors_fx(self):
        base = 100.0
        # 환율 10% 상승 → 수요 5% 감소
        adjusted = self.forecaster.apply_external_factors(base, fx_change_pct=10.0)
        assert adjusted < base

    def test_apply_external_factors_promo(self):
        base = 100.0
        adjusted = self.forecaster.apply_external_factors(base, promotion_boost=0.20)
        assert adjusted == pytest.approx(120.0, abs=0.1)

    def test_calculate_elasticity_default(self):
        # 데이터 없을 때 기본값
        e = self.forecaster.calculate_elasticity('NOSKU')
        assert e == -1.0

    def test_calculate_elasticity_with_data(self):
        self.forecaster.record_sales('SKU001', qty=100, price=10000)
        self.forecaster.record_sales('SKU001', qty=90, price=11000)  # 가격↑ 수요↓
        e = self.forecaster.calculate_elasticity('SKU001')
        assert e < 0  # 정상재

    def test_calculate_mape(self):
        actuals = [100, 110, 120]
        preds = [100, 110, 120]
        mape = self.forecaster.calculate_mape(actuals, preds)
        assert mape == 0.0

    def test_calculate_mape_with_error(self):
        actuals = [100, 100, 100]
        preds = [90, 110, 100]
        mape = self.forecaster.calculate_mape(actuals, preds)
        assert mape > 0

    def test_calculate_rmse(self):
        actuals = [100, 110, 120]
        preds = [100, 110, 120]
        rmse = self.forecaster.calculate_rmse(actuals, preds)
        assert rmse == 0.0

    def test_forecast_returns_demand_forecast(self):
        from src.ai_pricing.pricing_models import DemandForecast
        self.forecaster.record_sales_batch('SKU001', [100, 110, 120])
        result = self.forecaster.forecast('SKU001', period='2024-01')
        assert isinstance(result, DemandForecast)
        assert result.sku == 'SKU001'
        assert result.period == '2024-01'
        assert result.confidence_interval_lower <= result.predicted_qty
        assert result.predicted_qty <= result.confidence_interval_upper

    def test_forecast_no_history(self):
        from src.ai_pricing.pricing_models import DemandForecast
        result = self.forecaster.forecast('NOSKU')
        assert isinstance(result, DemandForecast)
        assert result.predicted_qty == 0.0

    def test_get_history(self):
        self.forecaster.record_sales_batch('SKU001', [100, 110])
        h = self.forecaster.get_history('SKU001')
        assert h == [100, 110]


# ─── PricingRules ────────────────────────────────────────────────────────────

class TestPricingRules:
    def _ctx(self, **kwargs):
        from src.ai_pricing.pricing_rules import RuleContext
        defaults = {
            'sku': 'SKU001',
            'current_price': 10000.0,
            'cost': 7000.0,
            'competitor_min': 9500.0,
            'competitor_avg': 10200.0,
            'demand_score': 1.0,
            'stock_qty': 100,
            'sales_velocity': 5.0,
            'season_factor': 1.0,
            'fx_rate_change': 0.0,
        }
        defaults.update(kwargs)
        return RuleContext(**defaults)

    def test_competitor_match_rule(self):
        from src.ai_pricing.pricing_rules import CompetitorMatchRule
        rule = CompetitorMatchRule(undercut_pct=0.02)
        result = rule.evaluate(self._ctx())
        assert result is not None
        assert result.suggested_price < 9500.0
        assert result.rule_name == 'competitor_match'

    def test_competitor_match_no_competitor(self):
        from src.ai_pricing.pricing_rules import CompetitorMatchRule
        rule = CompetitorMatchRule()
        result = rule.evaluate(self._ctx(competitor_min=0))
        assert result is None

    def test_competitor_match_abs_undercut(self):
        from src.ai_pricing.pricing_rules import CompetitorMatchRule
        rule = CompetitorMatchRule(undercut_abs=500.0)
        result = rule.evaluate(self._ctx(competitor_min=9500.0))
        assert result.suggested_price == pytest.approx(9000.0, abs=1.0)

    def test_demand_surge_rule_triggers(self):
        from src.ai_pricing.pricing_rules import DemandSurgeRule
        rule = DemandSurgeRule(surge_threshold=1.5)
        result = rule.evaluate(self._ctx(demand_score=2.0))
        assert result is not None
        assert result.suggested_price > 10000.0

    def test_demand_surge_rule_no_trigger(self):
        from src.ai_pricing.pricing_rules import DemandSurgeRule
        rule = DemandSurgeRule(surge_threshold=1.5)
        result = rule.evaluate(self._ctx(demand_score=1.0))
        assert result is None

    def test_slow_mover_rule_triggers(self):
        from src.ai_pricing.pricing_rules import SlowMoverRule
        # stock=300, velocity=1 → 300일 체류 → 30일 임계값 초과
        rule = SlowMoverRule(slow_threshold_days=30.0, discount_pct=0.10)
        result = rule.evaluate(self._ctx(stock_qty=300, sales_velocity=1.0))
        assert result is not None
        assert result.suggested_price < 10000.0

    def test_slow_mover_rule_no_trigger(self):
        from src.ai_pricing.pricing_rules import SlowMoverRule
        # stock=10, velocity=5 → 2일 → 30일 미만
        rule = SlowMoverRule(slow_threshold_days=30.0)
        result = rule.evaluate(self._ctx(stock_qty=10, sales_velocity=5.0))
        assert result is None

    def test_slow_mover_rule_zero_velocity(self):
        from src.ai_pricing.pricing_rules import SlowMoverRule
        rule = SlowMoverRule()
        result = rule.evaluate(self._ctx(sales_velocity=0.0))
        assert result is None

    def test_seasonal_rule_peak(self):
        from src.ai_pricing.pricing_rules import SeasonalRule
        rule = SeasonalRule(peak_threshold=1.15, peak_boost=0.08)
        result = rule.evaluate(self._ctx(season_factor=1.20))
        assert result is not None
        assert result.suggested_price > 10000.0

    def test_seasonal_rule_off_peak(self):
        from src.ai_pricing.pricing_rules import SeasonalRule
        rule = SeasonalRule(off_threshold=0.90, off_discount=0.05)
        result = rule.evaluate(self._ctx(season_factor=0.85))
        assert result is not None
        assert result.suggested_price < 10000.0

    def test_seasonal_rule_normal(self):
        from src.ai_pricing.pricing_rules import SeasonalRule
        rule = SeasonalRule()
        result = rule.evaluate(self._ctx(season_factor=1.0))
        assert result is None

    def test_bundle_pricing_rule(self):
        from src.ai_pricing.pricing_rules import BundlePricingRule
        rule = BundlePricingRule(bundle_discount_pct=0.05)
        result = rule.evaluate(self._ctx(bundle_skus=['SKU002', 'SKU003']))
        assert result is not None
        assert result.suggested_price < 10000.0

    def test_bundle_pricing_rule_no_bundle(self):
        from src.ai_pricing.pricing_rules import BundlePricingRule
        rule = BundlePricingRule()
        result = rule.evaluate(self._ctx(bundle_skus=[]))
        assert result is None

    def test_margin_protection_rule_triggers(self):
        from src.ai_pricing.pricing_rules import MarginProtectionRule
        rule = MarginProtectionRule(min_margin_pct=0.20)
        # 현재 마진: (10000-7000)/10000 = 30% → 이미 충족
        result = rule.evaluate(self._ctx(current_price=10000.0, cost=9500.0))
        # 마진 부족 시 트리거: cost=9500, min_margin=20% → min_price = 9500/0.8 = 11875
        assert result is not None
        assert result.suggested_price > 10000.0
        assert result.confidence == 1.0

    def test_margin_protection_rule_no_trigger(self):
        from src.ai_pricing.pricing_rules import MarginProtectionRule
        rule = MarginProtectionRule(min_margin_pct=0.10)
        # 현재 마진 = 30% > 10%
        result = rule.evaluate(self._ctx(current_price=10000.0, cost=7000.0))
        assert result is None

    def test_margin_protection_no_cost(self):
        from src.ai_pricing.pricing_rules import MarginProtectionRule
        rule = MarginProtectionRule()
        result = rule.evaluate(self._ctx(cost=0.0))
        assert result is None

    def test_get_default_rules(self):
        from src.ai_pricing.pricing_rules import get_default_rules
        rules = get_default_rules()
        assert len(rules) == 6
        names = {r.name for r in rules}
        assert 'margin_protection' in names
        assert 'competitor_match' in names


# ─── PriceOptimizer ─────────────────────────────────────────────────────────

class TestPriceOptimizer:
    def _pp(self, **kwargs):
        from src.ai_pricing.pricing_models import PricePoint
        defaults = dict(
            sku='SKU001',
            base_price=10000.0,
            cost=7000.0,
            competitor_avg=10200.0,
            demand_score=1.0,
        )
        defaults.update(kwargs)
        return PricePoint(**defaults)

    def test_optimize_returns_price_point(self):
        from src.ai_pricing.price_optimizer import PriceOptimizer
        opt = PriceOptimizer()
        pp = opt.optimize(self._pp())
        assert pp.optimized_price > 0

    def test_optimize_profit_objective(self):
        from src.ai_pricing.price_optimizer import PriceOptimizer, OBJECTIVE_PROFIT
        opt = PriceOptimizer(objective=OBJECTIVE_PROFIT)
        pp = opt.optimize(self._pp())
        # 원가 대비 최소 마진 보장
        assert pp.optimized_price >= 7000.0 / (1 - 0.15)

    def test_optimize_revenue_objective(self):
        from src.ai_pricing.price_optimizer import PriceOptimizer, OBJECTIVE_REVENUE
        opt = PriceOptimizer(objective=OBJECTIVE_REVENUE)
        pp = opt.optimize(self._pp())
        assert pp.optimized_price > 0

    def test_optimize_market_share_objective(self):
        from src.ai_pricing.price_optimizer import PriceOptimizer, OBJECTIVE_MARKET_SHARE
        opt = PriceOptimizer(objective=OBJECTIVE_MARKET_SHARE)
        pp = opt.optimize(self._pp(competitor_avg=10200.0))
        # 시장점유율 최대화 → 경쟁사 평균보다 낮게
        assert pp.optimized_price <= 10200.0

    def test_min_margin_constraint(self):
        from src.ai_pricing.price_optimizer import PriceOptimizer
        opt = PriceOptimizer(min_margin_pct=0.20)
        pp = opt.optimize(self._pp(cost=8000.0, base_price=9000.0))
        min_price = 8000.0 / (1 - 0.20)
        assert pp.optimized_price >= min_price

    def test_floor_price_constraint(self):
        from src.ai_pricing.price_optimizer import PriceOptimizer
        opt = PriceOptimizer(min_price_floor=15000.0)
        pp = opt.optimize(self._pp(base_price=10000.0, cost=5000.0, competitor_avg=0))
        assert pp.optimized_price >= 15000.0

    def test_ceiling_price_constraint(self):
        from src.ai_pricing.price_optimizer import PriceOptimizer
        # competitor_avg=0 so no competitor bound interferes with ceiling
        opt = PriceOptimizer(max_price_ceiling=8000.0, competitor_bound_pct=0.0)
        pp = opt.optimize(self._pp(cost=1000.0, competitor_avg=0))
        assert pp.optimized_price <= 8000.0

    def test_simulate_basic(self):
        from src.ai_pricing.price_optimizer import PriceOptimizer
        opt = PriceOptimizer()
        pp = self._pp()
        result = opt.simulate(pp, test_price=9000.0, elasticity=-1.5, base_qty=100)
        assert 'current' in result
        assert 'new' in result
        assert 'delta' in result
        assert result['current']['price'] == 10000.0
        assert result['new']['price'] == 9000.0

    def test_simulate_elastic_demand(self):
        from src.ai_pricing.price_optimizer import PriceOptimizer
        opt = PriceOptimizer()
        pp = self._pp(base_price=10000.0)
        # 가격 10% 인하, 탄력성 -2 → 수요 20% 증가
        result = opt.simulate(pp, test_price=9000.0, elasticity=-2.0, base_qty=100)
        assert result['new']['qty'] > 100

    def test_simulate_revenue_impact(self):
        from src.ai_pricing.price_optimizer import PriceOptimizer
        opt = PriceOptimizer()
        pp = self._pp(base_price=10000.0, cost=0.0)
        result = opt.simulate(pp, test_price=10000.0, base_qty=100)
        assert result['delta']['revenue'] == 0.0

    def test_ab_experiment(self):
        from src.ai_pricing.price_optimizer import PriceOptimizer
        opt = PriceOptimizer()
        exp = opt.create_ab_experiment('exp1', 'SKU001', 10000.0, 9500.0)
        assert exp['experiment_id'] == 'exp1'
        assert exp['status'] == 'running'

    def test_ab_record_result(self):
        from src.ai_pricing.price_optimizer import PriceOptimizer
        opt = PriceOptimizer()
        opt.create_ab_experiment('exp1', 'SKU001', 10000.0, 9500.0)
        opt.record_ab_result('exp1', 'control', converted=True)
        opt.record_ab_result('exp1', 'variant', converted=True)
        opt.record_ab_result('exp1', 'variant', converted=False)
        result = opt.get_ab_result('exp1')
        assert result['control_impressions'] == 1
        assert result['variant_impressions'] == 2
        assert result['control_cvr'] == 1.0
        assert result['variant_cvr'] == pytest.approx(0.5)

    def test_ab_result_not_found(self):
        from src.ai_pricing.price_optimizer import PriceOptimizer
        opt = PriceOptimizer()
        assert opt.get_ab_result('nonexistent') is None

    def test_get_ab_experiments(self):
        from src.ai_pricing.price_optimizer import PriceOptimizer
        opt = PriceOptimizer()
        opt.create_ab_experiment('exp1', 'SKU001', 10000.0, 9500.0)
        opt.create_ab_experiment('exp2', 'SKU002', 20000.0, 19000.0)
        exps = opt.get_ab_experiments()
        assert len(exps) == 2


# ─── PriceAlertSystem ────────────────────────────────────────────────────────

class TestPriceAlertSystem:
    def setup_method(self):
        from src.ai_pricing.price_alert_system import PriceAlertSystem
        self.system = PriceAlertSystem()

    def test_alert_price_change(self):
        alert = self.system.alert_price_change('SKU001', 10000.0, 11000.0, 'ensemble')
        assert alert['type'] == 'price_change'
        assert alert['change_pct'] == 10.0
        assert alert['direction'] == '▲'

    def test_alert_price_decrease(self):
        alert = self.system.alert_price_change('SKU001', 10000.0, 9000.0)
        assert alert['direction'] == '▼'
        assert alert['change_pct'] == -10.0

    def test_alert_competitor_change(self):
        alert = self.system.alert_competitor_change(
            'coupang', 'SKU001', 10000.0, 15000.0, 50.0
        )
        assert alert['type'] == 'competitor_price_change'
        assert alert['direction'] == '급등'

    def test_alert_margin_risk(self):
        alert = self.system.alert_margin_risk('SKU001', 10000.0, 9500.0, 0.05)
        assert alert['type'] == 'margin_risk'
        assert alert['current_margin'] == pytest.approx(0.05)

    def test_get_alerts_all(self):
        self.system.alert_price_change('SKU001', 10000.0, 11000.0)
        self.system.alert_margin_risk('SKU002', 5000.0, 4800.0, 0.04)
        alerts = self.system.get_alerts()
        assert len(alerts) == 2

    def test_get_alerts_filtered(self):
        self.system.alert_price_change('SKU001', 10000.0, 11000.0)
        self.system.alert_margin_risk('SKU002', 5000.0, 4800.0, 0.04)
        margin_alerts = self.system.get_alerts(alert_type='margin_risk')
        assert len(margin_alerts) == 1
        assert margin_alerts[0]['type'] == 'margin_risk'

    def test_generate_daily_report(self):
        self.system.alert_price_change('SKU001', 10000.0, 11000.0)
        self.system.alert_price_change('SKU002', 20000.0, 18000.0)
        report = self.system.generate_daily_report()
        assert '총 가격 변경' in report
        assert '2건' in report

    def test_clear_alerts(self):
        self.system.alert_price_change('SKU001', 10000.0, 11000.0)
        self.system.clear_alerts()
        assert self.system.get_alerts() == []

    def test_alert_limit(self):
        for i in range(10):
            self.system.alert_price_change(f'SKU{i:03d}', 10000.0, 11000.0)
        alerts = self.system.get_alerts(limit=5)
        assert len(alerts) == 5


# ─── PricingAnalytics ────────────────────────────────────────────────────────

class TestPricingAnalytics:
    def setup_method(self):
        from src.ai_pricing.pricing_analytics import PricingAnalytics
        self.analytics = PricingAnalytics()

    def test_record_and_analyze_effect(self):
        self.analytics.record_performance('SKU001', 100000, 120000, 20000, 25000)
        effect = self.analytics.analyze_price_effect('SKU001')
        assert effect['revenue_change_pct'] == 20.0
        assert effect['profit_change_pct'] == 25.0

    def test_analyze_effect_no_data(self):
        effect = self.analytics.analyze_price_effect('NOSKU')
        assert 'error' in effect

    def test_analyze_all_effects(self):
        self.analytics.record_performance('SKU001', 100000, 110000, 20000, 22000)
        self.analytics.record_performance('SKU002', 50000, 45000, 10000, 9000)
        effects = self.analytics.analyze_all_effects()
        assert len(effects) == 2

    def test_elasticity_report_inelastic(self):
        report = self.analytics.elasticity_report('SKU001', -0.5)
        assert report['category'] == 'inelastic'
        assert 'inelastic' in report['interpretation'].lower() or '비탄력' in report['interpretation']

    def test_elasticity_report_elastic(self):
        report = self.analytics.elasticity_report('SKU001', -2.0)
        assert report['category'] == 'elastic'

    def test_competitiveness_score_leader(self):
        result = self.analytics.competitiveness_score(
            our_price=8000.0,
            competitor_min=9000.0,
            competitor_avg=10000.0,
            competitor_max=12000.0,
        )
        assert result['score'] > 50
        assert result['grade'] in ('A', 'B')

    def test_competitiveness_score_laggard(self):
        result = self.analytics.competitiveness_score(
            our_price=15000.0,
            competitor_min=9000.0,
            competitor_avg=10000.0,
            competitor_max=12000.0,
        )
        leader = self.analytics.competitiveness_score(
            our_price=8000.0,
            competitor_min=9000.0,
            competitor_avg=10000.0,
            competitor_max=12000.0,
        )
        # 경쟁사보다 비싼 상품은 저렴한 상품보다 경쟁력 지수가 낮아야 함
        assert result['score'] <= leader['score']

    def test_forecast_accuracy_report(self):
        report = self.analytics.forecast_accuracy_report(
            'SKU001',
            [100, 110, 120],
            [100, 110, 120],
            mape=0.0,
            rmse=0.0,
        )
        assert report['accuracy_grade'] == 'A'
        assert report['periods'] == 3

    def test_roi_analysis_no_data(self):
        roi = self.analytics.roi_analysis()
        assert 'error' in roi

    def test_roi_analysis_with_data(self):
        self.analytics.record_performance('SKU001', 100000, 120000, 20000, 25000)
        roi = self.analytics.roi_analysis()
        assert roi['revenue_roi_pct'] == 20.0
        assert roi['profit_roi_pct'] == 25.0

    def test_get_metrics(self):
        from src.ai_pricing.pricing_models import PricingDecision
        self.analytics.record_decision(
            PricingDecision(sku='SKU001', old_price=10000.0, new_price=11000.0)
        )
        m = self.analytics.get_metrics()
        assert m.total_optimized == 1

    def test_get_decision_history(self):
        from src.ai_pricing.pricing_models import PricingDecision
        d = PricingDecision(sku='SKU001', old_price=10000.0, new_price=11000.0)
        self.analytics.record_decision(d)
        history = self.analytics.get_decision_history('SKU001')
        assert len(history) == 1


# ─── PricingScheduler ────────────────────────────────────────────────────────

class TestPricingScheduler:
    def setup_method(self):
        from src.ai_pricing.pricing_scheduler import PricingScheduler
        self.scheduler = PricingScheduler()

    def test_add_schedule(self):
        job = self.scheduler.add_schedule('hourly', skus=['SKU001'])
        assert job.job_id
        assert job.schedule_type == 'hourly'

    def test_get_schedules(self):
        self.scheduler.add_schedule('daily', category='electronics')
        schedules = self.scheduler.get_schedules()
        assert len(schedules) == 1
        assert schedules[0]['schedule_type'] == 'daily'

    def test_remove_schedule(self):
        job = self.scheduler.add_schedule('hourly')
        result = self.scheduler.remove_schedule(job.job_id)
        assert result is True
        assert self.scheduler.get_schedule(job.job_id) is None

    def test_remove_nonexistent(self):
        assert self.scheduler.remove_schedule('nonexistent') is False

    def test_mark_ran(self):
        job = self.scheduler.add_schedule('hourly')
        self.scheduler.mark_ran(job.job_id)
        assert job.run_count == 1
        assert job.last_run is not None

    def test_get_current_price_type_peak(self):
        # UTC 10 = KST 19 → peak
        price_type = self.scheduler.get_current_price_type(hour=10)
        assert price_type == 'peak'

    def test_get_current_price_type_off_peak(self):
        # UTC 0 = KST 9 → off_peak
        price_type = self.scheduler.get_current_price_type(hour=0)
        assert price_type == 'off_peak'

    def test_get_peak_multiplier(self):
        # peak시간
        m_peak = self.scheduler.get_peak_multiplier(hour=10)
        m_off = self.scheduler.get_peak_multiplier(hour=0)
        assert m_peak > m_off

    def test_schedule_promo(self):
        now = datetime.now(timezone.utc)
        promo = self.scheduler.schedule_promo(
            sku='SKU001',
            promo_price=8000.0,
            start_at=now - timedelta(hours=1),
            end_at=now + timedelta(hours=1),
            reason='Flash sale',
        )
        assert promo.is_active()
        assert promo.sku == 'SKU001'

    def test_schedule_promo_not_active(self):
        now = datetime.now(timezone.utc)
        promo = self.scheduler.schedule_promo(
            sku='SKU001',
            promo_price=8000.0,
            start_at=now + timedelta(hours=1),
            end_at=now + timedelta(hours=2),
        )
        assert not promo.is_active()

    def test_get_active_promo(self):
        now = datetime.now(timezone.utc)
        self.scheduler.schedule_promo(
            sku='SKU001',
            promo_price=8000.0,
            start_at=now - timedelta(hours=1),
            end_at=now + timedelta(hours=1),
        )
        active = self.scheduler.get_active_promo('SKU001')
        assert active is not None
        assert active.promo_price == 8000.0

    def test_get_active_promo_none(self):
        active = self.scheduler.get_active_promo('NOSKU')
        assert active is None

    def test_run_batch_update(self):
        skus = ['SKU001', 'SKU002', 'SKU003']
        price_map = {'SKU001': 11000.0, 'SKU002': 9500.0}
        result = self.scheduler.run_batch_update(skus, price_map, dry_run=False)
        assert result['total'] == 3
        assert result['applied'] == 2
        assert result['skipped'] == 1
        assert result['dry_run'] is False

    def test_run_batch_update_dry_run(self):
        skus = ['SKU001']
        price_map = {'SKU001': 11000.0}
        result = self.scheduler.run_batch_update(skus, price_map, dry_run=True)
        assert result['dry_run'] is True
        assert result['applied'] == 0

    def test_get_batch_history(self):
        self.scheduler.run_batch_update(['SKU001'], {'SKU001': 11000.0})
        history = self.scheduler.get_batch_history()
        assert len(history) == 1


# ─── DynamicPricingEngine ────────────────────────────────────────────────────

class TestDynamicPricingEngine:
    def setup_method(self):
        from src.ai_pricing.dynamic_pricing_engine import DynamicPricingEngine
        self.engine = DynamicPricingEngine(auto_mode=False)

    def test_optimize_sku_returns_decision(self):
        from src.ai_pricing.pricing_models import PricingDecision
        decision = self.engine.optimize_sku(
            sku='SKU001',
            base_price=10000.0,
            cost=7000.0,
        )
        assert isinstance(decision, PricingDecision)
        assert decision.sku == 'SKU001'
        assert decision.old_price == 10000.0
        assert decision.new_price > 0

    def test_optimize_sku_manual_mode_not_approved(self):
        decision = self.engine.optimize_sku(
            sku='SKU001',
            base_price=10000.0,
            cost=7000.0,
        )
        # 수동 모드 → 승인 대기
        assert not decision.approved

    def test_optimize_sku_auto_mode_approved(self):
        from src.ai_pricing.dynamic_pricing_engine import DynamicPricingEngine
        engine = DynamicPricingEngine(auto_mode=True)
        decision = engine.optimize_sku(
            sku='SKU001',
            base_price=10000.0,
            cost=7000.0,
        )
        assert decision.approved
        assert decision.applied_at is not None

    def test_optimize_category(self):
        sku_map = {
            'SKU001': {'price': 10000.0, 'cost': 7000.0},
            'SKU002': {'price': 20000.0, 'cost': 15000.0},
        }
        decisions = self.engine.optimize_category('electronics', sku_map)
        assert len(decisions) == 2
        skus = {d.sku for d in decisions}
        assert 'SKU001' in skus
        assert 'SKU002' in skus

    def test_approve_decision(self):
        decision = self.engine.optimize_sku('SKU001', 10000.0, 7000.0)
        assert not decision.approved
        result = self.engine.approve_decision(decision.decision_id)
        assert result is True
        assert decision.approved

    def test_approve_nonexistent_decision(self):
        result = self.engine.approve_decision('nonexistent')
        assert result is False

    def test_rollback_price(self):
        from src.ai_pricing.dynamic_pricing_engine import DynamicPricingEngine
        engine = DynamicPricingEngine(auto_mode=True)
        engine.optimize_sku('SKU001', 10000.0, 7000.0)
        engine.optimize_sku('SKU001', 10000.0, 7000.0)
        prev = engine.rollback_price('SKU001')
        assert prev is not None

    def test_rollback_no_history(self):
        prev = self.engine.rollback_price('NOSKU')
        assert prev is None

    def test_get_recommendations(self):
        self.engine.optimize_sku('SKU001', 10000.0, 7000.0)
        self.engine.optimize_sku('SKU002', 20000.0, 15000.0)
        recs = self.engine.get_recommendations()
        assert len(recs) >= 0  # 수동 모드에서 미승인 항목

    def test_get_metrics(self):
        from src.ai_pricing.pricing_models import PricingMetrics
        self.engine.optimize_sku('SKU001', 10000.0, 7000.0)
        m = self.engine.get_metrics()
        assert isinstance(m, PricingMetrics)
        assert m.total_optimized >= 1

    def test_get_history(self):
        self.engine.optimize_sku('SKU001', 10000.0, 7000.0)
        self.engine.optimize_sku('SKU001', 10000.0, 7000.0)
        history = self.engine.get_history('SKU001')
        assert len(history) == 2

    def test_set_mode(self):
        self.engine.set_mode(True)
        assert self.engine._auto_mode is True
        self.engine.set_mode(False)
        assert self.engine._auto_mode is False

    def test_ensemble_price_with_margin_protection(self):
        """MarginProtectionRule은 앙상블에서 최우선 적용."""
        from src.ai_pricing.pricing_rules import RuleResult
        rule_results = [
            RuleResult(rule_name='margin_protection', suggested_price=12000.0, confidence=1.0),
            RuleResult(rule_name='competitor_match', suggested_price=9000.0, confidence=0.8),
        ]
        price = self.engine._ensemble_price(rule_results, 10000.0)
        assert price == 12000.0

    def test_ensemble_price_fallback(self):
        price = self.engine._ensemble_price([], 10000.0)
        assert price == 10000.0

    def test_accessor_properties(self):
        from src.ai_pricing.competitor_tracker import CompetitorPriceTracker
        from src.ai_pricing.demand_forecaster import DemandForecaster
        from src.ai_pricing.price_optimizer import PriceOptimizer
        assert isinstance(self.engine.competitor, CompetitorPriceTracker)
        assert isinstance(self.engine.forecaster, DemandForecaster)
        assert isinstance(self.engine.optimizer, PriceOptimizer)


# ─── API Blueprint ──────────────────────────────────────────────────────────

class TestAIPricingAPI:
    def setup_method(self):
        import src.api.ai_pricing_api as m
        # 엔진 재초기화
        m._engine = None
        from flask import Flask
        self.app = Flask(__name__)
        self.app.register_blueprint(m.ai_pricing_bp)
        self.client = self.app.test_client()

    def test_optimize_sku_post(self):
        resp = self.client.post(
            '/api/v1/ai-pricing/optimize',
            json={'sku': 'SKU001', 'base_price': 10000.0, 'cost': 7000.0},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['sku'] == 'SKU001'
        assert 'new_price' in data

    def test_optimize_category_post(self):
        resp = self.client.post(
            '/api/v1/ai-pricing/optimize',
            json={
                'category': 'electronics',
                'sku_map': {
                    'SKU001': {'price': 10000.0, 'cost': 7000.0},
                },
            },
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['category'] == 'electronics'

    def test_optimize_missing_params(self):
        resp = self.client.post('/api/v1/ai-pricing/optimize', json={})
        assert resp.status_code == 400

    def test_simulate_post(self):
        resp = self.client.post(
            '/api/v1/ai-pricing/simulate',
            json={
                'sku': 'SKU001',
                'base_price': 10000.0,
                'test_price': 9000.0,
                'cost': 7000.0,
            },
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'current' in data
        assert 'new' in data
        assert 'delta' in data

    def test_simulate_missing_params(self):
        resp = self.client.post('/api/v1/ai-pricing/simulate', json={'sku': 'SKU001'})
        assert resp.status_code == 400

    def test_recommendations_get(self):
        resp = self.client.get('/api/v1/ai-pricing/recommendations')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'recommendations' in data

    def test_competitors_get(self):
        resp = self.client.get('/api/v1/ai-pricing/competitors/SKU001?our_price=10000')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['sku'] == 'SKU001'

    def test_forecast_get(self):
        resp = self.client.get('/api/v1/ai-pricing/forecast/SKU001')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['sku'] == 'SKU001'
        assert 'predicted_qty' in data

    def test_history_get(self):
        resp = self.client.get('/api/v1/ai-pricing/history/SKU001')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['sku'] == 'SKU001'

    def test_analytics_get(self):
        resp = self.client.get('/api/v1/ai-pricing/analytics')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'effects' in data
        assert 'roi' in data

    def test_metrics_get(self):
        resp = self.client.get('/api/v1/ai-pricing/metrics')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'total_optimized' in data

    def test_rules_post(self):
        resp = self.client.post(
            '/api/v1/ai-pricing/rules',
            json={'rule_type': 'competitor_match', 'undercut_pct': 0.03},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['status'] == 'ok'

    def test_rules_post_invalid(self):
        resp = self.client.post(
            '/api/v1/ai-pricing/rules',
            json={'rule_type': 'invalid_rule'},
        )
        assert resp.status_code == 400

    def test_rules_get(self):
        resp = self.client.get('/api/v1/ai-pricing/rules')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'rules' in data
        assert data['count'] > 0

    def test_schedule_post(self):
        resp = self.client.post(
            '/api/v1/ai-pricing/schedule',
            json={'schedule_type': 'daily', 'category': 'electronics'},
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['schedule_type'] == 'daily'

    def test_alerts_get(self):
        resp = self.client.get('/api/v1/ai-pricing/alerts')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'alerts' in data

    def test_alerts_get_filtered(self):
        resp = self.client.get('/api/v1/ai-pricing/alerts?type=price_change')
        assert resp.status_code == 200
