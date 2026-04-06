"""tests/test_order_matching.py — Phase 112: 주문 매칭 + 이행 가능성 확인 테스트 (50개+)."""
from __future__ import annotations

import pytest


# ═══════════════════════════════════════════════════════════════════════════════
# 공통 픽스처
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def matcher():
    from src.order_matching.matcher import OrderSourceMatcher
    m = OrderSourceMatcher()
    # 소싱처 등록
    m.register_source('p1', {'source_id': 's1', 'price': 5000, 'stock': 100, 'active': True,
                              'shipping_days': 3, 'score': 80, 'priority_rank': 1, 'reliability': 0.9})
    m.register_source('p1', {'source_id': 's2', 'price': 5500, 'stock': 50, 'active': True,
                              'shipping_days': 5, 'score': 70, 'priority_rank': 2, 'reliability': 0.8})
    m.register_source('p2', {'source_id': 's3', 'price': 8000, 'stock': 0, 'active': True,
                              'shipping_days': 2, 'score': 60, 'priority_rank': 1, 'reliability': 0.7})
    m.register_source('p3', {'source_id': 's4', 'price': 3000, 'stock': 200, 'active': False,
                              'shipping_days': 4, 'score': 50, 'priority_rank': 1, 'reliability': 0.6})
    m.register_order('order1', [{'product_id': 'p1', 'quantity': 2}])
    m.register_order('order2', [
        {'product_id': 'p1', 'quantity': 1},
        {'product_id': 'p2', 'quantity': 1},
    ])
    return m


@pytest.fixture
def checker():
    from src.order_matching.fulfillment_checker import FulfillmentChecker
    c = FulfillmentChecker(min_margin_rate=0.05, max_price_change_rate=0.20)
    c.register_source('s1', {
        'product_id': 'p1', 'price': 5000, 'last_price': 5000,
        'stock': 100, 'active': True, 'shipping_available': True,
        'reliability': 0.9, 'shipping_days': 3,
    })
    c.register_source('s2', {
        'product_id': 'p1', 'price': 5000, 'last_price': 5000,
        'stock': 0, 'active': True, 'shipping_available': True,
        'reliability': 0.9, 'shipping_days': 3,
    })
    c.register_source('s3', {
        'product_id': 'p2', 'price': 9000, 'last_price': 5000,
        'stock': 50, 'active': True, 'shipping_available': True,
        'reliability': 0.9, 'shipping_days': 3,
    })
    c.register_source('s4', {
        'product_id': 'p3', 'price': 5000, 'last_price': 5000,
        'stock': 100, 'active': False, 'shipping_available': True,
        'reliability': 0.9, 'shipping_days': 3,
    })
    c.register_source('s5', {
        'product_id': 'p4', 'price': 5000, 'last_price': 5000,
        'stock': 100, 'active': True, 'shipping_available': False,
        'reliability': 0.9, 'shipping_days': 3,
    })
    c.register_source('s6', {
        'product_id': 'p5', 'price': 5000, 'last_price': 5000,
        'stock': 100, 'active': True, 'shipping_available': True,
        'reliability': 0.3, 'shipping_days': 3,
    })
    c.register_source('s7', {
        'product_id': 'p6', 'price': 9500, 'last_price': 9500,
        'stock': 100, 'active': True, 'shipping_available': True,
        'reliability': 0.9, 'shipping_days': 3,
    })
    c.register_order('order1', [{'product_id': 'p1', 'quantity': 1, 'selling_price': 8000,
                                  'source_id': 's1'}])
    return c


@pytest.fixture
def priority_manager():
    from src.order_matching.source_priority import SourcePriorityManager
    mgr = SourcePriorityManager()
    mgr.register_source_info('s1', {'price': 5000, 'reliability': 0.9,
                                     'shipping_days': 3, 'quality_score': 0.9})
    mgr.register_source_info('s2', {'price': 6000, 'reliability': 0.8,
                                     'shipping_days': 5, 'quality_score': 0.7})
    mgr.register_source_info('s3', {'price': 4500, 'reliability': 0.7,
                                     'shipping_days': 7, 'quality_score': 0.6})
    mgr.set_priority('p1', 's1', 1)
    mgr.set_priority('p1', 's2', 2)
    mgr.set_priority('p1', 's3', 3)
    return mgr


@pytest.fixture
def risk_assessor():
    from src.order_matching.risk_assessor import OrderRiskAssessor
    a = OrderRiskAssessor()
    a.register_source_context('s1', {
        'check_fail_rate': 0.05, 'price_volatility': 0.03,
        'delivery_uncertainty': 0.1, 'stock': 100,
        'is_foreign_currency': False, 'fx_volatility': 0.0,
    })
    a.register_source_context('s2', {
        'check_fail_rate': 0.6, 'price_volatility': 0.3,
        'delivery_uncertainty': 0.5, 'stock': 2,
        'is_foreign_currency': True, 'fx_volatility': 0.1,
    })
    a.register_product_context('p1', {'is_peak_season': False, 'demand_surge': 0.0})
    a.register_product_context('p2', {'is_peak_season': True, 'demand_surge': 0.8})
    return a


@pytest.fixture
def sla_tracker():
    from src.order_matching.sla_tracker import FulfillmentSLATracker
    return FulfillmentSLATracker()


# ═══════════════════════════════════════════════════════════════════════════════
# OrderSourceMatcher 테스트
# ═══════════════════════════════════════════════════════════════════════════════

class TestOrderSourceMatcher:

    def test_match_order_single_product(self, matcher):
        results = matcher.match_order('order1')
        assert len(results) == 1
        assert results[0].order_id == 'order1'
        assert results[0].product_id == 'p1'

    def test_match_order_multiple_products(self, matcher):
        results = matcher.match_order('order2')
        assert len(results) == 2
        product_ids = [r.product_id for r in results]
        assert 'p1' in product_ids
        assert 'p2' in product_ids

    def test_match_product_with_sources(self, matcher):
        result = matcher.match_product('p1', quantity=1)
        assert result.product_id == 'p1'
        assert result.best_source == 's1'
        assert result.fulfillment_status.value == 'fulfillable'

    def test_match_product_no_sources(self, matcher):
        result = matcher.match_product('p_unknown', quantity=1)
        from src.order_matching.matcher import FulfillmentStatus
        assert result.fulfillment_status == FulfillmentStatus.unfulfillable
        assert result.best_source is None
        assert result.metadata.get('reason') == 'no_sources_registered'

    def test_match_product_out_of_stock(self, matcher):
        result = matcher.match_product('p2', quantity=1)
        from src.order_matching.matcher import FulfillmentStatus
        assert result.fulfillment_status == FulfillmentStatus.unfulfillable

    def test_match_product_inactive_source(self, matcher):
        result = matcher.match_product('p3', quantity=1)
        from src.order_matching.matcher import FulfillmentStatus
        assert result.fulfillment_status == FulfillmentStatus.unfulfillable

    def test_match_product_multiple_sources_best_selected(self, matcher):
        result = matcher.match_product('p1', quantity=1)
        # s1 has priority_rank=1 and higher score
        assert result.best_source == 's1'
        assert 's1' in result.matched_sources
        assert 's2' in result.matched_sources

    def test_match_bulk_orders(self, matcher):
        results = matcher.match_bulk_orders(['order1', 'order2'])
        assert 'order1' in results
        assert 'order2' in results
        assert len(results['order1']) == 1
        assert len(results['order2']) == 2

    def test_get_match_result(self, matcher):
        matcher.match_order('order1')
        results = matcher.get_match_result('order1')
        assert results is not None
        assert len(results) == 1

    def test_get_match_result_not_found(self, matcher):
        result = matcher.get_match_result('nonexistent')
        assert result is None

    def test_get_match_history(self, matcher):
        matcher.match_order('order1')
        matcher.match_order('order2')
        history = matcher.get_match_history()
        assert len(history) >= 2

    def test_get_match_history_by_order_id(self, matcher):
        matcher.match_order('order1')
        history = matcher.get_match_history(order_id='order1')
        assert all(r.order_id == 'order1' for r in history)

    def test_get_match_history_by_product_id(self, matcher):
        matcher.match_order('order1')
        history = matcher.get_match_history(product_id='p1')
        assert all(r.product_id == 'p1' for r in history)

    def test_get_match_history_limit(self, matcher):
        for i in range(10):
            matcher.match_product(f'p_{i}', quantity=1)
        history = matcher.get_match_history(limit=5)
        assert len(history) <= 5

    def test_get_match_stats_empty(self):
        from src.order_matching.matcher import OrderSourceMatcher
        m = OrderSourceMatcher()
        stats = m.get_match_stats()
        assert stats['total'] == 0
        assert stats['success_rate'] == 0.0

    def test_get_match_stats_with_data(self, matcher):
        matcher.match_order('order1')
        matcher.match_order('order2')
        stats = matcher.get_match_stats()
        assert stats['total'] >= 1
        assert 'fulfillable' in stats
        assert 'unfulfillable' in stats
        assert 'success_rate' in stats

    def test_match_result_has_estimated_cost(self, matcher):
        result = matcher.match_product('p1', quantity=2)
        assert result.estimated_cost > 0

    def test_match_result_has_delivery_days(self, matcher):
        result = matcher.match_product('p1', quantity=1)
        assert result.estimated_delivery_days > 0

    def test_match_result_has_risk_score(self, matcher):
        result = matcher.match_product('p1', quantity=1)
        assert 0 <= result.risk_score <= 100

    def test_fulfillment_status_enum_values(self):
        from src.order_matching.matcher import FulfillmentStatus
        assert FulfillmentStatus.fulfillable.value == 'fulfillable'
        assert FulfillmentStatus.unfulfillable.value == 'unfulfillable'
        assert FulfillmentStatus.risky.value == 'risky'
        assert FulfillmentStatus.partially_fulfillable.value == 'partially_fulfillable'
        assert FulfillmentStatus.pending_check.value == 'pending_check'


# ═══════════════════════════════════════════════════════════════════════════════
# FulfillmentChecker 테스트
# ═══════════════════════════════════════════════════════════════════════════════

class TestFulfillmentChecker:

    def test_check_fulfillment_ok(self, checker):
        results = checker.check_fulfillment('order1', source_id='s1')
        assert len(results) == 1
        assert results[0].is_available is True
        assert results[0].issues == []

    def test_check_product_out_of_stock(self, checker):
        result = checker.check_product_fulfillment('p1', quantity=1, source_id='s2')
        assert result.is_available is False
        assert 'out_of_stock' in result.issues

    def test_check_product_price_exceeded(self, checker):
        # s3: price 9000, last_price 5000 → 80% 변동 > 20% 임계값
        result = checker.check_product_fulfillment('p2', quantity=1, source_id='s3')
        assert 'price_exceeded' in result.issues

    def test_check_product_source_inactive(self, checker):
        result = checker.check_product_fulfillment('p3', quantity=1, source_id='s4')
        assert 'source_inactive' in result.issues

    def test_check_product_shipping_unavailable(self, checker):
        result = checker.check_product_fulfillment('p4', quantity=1, source_id='s5')
        assert 'shipping_unavailable' in result.issues

    def test_check_product_source_unreliable(self, checker):
        result = checker.check_product_fulfillment('p5', quantity=1, source_id='s6')
        assert 'source_unreliable' in result.issues

    def test_check_product_margin_below_threshold(self, checker):
        # s7: price 9500, selling_price 10000 → margin_rate = 500/10000 = 5% == threshold
        # with strict < threshold check: 5% is not below 5%
        # Let's use s1 with very low selling_price
        result = checker.check_product_fulfillment(
            'p1', quantity=1, source_id='s1', selling_price=5100
        )
        # margin = 100, margin_rate = 100/5100 ≈ 1.96% < 5%
        assert 'margin_below_threshold' in result.issues

    def test_handle_unfulfillable_with_alternative(self, checker):
        # Register an alternative source for p_alt
        checker.register_source('s_alt', {
            'product_id': 'p_alt', 'price': 5000, 'last_price': 5000,
            'stock': 50, 'active': True, 'shipping_available': True, 'reliability': 0.9,
        })
        action = checker.handle_unfulfillable('order_x', 'p_alt', 'out_of_stock')
        assert action['alternative_found'] is True
        assert action['action_taken'] == 'switched_to_alternative'

    def test_handle_unfulfillable_no_alternative(self, checker):
        action = checker.handle_unfulfillable('order_x', 'p_none', 'out_of_stock')
        assert action['alternative_found'] is False
        assert action['action_taken'] == 'notified_and_paused'

    def test_handle_unfulfillable_creates_notification(self, checker):
        checker.handle_unfulfillable('order_x', 'p_none', 'out_of_stock')
        notifications = checker.get_notifications()
        assert len(notifications) >= 1
        assert notifications[-1]['type'] == 'fulfillment_failed'

    def test_check_result_dataclass_fields(self, checker):
        result = checker.check_product_fulfillment('p1', quantity=1, source_id='s1')
        assert hasattr(result, 'check_id')
        assert hasattr(result, 'stock_available')
        assert hasattr(result, 'price_valid')
        assert hasattr(result, 'shipping_possible')
        assert hasattr(result, 'estimated_total_cost')
        assert hasattr(result, 'estimated_margin')


# ═══════════════════════════════════════════════════════════════════════════════
# SourcePriorityManager 테스트
# ═══════════════════════════════════════════════════════════════════════════════

class TestSourcePriorityManager:

    def test_set_and_get_priority(self, priority_manager):
        priorities = priority_manager.get_priorities('p1')
        assert len(priorities) == 3
        assert priorities[0].priority_rank == 1
        assert priorities[0].source_id == 's1'

    def test_priority_ranks_ordered(self, priority_manager):
        priorities = priority_manager.get_priorities('p1')
        ranks = [p.priority_rank for p in priorities]
        assert ranks == sorted(ranks)

    def test_get_primary_source(self, priority_manager):
        primary = priority_manager.get_primary_source('p1')
        assert primary is not None
        assert primary.is_primary is True
        assert primary.priority_rank == 1

    def test_get_backup_sources(self, priority_manager):
        backups = priority_manager.get_backup_sources('p1')
        assert len(backups) == 2
        assert all(b.is_backup for b in backups)

    def test_auto_rank_sources(self, priority_manager):
        priorities = priority_manager.auto_rank_sources('p1')
        assert len(priorities) == 3
        # First rank should have highest weighted_total
        assert priorities[0].score >= priorities[1].score

    def test_auto_rank_scoring_factors(self, priority_manager):
        priorities = priority_manager.auto_rank_sources('p1')
        for p in priorities:
            factors = p.scoring_factors
            assert 0 <= factors.price_score <= 100
            assert 0 <= factors.reliability_score <= 100
            assert 0 <= factors.shipping_speed_score <= 100
            assert 0 <= factors.quality_score <= 100
            assert factors.weighted_total > 0

    def test_promote_backup(self, priority_manager):
        promoted = priority_manager.promote_backup('p1', 's2')
        assert promoted is not None
        assert promoted.is_primary is True
        assert promoted.priority_rank == 1
        # Old primary should be demoted
        old_primary = next(
            (p for p in priority_manager.get_priorities('p1') if p.source_id == 's1'), None
        )
        assert old_primary is not None
        assert old_primary.is_primary is False

    def test_demote_source(self, priority_manager):
        demoted = priority_manager.demote_source('p1', 's1', 'price_spike')
        assert demoted is not None
        assert demoted.is_backup is True
        history = priority_manager.get_demotion_history()
        assert len(history) >= 1
        assert history[-1]['reason'] == 'price_spike'

    def test_promote_nonexistent_source(self, priority_manager):
        result = priority_manager.promote_backup('p1', 's_none')
        assert result is None

    def test_set_priority_creates_primary(self):
        from src.order_matching.source_priority import SourcePriorityManager
        mgr = SourcePriorityManager()
        p = mgr.set_priority('pX', 'sX', 1)
        assert p.is_primary is True
        assert p.is_backup is False

    def test_set_priority_creates_backup(self):
        from src.order_matching.source_priority import SourcePriorityManager
        mgr = SourcePriorityManager()
        p = mgr.set_priority('pX', 'sX', 2)
        assert p.is_primary is False
        assert p.is_backup is True


# ═══════════════════════════════════════════════════════════════════════════════
# OrderRiskAssessor 테스트
# ═══════════════════════════════════════════════════════════════════════════════

class TestOrderRiskAssessor:

    def test_assess_product_risk_low(self, risk_assessor):
        assessment = risk_assessor.assess_product_risk('p1', source_id='s1')
        from src.order_matching.risk_assessor import RiskLevel
        assert assessment.risk_level in (RiskLevel.low, RiskLevel.medium)
        assert 0 <= assessment.overall_risk_score <= 100

    def test_assess_product_risk_high(self, risk_assessor):
        assessment = risk_assessor.assess_product_risk('p2', source_id='s2')
        from src.order_matching.risk_assessor import RiskLevel
        assert assessment.overall_risk_score > 30

    def test_assess_order_risk(self, risk_assessor):
        assessment = risk_assessor.assess_order_risk('order1')
        assert assessment is not None
        assert hasattr(assessment, 'overall_risk_score')

    def test_risk_factors_count(self, risk_assessor):
        assessment = risk_assessor.assess_product_risk('p1', source_id='s1')
        assert len(assessment.risk_factors) == 6

    def test_risk_factor_types(self, risk_assessor):
        assessment = risk_assessor.assess_product_risk('p1', source_id='s1')
        factor_types = [f.factor_type for f in assessment.risk_factors]
        assert 'source_stability' in factor_types
        assert 'price_volatility' in factor_types
        assert 'stock_risk' in factor_types
        assert 'shipping_risk' in factor_types
        assert 'fx_risk' in factor_types
        assert 'season_demand_risk' in factor_types

    def test_risk_level_enum(self):
        from src.order_matching.risk_assessor import RiskLevel
        assert RiskLevel.low.value == 'low'
        assert RiskLevel.medium.value == 'medium'
        assert RiskLevel.high.value == 'high'
        assert RiskLevel.critical.value == 'critical'

    def test_get_high_risk_orders(self, risk_assessor):
        # Register high-risk context
        risk_assessor.register_source_context('s_high', {
            'check_fail_rate': 0.9, 'price_volatility': 0.5,
            'delivery_uncertainty': 0.8, 'stock': 0,
            'is_foreign_currency': True, 'fx_volatility': 0.3,
        })
        risk_assessor.assess_product_risk('p_high', source_id='s_high', order_id='order_high')
        high_risk = risk_assessor.get_high_risk_orders()
        assert isinstance(high_risk, list)

    def test_get_risk_summary(self, risk_assessor):
        risk_assessor.assess_product_risk('p1', source_id='s1')
        summary = risk_assessor.get_risk_summary()
        assert 'total' in summary
        assert 'low' in summary
        assert 'medium' in summary
        assert 'high' in summary
        assert 'critical' in summary
        assert 'avg_score' in summary

    def test_risk_summary_empty(self):
        from src.order_matching.risk_assessor import OrderRiskAssessor
        a = OrderRiskAssessor()
        summary = a.get_risk_summary()
        assert summary['total'] == 0

    def test_recommendations_populated(self, risk_assessor):
        assessment = risk_assessor.assess_product_risk('p2', source_id='s2')
        assert isinstance(assessment.recommendations, list)
        assert len(assessment.recommendations) > 0

    def test_peak_season_increases_risk(self, risk_assessor):
        # p2 has is_peak_season=True
        a_peak = risk_assessor.assess_product_risk('p2', source_id='s1')
        # p1 has is_peak_season=False
        a_normal = risk_assessor.assess_product_risk('p1', source_id='s1')
        # Peak season should contribute to higher score
        peak_season_factor = next(
            f for f in a_peak.risk_factors if f.factor_type == 'season_demand_risk'
        )
        normal_factor = next(
            f for f in a_normal.risk_factors if f.factor_type == 'season_demand_risk'
        )
        assert peak_season_factor.score > normal_factor.score


# ═══════════════════════════════════════════════════════════════════════════════
# FulfillmentSLATracker 테스트
# ═══════════════════════════════════════════════════════════════════════════════

class TestFulfillmentSLATracker:

    def test_start_tracking(self, sla_tracker):
        status = sla_tracker.start_tracking('order1')
        assert status.order_id == 'order1'
        from src.order_matching.sla_tracker import FulfillmentStage
        assert status.stage == FulfillmentStage.order_received
        assert status.is_overdue is False

    def test_update_stage(self, sla_tracker):
        from src.order_matching.sla_tracker import FulfillmentStage
        sla_tracker.start_tracking('order1')
        status = sla_tracker.update_stage('order1', FulfillmentStage.source_matched)
        assert status is not None
        assert status.stage == FulfillmentStage.source_matched

    def test_update_stage_unknown_order(self, sla_tracker):
        from src.order_matching.sla_tracker import FulfillmentStage
        result = sla_tracker.update_stage('nonexistent', FulfillmentStage.shipped)
        assert result is None

    def test_get_sla_status(self, sla_tracker):
        sla_tracker.start_tracking('order1')
        status = sla_tracker.get_sla_status('order1')
        assert status is not None
        assert status.order_id == 'order1'

    def test_get_sla_status_not_found(self, sla_tracker):
        status = sla_tracker.get_sla_status('nonexistent')
        assert status is None

    def test_sla_not_overdue_initially(self, sla_tracker):
        status = sla_tracker.start_tracking('order1')
        assert status.is_overdue is False
        assert status.remaining_hours > 0

    def test_get_overdue_orders_empty(self, sla_tracker):
        sla_tracker.start_tracking('order1')
        overdue = sla_tracker.get_overdue_orders()
        # Fresh tracking should not be overdue
        assert isinstance(overdue, list)

    def test_get_sla_performance(self, sla_tracker):
        sla_tracker.start_tracking('order1')
        sla_tracker.start_tracking('order2')
        perf = sla_tracker.get_sla_performance()
        assert perf['total'] == 2
        assert 'achievement_rate' in perf
        assert 'on_time' in perf

    def test_get_sla_performance_empty(self, sla_tracker):
        perf = sla_tracker.get_sla_performance()
        assert perf['total'] == 0
        assert perf['achievement_rate'] == 0.0

    def test_stage_duration_stats_empty(self, sla_tracker):
        stats = sla_tracker.get_stage_duration_stats()
        assert isinstance(stats, dict)

    def test_stage_duration_stats_after_update(self, sla_tracker):
        from src.order_matching.sla_tracker import FulfillmentStage
        sla_tracker.start_tracking('order1')
        sla_tracker.update_stage('order1', FulfillmentStage.source_matched)
        stats = sla_tracker.get_stage_duration_stats()
        assert 'order_received' in stats

    def test_fulfillment_stage_enum(self):
        from src.order_matching.sla_tracker import FulfillmentStage
        assert FulfillmentStage.order_received.value == 'order_received'
        assert FulfillmentStage.delivered.value == 'delivered'

    def test_sla_config_defaults(self):
        from src.order_matching.sla_tracker import SLAConfig
        config = SLAConfig()
        assert config.order_to_purchase_hours == 4
        assert config.purchase_to_warehouse_hours == 72
        assert config.warehouse_to_ship_hours == 24

    def test_elapsed_hours_positive(self, sla_tracker):
        sla_tracker.start_tracking('order1')
        status = sla_tracker.get_sla_status('order1')
        assert status.elapsed_hours >= 0

    def test_multiple_stage_transitions(self, sla_tracker):
        from src.order_matching.sla_tracker import FulfillmentStage
        sla_tracker.start_tracking('order1')
        for stage in [
            FulfillmentStage.source_matched,
            FulfillmentStage.purchase_initiated,
            FulfillmentStage.purchase_confirmed,
        ]:
            status = sla_tracker.update_stage('order1', stage)
            assert status.stage == stage


# ═══════════════════════════════════════════════════════════════════════════════
# OrderMatchingDashboard 테스트
# ═══════════════════════════════════════════════════════════════════════════════

class TestOrderMatchingDashboard:

    def test_get_dashboard_data(self, matcher, checker, risk_assessor, sla_tracker):
        from src.order_matching.order_matching_dashboard import OrderMatchingDashboard
        dashboard = OrderMatchingDashboard(
            matcher=matcher,
            fulfillment_checker=checker,
            risk_assessor=risk_assessor,
            sla_tracker=sla_tracker,
        )
        data = dashboard.get_dashboard_data()
        assert 'timestamp' in data
        assert 'matching_summary' in data
        assert 'sla_summary' in data
        assert 'risk_distribution' in data
        assert 'unfulfillable_reasons' in data
        assert 'recent_match_feed' in data

    def test_get_daily_stats(self, matcher):
        from src.order_matching.order_matching_dashboard import OrderMatchingDashboard
        dashboard = OrderMatchingDashboard(matcher=matcher)
        stats = dashboard.get_daily_stats()
        assert 'date' in stats
        assert 'match_stats' in stats

    def test_get_unfulfillable_summary(self, checker):
        from src.order_matching.order_matching_dashboard import OrderMatchingDashboard
        checker.handle_unfulfillable('order_x', 'p_none', 'out_of_stock')
        dashboard = OrderMatchingDashboard(fulfillment_checker=checker)
        summary = dashboard.get_unfulfillable_summary()
        assert summary['total'] >= 1
        assert 'by_reason' in summary

    def test_dashboard_no_components(self):
        from src.order_matching.order_matching_dashboard import OrderMatchingDashboard
        dashboard = OrderMatchingDashboard()
        data = dashboard.get_dashboard_data()
        assert 'timestamp' in data


# ═══════════════════════════════════════════════════════════════════════════════
# API 테스트
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def app_client():
    import importlib
    import sys
    # Reset module-level singletons
    for mod_name in list(sys.modules.keys()):
        if 'order_matching_api' in mod_name:
            del sys.modules[mod_name]
    from flask import Flask
    from src.api.order_matching_api import order_matching_bp
    app = Flask(__name__)
    app.register_blueprint(order_matching_bp)
    app.config['TESTING'] = True
    return app.test_client()


class TestOrderMatchingAPI:

    def test_match_order_endpoint(self, app_client):
        resp = app_client.post('/api/v1/order-matching/match/order1',
                               json={'items': [{'product_id': 'p1', 'quantity': 1}]})
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)

    def test_match_product_endpoint(self, app_client):
        resp = app_client.post('/api/v1/order-matching/match/product',
                               json={'product_id': 'p1', 'quantity': 1})
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'product_id' in data

    def test_match_product_missing_id(self, app_client):
        resp = app_client.post('/api/v1/order-matching/match/product', json={})
        assert resp.status_code == 400

    def test_match_bulk_endpoint(self, app_client):
        resp = app_client.post('/api/v1/order-matching/match/bulk',
                               json={'order_ids': ['o1', 'o2']})
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'o1' in data
        assert 'o2' in data

    def test_match_bulk_missing_ids(self, app_client):
        resp = app_client.post('/api/v1/order-matching/match/bulk', json={})
        assert resp.status_code == 400

    def test_get_match_result_not_found(self, app_client):
        resp = app_client.get('/api/v1/order-matching/match/nonexistent')
        assert resp.status_code == 404

    def test_get_match_history_endpoint(self, app_client):
        resp = app_client.get('/api/v1/order-matching/match/history')
        assert resp.status_code == 200

    def test_get_match_stats_endpoint(self, app_client):
        resp = app_client.get('/api/v1/order-matching/match/stats')
        assert resp.status_code == 200

    def test_check_fulfillment_endpoint(self, app_client):
        resp = app_client.post('/api/v1/order-matching/fulfillment/check/order1',
                               json={})
        assert resp.status_code == 200

    def test_check_product_fulfillment_endpoint(self, app_client):
        resp = app_client.post('/api/v1/order-matching/fulfillment/check/product',
                               json={'product_id': 'p1', 'quantity': 1})
        assert resp.status_code == 200

    def test_check_product_fulfillment_missing(self, app_client):
        resp = app_client.post('/api/v1/order-matching/fulfillment/check/product', json={})
        assert resp.status_code == 400

    def test_handle_unfulfillable_endpoint(self, app_client):
        resp = app_client.post('/api/v1/order-matching/fulfillment/handle-unfulfillable',
                               json={'order_id': 'o1', 'product_id': 'p1',
                                     'reason': 'out_of_stock'})
        assert resp.status_code == 200

    def test_handle_unfulfillable_missing_fields(self, app_client):
        resp = app_client.post('/api/v1/order-matching/fulfillment/handle-unfulfillable',
                               json={})
        assert resp.status_code == 400

    def test_get_priorities_endpoint(self, app_client):
        resp = app_client.get('/api/v1/order-matching/priorities/p1')
        assert resp.status_code == 200

    def test_set_priority_endpoint(self, app_client):
        resp = app_client.post('/api/v1/order-matching/priorities/p1',
                               json={'source_id': 's1', 'priority_rank': 1})
        assert resp.status_code == 200

    def test_set_priority_missing_source(self, app_client):
        resp = app_client.post('/api/v1/order-matching/priorities/p1', json={})
        assert resp.status_code == 400

    def test_auto_rank_endpoint(self, app_client):
        resp = app_client.post('/api/v1/order-matching/priorities/p1/auto-rank')
        assert resp.status_code == 200

    def test_promote_source_not_found(self, app_client):
        resp = app_client.post('/api/v1/order-matching/priorities/p1/promote/nonexistent')
        assert resp.status_code == 404

    def test_demote_source_not_found(self, app_client):
        resp = app_client.post('/api/v1/order-matching/priorities/p1/demote/nonexistent',
                               json={'reason': 'test'})
        assert resp.status_code == 404

    def test_get_order_risk_endpoint(self, app_client):
        resp = app_client.get('/api/v1/order-matching/risk/order1')
        assert resp.status_code == 200

    def test_get_product_risk_endpoint(self, app_client):
        resp = app_client.get('/api/v1/order-matching/risk/product/p1')
        assert resp.status_code == 200

    def test_get_high_risk_orders_endpoint(self, app_client):
        resp = app_client.get('/api/v1/order-matching/risk/high-risk')
        assert resp.status_code == 200

    def test_get_risk_summary_endpoint(self, app_client):
        resp = app_client.get('/api/v1/order-matching/risk/summary')
        assert resp.status_code == 200

    def test_sla_start_endpoint(self, app_client):
        resp = app_client.post('/api/v1/order-matching/sla/start/order1')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['order_id'] == 'order1'

    def test_sla_update_endpoint(self, app_client):
        app_client.post('/api/v1/order-matching/sla/start/order1')
        resp = app_client.post('/api/v1/order-matching/sla/update/order1',
                               json={'stage': 'source_matched'})
        assert resp.status_code == 200

    def test_sla_update_invalid_stage(self, app_client):
        app_client.post('/api/v1/order-matching/sla/start/order1')
        resp = app_client.post('/api/v1/order-matching/sla/update/order1',
                               json={'stage': 'invalid_stage'})
        assert resp.status_code == 400

    def test_sla_status_endpoint(self, app_client):
        app_client.post('/api/v1/order-matching/sla/start/order_sla')
        resp = app_client.get('/api/v1/order-matching/sla/order_sla')
        assert resp.status_code == 200

    def test_sla_status_not_found(self, app_client):
        resp = app_client.get('/api/v1/order-matching/sla/nonexistent')
        assert resp.status_code == 404

    def test_sla_overdue_endpoint(self, app_client):
        resp = app_client.get('/api/v1/order-matching/sla/overdue')
        assert resp.status_code == 200

    def test_sla_performance_endpoint(self, app_client):
        resp = app_client.get('/api/v1/order-matching/sla/performance')
        assert resp.status_code == 200

    def test_sla_stage_stats_endpoint(self, app_client):
        resp = app_client.get('/api/v1/order-matching/sla/stage-stats')
        assert resp.status_code == 200

    def test_dashboard_endpoint(self, app_client):
        resp = app_client.get('/api/v1/order-matching/dashboard')
        assert resp.status_code == 200

    def test_daily_stats_endpoint(self, app_client):
        resp = app_client.get('/api/v1/order-matching/dashboard/daily')
        assert resp.status_code == 200

    def test_unfulfillable_summary_endpoint(self, app_client):
        resp = app_client.get('/api/v1/order-matching/dashboard/unfulfillable')
        assert resp.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════════
# 봇 커맨드 테스트
# ═══════════════════════════════════════════════════════════════════════════════

class TestOrderMatchingBotCommands:

    def test_cmd_match_order(self):
        from src.bot.order_matching_commands import cmd_match_order
        result = cmd_match_order('order1')
        assert isinstance(result, str)

    def test_cmd_match_order_empty(self):
        from src.bot.order_matching_commands import cmd_match_order
        result = cmd_match_order('')
        assert isinstance(result, str)
        assert '사용법' in result

    def test_cmd_match_status(self):
        from src.bot.order_matching_commands import cmd_match_status
        result = cmd_match_status('order1')
        assert isinstance(result, str)

    def test_cmd_match_status_empty(self):
        from src.bot.order_matching_commands import cmd_match_status
        result = cmd_match_status('')
        assert isinstance(result, str)

    def test_cmd_fulfillment_check(self):
        from src.bot.order_matching_commands import cmd_fulfillment_check
        result = cmd_fulfillment_check('order1')
        assert isinstance(result, str)

    def test_cmd_fulfillment_check_empty(self):
        from src.bot.order_matching_commands import cmd_fulfillment_check
        result = cmd_fulfillment_check('')
        assert isinstance(result, str)

    def test_cmd_fulfillment_risk_with_id(self):
        from src.bot.order_matching_commands import cmd_fulfillment_risk
        result = cmd_fulfillment_risk('order1')
        assert isinstance(result, str)

    def test_cmd_fulfillment_risk_no_id(self):
        from src.bot.order_matching_commands import cmd_fulfillment_risk
        result = cmd_fulfillment_risk()
        assert isinstance(result, str)

    def test_cmd_sla_status_with_id(self):
        from src.bot.order_matching_commands import cmd_sla_status
        result = cmd_sla_status('order1')
        assert isinstance(result, str)

    def test_cmd_sla_status_no_id(self):
        from src.bot.order_matching_commands import cmd_sla_status
        result = cmd_sla_status()
        assert isinstance(result, str)

    def test_cmd_sla_overdue(self):
        from src.bot.order_matching_commands import cmd_sla_overdue
        result = cmd_sla_overdue()
        assert isinstance(result, str)

    def test_cmd_source_priority(self):
        from src.bot.order_matching_commands import cmd_source_priority
        result = cmd_source_priority('p1')
        assert isinstance(result, str)

    def test_cmd_source_priority_empty(self):
        from src.bot.order_matching_commands import cmd_source_priority
        result = cmd_source_priority('')
        assert isinstance(result, str)

    def test_cmd_matching_dashboard(self):
        from src.bot.order_matching_commands import cmd_matching_dashboard
        result = cmd_matching_dashboard()
        assert isinstance(result, str)

    def test_cmd_unfulfillable(self):
        from src.bot.order_matching_commands import cmd_unfulfillable
        result = cmd_unfulfillable()
        assert isinstance(result, str)

    def test_cmd_high_risk_orders(self):
        from src.bot.order_matching_commands import cmd_high_risk_orders
        result = cmd_high_risk_orders()
        assert isinstance(result, str)

    def test_commands_accessible_from_main_commands(self):
        """Phase 112 commands are accessible from main commands.py."""
        from src.bot import commands
        assert hasattr(commands, 'cmd_match_order')
        assert hasattr(commands, 'cmd_match_status')
        assert hasattr(commands, 'cmd_fulfillment_check')
        assert hasattr(commands, 'cmd_fulfillment_risk')
        assert hasattr(commands, 'cmd_sla_status')
        assert hasattr(commands, 'cmd_sla_overdue')
        assert hasattr(commands, 'cmd_source_priority')
        assert hasattr(commands, 'cmd_matching_dashboard')
        assert hasattr(commands, 'cmd_unfulfillable')
        assert hasattr(commands, 'cmd_high_risk_orders')
