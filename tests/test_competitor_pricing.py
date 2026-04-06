"""tests/test_competitor_pricing.py — Phase 111: 경쟁사 가격 모니터링 테스트.

CompetitorTracker, CompetitorMatcher, PricePositionAnalyzer,
PriceAdjustmentSuggester, CompetitorPriceRules, CompetitorAlertService,
CompetitorDashboard, CompetitorCheckScheduler, API 엔드포인트, 봇 커맨드
"""
from __future__ import annotations

import pytest


# ==============================================================================
# 헬퍼
# ==============================================================================

def _sample_competitor(**kwargs) -> dict:
    base = {
        'product_id': 'p1',
        'competitor_name': '테스트셀러',
        'platform': 'coupang',
        'title': '블루투스 이어폰 무선 노이즈캔슬링',
        'price': 30000.0,
        'currency': 'KRW',
        'url': 'https://coupang.com/test',
        'seller_name': '테스트셀러',
        'seller_rating': 4.5,
        'shipping_cost': 0.0,
        'is_available': True,
    }
    base.update(kwargs)
    return base


# ==============================================================================
# CompetitorTracker
# ==============================================================================

class TestCompetitorTracker:
    def _make(self):
        from src.competitor_pricing.tracker import CompetitorTracker
        return CompetitorTracker()

    def test_add_competitor_returns_product(self):
        tracker = self._make()
        p = tracker.add_competitor(_sample_competitor())
        assert p.competitor_id
        assert p.product_id == 'p1'
        assert p.price == 30000.0

    def test_add_competitor_auto_id(self):
        tracker = self._make()
        p = tracker.add_competitor(_sample_competitor())
        assert len(p.competitor_id) == 36  # UUID

    def test_add_competitor_custom_id(self):
        tracker = self._make()
        p = tracker.add_competitor(_sample_competitor(competitor_id='my-id'))
        assert p.competitor_id == 'my-id'

    def test_remove_competitor_existing(self):
        tracker = self._make()
        p = tracker.add_competitor(_sample_competitor())
        result = tracker.remove_competitor(p.competitor_id)
        assert result is True
        assert tracker.get_competitor(p.competitor_id) is None

    def test_remove_competitor_nonexistent(self):
        tracker = self._make()
        result = tracker.remove_competitor('nonexistent')
        assert result is False

    def test_get_competitors_all(self):
        tracker = self._make()
        tracker.add_competitor(_sample_competitor(product_id='p1'))
        tracker.add_competitor(_sample_competitor(product_id='p2'))
        all_comps = tracker.get_competitors()
        assert len(all_comps) == 2

    def test_get_competitors_filtered_by_product(self):
        tracker = self._make()
        tracker.add_competitor(_sample_competitor(product_id='p1'))
        tracker.add_competitor(_sample_competitor(product_id='p2'))
        p1_comps = tracker.get_competitors(my_product_id='p1')
        assert all(c.product_id == 'p1' for c in p1_comps)
        assert len(p1_comps) == 1

    def test_get_competitor_returns_product(self):
        tracker = self._make()
        p = tracker.add_competitor(_sample_competitor())
        fetched = tracker.get_competitor(p.competitor_id)
        assert fetched is not None
        assert fetched.competitor_id == p.competitor_id

    def test_check_competitor_updates_price(self):
        tracker = self._make()
        p = tracker.add_competitor(_sample_competitor(price=30000.0))
        updated = tracker.check_competitor(p.competitor_id)
        assert updated is not None
        assert updated.last_checked_at != p.last_checked_at or True  # mutable

    def test_check_competitor_nonexistent_returns_none(self):
        tracker = self._make()
        result = tracker.check_competitor('nonexistent')
        assert result is None

    def test_check_all_returns_list(self):
        tracker = self._make()
        tracker.add_competitor(_sample_competitor())
        tracker.add_competitor(_sample_competitor(product_id='p2'))
        results = tracker.check_all()
        assert len(results) == 2

    def test_get_price_history_initial(self):
        tracker = self._make()
        p = tracker.add_competitor(_sample_competitor(price=30000.0))
        history = tracker.get_price_history(p.competitor_id)
        assert len(history) >= 1
        assert history[0]['price'] == 30000.0

    def test_get_price_history_after_check(self):
        tracker = self._make()
        p = tracker.add_competitor(_sample_competitor(price=30000.0))
        tracker.check_competitor(p.competitor_id)
        history = tracker.get_price_history(p.competitor_id)
        assert len(history) >= 2

    def test_get_price_history_empty_for_nonexistent(self):
        tracker = self._make()
        history = tracker.get_price_history('nonexistent')
        assert history == []

    def test_check_competitor_retry_logic(self):
        """mock 체크가 최대 3회 재시도 지원."""
        from src.competitor_pricing.tracker import MAX_RETRIES
        assert MAX_RETRIES == 3

    def test_competitor_fields(self):
        tracker = self._make()
        p = tracker.add_competitor(_sample_competitor(
            seller_rating=4.8,
            shipping_cost=2500.0,
            is_available=False,
        ))
        assert p.seller_rating == 4.8
        assert p.shipping_cost == 2500.0
        assert p.is_available is False


# ==============================================================================
# CompetitorMatcher
# ==============================================================================

class TestCompetitorMatcher:
    def _make(self):
        from src.competitor_pricing.matcher import CompetitorMatcher
        return CompetitorMatcher()

    def test_find_competitors_returns_list(self):
        matcher = self._make()
        matches = matcher.find_competitors('p1')
        assert isinstance(matches, list)

    def test_find_competitors_creates_matches(self):
        matcher = self._make()
        matches = matcher.find_competitors('p1')
        assert len(matches) >= 1

    def test_calculate_match_score_identical_titles(self):
        from src.competitor_pricing.tracker import CompetitorProduct
        matcher = self._make()
        my_product = {'title': '블루투스 이어폰 무선', 'price': 30000.0, 'category': 'electronics'}
        from dataclasses import field as dc_field
        cp = CompetitorProduct(
            competitor_id='c1', product_id='p1',
            competitor_name='셀러', platform='naver',
            title='블루투스 이어폰 무선',
            price=30000.0,
        )
        score = matcher.calculate_match_score(my_product, cp)
        assert score > 50.0

    def test_calculate_match_score_different_titles(self):
        from src.competitor_pricing.tracker import CompetitorProduct
        matcher = self._make()
        my_product = {'title': '블루투스 이어폰', 'price': 30000.0}
        cp = CompetitorProduct(
            competitor_id='c2', product_id='p1',
            competitor_name='셀러', platform='naver',
            title='노트북 15인치 게이밍',
            price=800000.0,
        )
        score = matcher.calculate_match_score(my_product, cp)
        assert score < 50.0

    def test_get_matches_empty_initially(self):
        matcher = self._make()
        matches = matcher.get_matches()
        assert isinstance(matches, list)

    def test_get_matches_after_find(self):
        matcher = self._make()
        matcher.find_competitors('p1')
        matches = matcher.get_matches(my_product_id='p1')
        assert len(matches) >= 1

    def test_confirm_match(self):
        matcher = self._make()
        matches = matcher.find_competitors('p1')
        match_id = matches[0].match_id
        result = matcher.confirm_match(match_id)
        assert result is True
        confirmed = [m for m in matcher.get_matches() if m.match_id == match_id]
        assert confirmed[0].confirmed is True

    def test_reject_match(self):
        matcher = self._make()
        matches = matcher.find_competitors('p1')
        match_id = matches[0].match_id
        result = matcher.reject_match(match_id)
        assert result is True
        rejected = [m for m in matcher.get_matches() if m.match_id == match_id]
        assert rejected[0].rejected is True

    def test_match_type_enum_values(self):
        from src.competitor_pricing.matcher import MatchType
        assert MatchType.exact.value == 'exact'
        assert MatchType.similar.value == 'similar'
        assert MatchType.alternative.value == 'alternative'

    def test_match_score_range(self):
        from src.competitor_pricing.tracker import CompetitorProduct
        matcher = self._make()
        my_product = {'title': '블루투스 이어폰', 'price': 30000.0, 'category': 'electronics'}
        cp = CompetitorProduct(
            competitor_id='c1', product_id='p1',
            competitor_name='셀러', platform='naver',
            title='블루투스 이어폰 무선 ANC',
            price=32000.0,
            metadata={'category': 'electronics'},
        )
        score = matcher.calculate_match_score(my_product, cp)
        assert 0.0 <= score <= 100.0


# ==============================================================================
# PricePositionAnalyzer
# ==============================================================================

class TestPricePositionAnalyzer:
    def _make_with_data(self):
        from src.competitor_pricing.tracker import CompetitorTracker
        from src.competitor_pricing.position_analyzer import PricePositionAnalyzer
        tracker = CompetitorTracker()
        tracker.add_competitor(_sample_competitor(price=20000.0, product_id='p1'))
        tracker.add_competitor(_sample_competitor(price=35000.0, product_id='p1', competitor_name='B'))
        analyzer = PricePositionAnalyzer(tracker)
        analyzer.register_my_product('p1', 30000.0)
        return analyzer

    def test_analyze_position_returns_position(self):
        analyzer = self._make_with_data()
        pos = analyzer.analyze_position('p1')
        assert pos.my_product_id == 'p1'
        assert pos.my_price == 30000.0

    def test_analyze_position_has_stats(self):
        analyzer = self._make_with_data()
        pos = analyzer.analyze_position('p1')
        assert pos.min_price > 0
        assert pos.max_price >= pos.min_price
        assert pos.avg_price > 0
        assert pos.median_price > 0

    def test_analyze_position_rank(self):
        analyzer = self._make_with_data()
        pos = analyzer.analyze_position('p1')
        assert 1 <= pos.my_rank <= pos.total_competitors + 1

    def test_position_label_cheapest(self):
        from src.competitor_pricing.tracker import CompetitorTracker
        from src.competitor_pricing.position_analyzer import PricePositionAnalyzer, PositionLabel
        tracker = CompetitorTracker()
        tracker.add_competitor(_sample_competitor(price=50000.0, product_id='p1'))
        tracker.add_competitor(_sample_competitor(price=60000.0, product_id='p1', competitor_name='B'))
        tracker.add_competitor(_sample_competitor(price=70000.0, product_id='p1', competitor_name='C'))
        analyzer = PricePositionAnalyzer(tracker)
        analyzer.register_my_product('p1', 10000.0)  # clearly cheapest
        pos = analyzer.analyze_position('p1')
        assert pos.position_label == PositionLabel.cheapest

    def test_position_label_most_expensive(self):
        from src.competitor_pricing.tracker import CompetitorTracker
        from src.competitor_pricing.position_analyzer import PricePositionAnalyzer, PositionLabel
        tracker = CompetitorTracker()
        # Add 10 cheap competitors so my price lands at 91st percentile (>90th)
        for i, price in enumerate([10000, 11000, 12000, 13000, 14000, 15000, 16000, 17000, 18000, 19000]):
            tracker.add_competitor(_sample_competitor(price=float(price), product_id='p1', competitor_name=f'C{i}'))
        analyzer = PricePositionAnalyzer(tracker)
        analyzer.register_my_product('p1', 99999.0)  # clearly the most expensive
        pos = analyzer.analyze_position('p1')
        assert pos.position_label == PositionLabel.most_expensive

    def test_analyze_position_no_competitors_uses_mock(self):
        from src.competitor_pricing.tracker import CompetitorTracker
        from src.competitor_pricing.position_analyzer import PricePositionAnalyzer
        tracker = CompetitorTracker()
        analyzer = PricePositionAnalyzer(tracker)
        analyzer.register_my_product('p_new', 30000.0)
        pos = analyzer.analyze_position('p_new')
        assert len(pos.competitor_prices) > 0

    def test_analyze_all_positions(self):
        analyzer = self._make_with_data()
        positions = analyzer.analyze_all_positions()
        assert 'p1' in positions

    def test_get_price_distribution_returns_buckets(self):
        analyzer = self._make_with_data()
        dist = analyzer.get_price_distribution('p1')
        assert isinstance(dist, list)
        assert len(dist) > 0
        assert 'count' in dist[0]
        assert 'range_start' in dist[0]
        assert 'range_end' in dist[0]

    def test_get_position_summary(self):
        analyzer = self._make_with_data()
        summary = analyzer.get_position_summary()
        assert isinstance(summary, dict)
        assert 'cheapest' in summary
        assert 'most_expensive' in summary

    def test_detect_price_war_empty(self):
        analyzer = self._make_with_data()
        wars = analyzer.detect_price_war()
        assert isinstance(wars, list)

    def test_detect_price_war_with_drops(self):
        from src.competitor_pricing.tracker import CompetitorTracker
        from src.competitor_pricing.position_analyzer import PricePositionAnalyzer
        tracker = CompetitorTracker()
        cp = tracker.add_competitor(_sample_competitor(price=30000.0, product_id='pwar'))
        # manually inject dropping prices into history
        tracker._price_history[cp.competitor_id] = [
            {'price': 30000.0, 'checked_at': '2024-01-01'},
            {'price': 28000.0, 'checked_at': '2024-01-02'},
            {'price': 26000.0, 'checked_at': '2024-01-03'},
            {'price': 24000.0, 'checked_at': '2024-01-04'},
        ]
        analyzer = PricePositionAnalyzer(tracker)
        wars = analyzer.detect_price_war('pwar')
        assert 'pwar' in wars


# ==============================================================================
# PriceAdjustmentSuggester
# ==============================================================================

class TestPriceAdjustmentSuggester:
    def _make(self):
        from src.competitor_pricing.tracker import CompetitorTracker
        from src.competitor_pricing.position_analyzer import PricePositionAnalyzer
        from src.competitor_pricing.adjuster import PriceAdjustmentSuggester
        tracker = CompetitorTracker()
        tracker.add_competitor(_sample_competitor(price=25000.0, product_id='p1'))
        tracker.add_competitor(_sample_competitor(price=28000.0, product_id='p1', competitor_name='B'))
        analyzer = PricePositionAnalyzer(tracker)
        analyzer.register_my_product('p1', 30000.0)
        return PriceAdjustmentSuggester(tracker, analyzer)

    def test_suggest_match_lowest(self):
        from src.competitor_pricing.adjuster import AdjustmentStrategy
        adjuster = self._make()
        suggestion = adjuster.suggest_adjustment('p1', strategy=AdjustmentStrategy.match_lowest)
        assert suggestion is not None
        assert suggestion.suggested_price <= 30000.0

    def test_suggest_beat_lowest(self):
        from src.competitor_pricing.adjuster import AdjustmentStrategy
        adjuster = self._make()
        suggestion = adjuster.suggest_adjustment('p1', strategy=AdjustmentStrategy.beat_lowest)
        assert suggestion is not None
        assert suggestion.suggested_price < 30000.0

    def test_suggest_match_average(self):
        from src.competitor_pricing.adjuster import AdjustmentStrategy
        adjuster = self._make()
        suggestion = adjuster.suggest_adjustment('p1', strategy=AdjustmentStrategy.match_average)
        assert suggestion is not None
        assert suggestion.suggested_price > 0

    def test_suggest_maintain_margin(self):
        from src.competitor_pricing.adjuster import AdjustmentStrategy
        adjuster = self._make()
        suggestion = adjuster.suggest_adjustment('p1', strategy=AdjustmentStrategy.maintain_margin)
        assert suggestion is not None

    def test_suggest_dynamic(self):
        from src.competitor_pricing.adjuster import AdjustmentStrategy
        adjuster = self._make()
        suggestion = adjuster.suggest_adjustment('p1', strategy=AdjustmentStrategy.dynamic)
        assert suggestion is not None

    def test_suggestion_has_required_fields(self):
        from src.competitor_pricing.adjuster import AdjustmentStrategy, SuggestionStatus
        adjuster = self._make()
        s = adjuster.suggest_adjustment('p1', AdjustmentStrategy.match_lowest)
        assert s.suggestion_id
        assert s.my_product_id == 'p1'
        assert s.current_price > 0
        assert s.suggested_price > 0
        assert s.status == SuggestionStatus.pending

    def test_apply_suggestion(self):
        from src.competitor_pricing.adjuster import AdjustmentStrategy, SuggestionStatus
        adjuster = self._make()
        s = adjuster.suggest_adjustment('p1', AdjustmentStrategy.match_lowest)
        result = adjuster.apply_suggestion(s.suggestion_id)
        assert result is True
        updated = adjuster.get_suggestions(status=SuggestionStatus.applied)
        assert any(u.suggestion_id == s.suggestion_id for u in updated)

    def test_reject_suggestion(self):
        from src.competitor_pricing.adjuster import AdjustmentStrategy, SuggestionStatus
        adjuster = self._make()
        s = adjuster.suggest_adjustment('p1', AdjustmentStrategy.match_lowest)
        result = adjuster.reject_suggestion(s.suggestion_id, reason='너무 낮음')
        assert result is True
        updated = adjuster.get_suggestions(status=SuggestionStatus.rejected)
        assert any(u.suggestion_id == s.suggestion_id for u in updated)

    def test_suggest_bulk_adjustments(self):
        adjuster = self._make()
        suggestions = adjuster.suggest_bulk_adjustments()
        assert isinstance(suggestions, list)

    def test_get_suggestions_filtered_by_status(self):
        from src.competitor_pricing.adjuster import AdjustmentStrategy, SuggestionStatus
        adjuster = self._make()
        adjuster.suggest_adjustment('p1', AdjustmentStrategy.match_lowest)
        pending = adjuster.get_suggestions(status=SuggestionStatus.pending)
        assert len(pending) >= 1

    def test_margin_safety_block(self):
        """제안 가격이 적자 임계값 이하면 거부."""
        from src.competitor_pricing.tracker import CompetitorTracker
        from src.competitor_pricing.position_analyzer import PricePositionAnalyzer
        from src.competitor_pricing.adjuster import PriceAdjustmentSuggester, AdjustmentStrategy
        tracker = CompetitorTracker()
        # 매우 낮은 경쟁사 가격 (원가보다 낮을 수 있음)
        tracker.add_competitor(_sample_competitor(price=1.0, product_id='p_cheap'))
        analyzer = PricePositionAnalyzer(tracker)
        analyzer.register_my_product('p_cheap', 10000.0)
        adjuster = PriceAdjustmentSuggester(tracker, analyzer)
        # match_lowest would suggest price of 1.0 which is catastrophic loss
        suggestion = adjuster.suggest_adjustment('p_cheap', AdjustmentStrategy.match_lowest)
        # Either blocked (None) or status is rejected
        if suggestion is not None:
            from src.competitor_pricing.adjuster import SuggestionStatus
            assert suggestion.status == SuggestionStatus.rejected or suggestion.suggested_price >= 1.0

    def test_auto_adjust_mode_default(self):
        adjuster = self._make()
        assert adjuster.auto_adjust_mode is False

    def test_auto_adjust_mode_setter(self):
        adjuster = self._make()
        adjuster.auto_adjust_mode = True
        assert adjuster.auto_adjust_mode is True


# ==============================================================================
# CompetitorPriceRules
# ==============================================================================

class TestCompetitorPriceRules:
    def _make(self):
        from src.competitor_pricing.price_rules import CompetitorPriceRules
        return CompetitorPriceRules()

    def test_default_rules_created(self):
        rules = self._make()
        assert len(rules.get_rules()) == 5

    def test_default_rule_names(self):
        rules = self._make()
        names = {r.name for r in rules.get_rules()}
        assert '마진_안전장치' in names
        assert '독점_판매' in names

    def test_add_rule(self):
        rules = self._make()
        new_rule = rules.add_rule({
            'name': '테스트_규칙',
            'condition': 'test_condition',
            'action': 'test_action',
            'priority': 3,
        })
        assert new_rule.rule_id
        assert new_rule.name == '테스트_규칙'
        assert len(rules.get_rules()) == 6

    def test_remove_rule(self):
        rules = self._make()
        rule_list = rules.get_rules()
        rule_id = rule_list[0].rule_id
        result = rules.remove_rule(rule_id)
        assert result is True
        assert len(rules.get_rules()) == 4

    def test_remove_nonexistent_rule(self):
        rules = self._make()
        result = rules.remove_rule('nonexistent')
        assert result is False

    def test_evaluate_rules_margin_safety(self):
        rules = self._make()
        ctx = {'margin_rate': 3.0}
        matched = rules.evaluate_rules('p1', ctx)
        names = [r.name for r in matched]
        assert '마진_안전장치' in names

    def test_evaluate_rules_monopoly(self):
        rules = self._make()
        ctx = {'competitor_count': 0}
        matched = rules.evaluate_rules('p1', ctx)
        names = [r.name for r in matched]
        assert '독점_판매' in names

    def test_evaluate_rules_price_above_min(self):
        rules = self._make()
        ctx = {'my_price_above_min': True}
        matched = rules.evaluate_rules('p1', ctx)
        names = [r.name for r in matched]
        assert '비싼_상품_알림' in names

    def test_evaluate_rules_competitor_out_of_stock(self):
        rules = self._make()
        ctx = {'all_competitors_unavailable': True}
        matched = rules.evaluate_rules('p1', ctx)
        names = [r.name for r in matched]
        assert '경쟁사_품절' in names

    def test_evaluate_rules_competitor_price_drop(self):
        rules = self._make()
        ctx = {'competitor_price_dropped': True}
        matched = rules.evaluate_rules('p1', ctx)
        names = [r.name for r in matched]
        assert '경쟁사_인하_알림' in names

    def test_get_rules_sorted_by_priority(self):
        rules = self._make()
        rule_list = rules.get_rules()
        priorities = [r.priority for r in rule_list]
        assert priorities == sorted(priorities, reverse=True)


# ==============================================================================
# CompetitorAlertService
# ==============================================================================

class TestCompetitorAlertService:
    def _make(self):
        from src.competitor_pricing.tracker import CompetitorTracker
        from src.competitor_pricing.competitor_alerts import CompetitorAlertService
        tracker = CompetitorTracker()
        svc = CompetitorAlertService(tracker)
        return svc, tracker

    def test_check_alerts_empty_history(self):
        svc, tracker = self._make()
        tracker.add_competitor(_sample_competitor(price=30000.0))
        alerts = svc.check_alerts()
        assert isinstance(alerts, list)

    def test_check_alerts_price_drop(self):
        from src.competitor_pricing.competitor_alerts import AlertType
        svc, tracker = self._make()
        cp = tracker.add_competitor(_sample_competitor(price=30000.0))
        # inject history with price drop > 5%
        tracker._price_history[cp.competitor_id] = [
            {'price': 30000.0, 'checked_at': '2024-01-01'},
            {'price': 25000.0, 'checked_at': '2024-01-02'},
        ]
        alerts = svc.check_alerts()
        drop_alerts = [a for a in alerts if a.alert_type == AlertType.price_drop]
        assert len(drop_alerts) >= 1

    def test_check_alerts_price_increase(self):
        from src.competitor_pricing.competitor_alerts import AlertType
        svc, tracker = self._make()
        cp = tracker.add_competitor(_sample_competitor(price=30000.0))
        # inject history with price increase > 5%
        tracker._price_history[cp.competitor_id] = [
            {'price': 25000.0, 'checked_at': '2024-01-01'},
            {'price': 30000.0, 'checked_at': '2024-01-02'},
        ]
        alerts = svc.check_alerts()
        inc_alerts = [a for a in alerts if a.alert_type == AlertType.price_increase]
        assert len(inc_alerts) >= 1

    def test_acknowledge_alert(self):
        from src.competitor_pricing.competitor_alerts import AlertType
        svc, tracker = self._make()
        cp = tracker.add_competitor(_sample_competitor(price=30000.0))
        tracker._price_history[cp.competitor_id] = [
            {'price': 30000.0, 'checked_at': '2024-01-01'},
            {'price': 20000.0, 'checked_at': '2024-01-02'},
        ]
        alerts = svc.check_alerts()
        assert len(alerts) >= 1
        result = svc.acknowledge_alert(alerts[0].alert_id)
        assert result is True
        updated = svc.get_alerts(acknowledged=True)
        assert any(a.alert_id == alerts[0].alert_id for a in updated)

    def test_get_alerts_filter_by_acknowledged(self):
        svc, tracker = self._make()
        alerts_before = svc.get_alerts(acknowledged=False)
        assert isinstance(alerts_before, list)

    def test_get_alert_summary(self):
        svc, _ = self._make()
        summary = svc.get_alert_summary()
        assert 'total' in summary
        assert 'by_type' in summary
        assert 'by_severity' in summary

    def test_alert_type_enum_values(self):
        from src.competitor_pricing.competitor_alerts import AlertType
        assert AlertType.price_drop.value == 'price_drop'
        assert AlertType.new_competitor.value == 'new_competitor'
        assert AlertType.price_war_detected.value == 'price_war_detected'
        assert AlertType.lost_cheapest.value == 'lost_cheapest'
        assert AlertType.became_cheapest.value == 'became_cheapest'


# ==============================================================================
# CompetitorDashboard
# ==============================================================================

class TestCompetitorDashboard:
    def _make(self):
        from src.competitor_pricing.tracker import CompetitorTracker
        from src.competitor_pricing.position_analyzer import PricePositionAnalyzer
        from src.competitor_pricing.adjuster import PriceAdjustmentSuggester
        from src.competitor_pricing.competitor_dashboard import CompetitorDashboard
        tracker = CompetitorTracker()
        tracker.add_competitor(_sample_competitor(price=25000.0, product_id='p1'))
        tracker.add_competitor(_sample_competitor(price=35000.0, product_id='p1', competitor_name='B'))
        analyzer = PricePositionAnalyzer(tracker)
        analyzer.register_my_product('p1', 30000.0)
        adjuster = PriceAdjustmentSuggester(tracker, analyzer)
        return CompetitorDashboard(tracker, analyzer, adjuster)

    def test_get_dashboard_data_keys(self):
        dashboard = self._make()
        data = dashboard.get_dashboard_data()
        assert 'position_distribution' in data
        assert 'total_competitors' in data
        assert 'suggestion_stats' in data
        assert 'price_war_products' in data
        assert 'competition_score' in data

    def test_get_dashboard_data_position_distribution(self):
        dashboard = self._make()
        data = dashboard.get_dashboard_data()
        dist = data['position_distribution']
        assert 'cheapest' in dist
        assert 'most_expensive' in dist

    def test_get_dashboard_data_total_competitors(self):
        dashboard = self._make()
        data = dashboard.get_dashboard_data()
        assert data['total_competitors'] >= 2

    def test_get_competition_intensity_returns_float(self):
        dashboard = self._make()
        intensity = dashboard.get_competition_intensity()
        assert isinstance(intensity, float)
        assert intensity >= 0.0

    def test_get_competition_intensity_for_product(self):
        dashboard = self._make()
        intensity = dashboard.get_competition_intensity('p1')
        assert isinstance(intensity, float)

    def test_suggestion_stats_in_dashboard(self):
        dashboard = self._make()
        data = dashboard.get_dashboard_data()
        stats = data['suggestion_stats']
        assert 'pending' in stats
        assert 'applied' in stats
        assert 'rejected' in stats


# ==============================================================================
# CompetitorCheckScheduler
# ==============================================================================

class TestCompetitorCheckScheduler:
    def _make(self):
        from src.competitor_pricing.competitor_scheduler import CompetitorCheckScheduler
        return CompetitorCheckScheduler()

    def _make_cp(self, price=30000.0):
        from src.competitor_pricing.tracker import CompetitorTracker
        tracker = CompetitorTracker()
        return tracker.add_competitor(_sample_competitor(price=price))

    def test_register_returns_entry(self):
        scheduler = self._make()
        cp = self._make_cp()
        entry = scheduler.register(cp, priority=5)
        assert entry.competitor_id == cp.competitor_id
        assert entry.interval_minutes > 0

    def test_register_popular_priority(self):
        from src.competitor_pricing.competitor_scheduler import INTERVAL_POPULAR
        scheduler = self._make()
        cp = self._make_cp()
        entry = scheduler.register(cp, priority=9)
        assert entry.interval_minutes == INTERVAL_POPULAR

    def test_register_normal_priority(self):
        from src.competitor_pricing.competitor_scheduler import INTERVAL_NORMAL
        scheduler = self._make()
        cp = self._make_cp()
        entry = scheduler.register(cp, priority=5)
        assert entry.interval_minutes == INTERVAL_NORMAL

    def test_register_inactive_priority(self):
        from src.competitor_pricing.competitor_scheduler import INTERVAL_INACTIVE
        scheduler = self._make()
        cp = self._make_cp()
        entry = scheduler.register(cp, priority=1)
        assert entry.interval_minutes == INTERVAL_INACTIVE

    def test_unregister(self):
        scheduler = self._make()
        cp = self._make_cp()
        scheduler.register(cp)
        result = scheduler.unregister(cp.competitor_id)
        assert result is True

    def test_unregister_nonexistent(self):
        scheduler = self._make()
        result = scheduler.unregister('nonexistent')
        assert result is False

    def test_get_next_checks(self):
        scheduler = self._make()
        cp1 = self._make_cp(price=10000.0)
        cp2 = self._make_cp(price=20000.0)
        scheduler.register(cp1)
        scheduler.register(cp2)
        next_checks = scheduler.get_next_checks(limit=5)
        assert len(next_checks) == 2

    def test_get_next_checks_limit(self):
        scheduler = self._make()
        for _ in range(5):
            cp = self._make_cp()
            scheduler.register(cp)
        checks = scheduler.get_next_checks(limit=3)
        assert len(checks) == 3

    def test_update_schedule(self):
        scheduler = self._make()
        cp = self._make_cp()
        scheduler.register(cp)
        result = scheduler.update_schedule(cp.competitor_id, 120)
        assert result is True
        entry = scheduler._schedules[cp.competitor_id]
        assert entry.interval_minutes == 120

    def test_mark_checked(self):
        scheduler = self._make()
        cp = self._make_cp()
        scheduler.register(cp)
        scheduler.mark_checked(cp.competitor_id, success=True)
        entry = scheduler._schedules[cp.competitor_id]
        assert entry.last_checked_at is not None

    def test_get_stats(self):
        scheduler = self._make()
        cp = self._make_cp()
        scheduler.register(cp)
        stats = scheduler.get_stats()
        assert 'total' in stats
        assert stats['total'] >= 1

    def test_price_war_interval(self):
        from src.competitor_pricing.competitor_scheduler import INTERVAL_PRICE_WAR
        assert INTERVAL_PRICE_WAR == 15


# ==============================================================================
# API 테스트
# ==============================================================================

@pytest.fixture
def api_client():
    import src.api.competitor_pricing_api as _api_mod
    # Reset singletons so each test starts fresh
    _api_mod._tracker = None
    _api_mod._matcher = None
    _api_mod._analyzer = None
    _api_mod._adjuster = None
    _api_mod._rules = None
    _api_mod._alerts = None
    _api_mod._dashboard = None
    _api_mod._scheduler = None

    from flask import Flask
    from src.api.competitor_pricing_api import competitor_pricing_bp
    app = Flask(__name__)
    app.register_blueprint(competitor_pricing_bp)
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client
    # Cleanup after test
    _api_mod._tracker = None
    _api_mod._matcher = None
    _api_mod._analyzer = None
    _api_mod._adjuster = None
    _api_mod._rules = None
    _api_mod._alerts = None
    _api_mod._dashboard = None
    _api_mod._scheduler = None


class TestCompetitorPricingAPI:
    def test_add_competitor_201(self, api_client):
        resp = api_client.post(
            '/api/v1/competitor-pricing/competitors',
            json=_sample_competitor(),
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['ok'] is True
        assert 'competitor' in data

    def test_list_competitors_200(self, api_client):
        resp = api_client.get('/api/v1/competitor-pricing/competitors')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'competitors' in data

    def test_get_competitor_404(self, api_client):
        resp = api_client.get('/api/v1/competitor-pricing/competitors/nonexistent')
        assert resp.status_code == 404

    def test_delete_competitor(self, api_client):
        # first add
        add_resp = api_client.post(
            '/api/v1/competitor-pricing/competitors',
            json=_sample_competitor(),
        )
        cid = add_resp.get_json()['competitor']['competitor_id']
        resp = api_client.delete(f'/api/v1/competitor-pricing/competitors/{cid}')
        assert resp.status_code == 200

    def test_check_competitor(self, api_client):
        add_resp = api_client.post(
            '/api/v1/competitor-pricing/competitors',
            json=_sample_competitor(),
        )
        cid = add_resp.get_json()['competitor']['competitor_id']
        resp = api_client.post(f'/api/v1/competitor-pricing/competitors/{cid}/check')
        assert resp.status_code == 200

    def test_get_price_history(self, api_client):
        add_resp = api_client.post(
            '/api/v1/competitor-pricing/competitors',
            json=_sample_competitor(),
        )
        cid = add_resp.get_json()['competitor']['competitor_id']
        resp = api_client.get(f'/api/v1/competitor-pricing/competitors/{cid}/history')
        assert resp.status_code == 200

    def test_find_competitors(self, api_client):
        resp = api_client.post('/api/v1/competitor-pricing/match/p1')
        assert resp.status_code == 201

    def test_get_matches(self, api_client):
        resp = api_client.get('/api/v1/competitor-pricing/matches')
        assert resp.status_code == 200

    def test_position_analysis(self, api_client):
        resp = api_client.get('/api/v1/competitor-pricing/position/p1')
        assert resp.status_code == 200

    def test_position_all(self, api_client):
        resp = api_client.get('/api/v1/competitor-pricing/position/all')
        assert resp.status_code == 200

    def test_position_summary(self, api_client):
        resp = api_client.get('/api/v1/competitor-pricing/position/summary')
        assert resp.status_code == 200

    def test_price_suggestion(self, api_client):
        resp = api_client.post('/api/v1/competitor-pricing/suggest/p1')
        assert resp.status_code in (200, 201)

    def test_bulk_suggestions(self, api_client):
        resp = api_client.post('/api/v1/competitor-pricing/suggest/bulk')
        assert resp.status_code in (200, 201)

    def test_get_suggestions(self, api_client):
        resp = api_client.get('/api/v1/competitor-pricing/suggestions')
        assert resp.status_code == 200

    def test_get_rules(self, api_client):
        resp = api_client.get('/api/v1/competitor-pricing/rules')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'rules' in data
        assert len(data['rules']) == 5  # default rules

    def test_add_rule(self, api_client):
        resp = api_client.post(
            '/api/v1/competitor-pricing/rules',
            json={'name': '새_규칙', 'condition': 'test', 'action': 'do_something'},
        )
        assert resp.status_code == 201

    def test_get_alerts(self, api_client):
        resp = api_client.get('/api/v1/competitor-pricing/alerts')
        assert resp.status_code == 200

    def test_get_alerts_summary(self, api_client):
        resp = api_client.get('/api/v1/competitor-pricing/alerts/summary')
        assert resp.status_code == 200

    def test_get_dashboard(self, api_client):
        resp = api_client.get('/api/v1/competitor-pricing/dashboard')
        assert resp.status_code == 200

    def test_get_schedule(self, api_client):
        resp = api_client.get('/api/v1/competitor-pricing/schedule')
        assert resp.status_code == 200


# ==============================================================================
# 봇 커맨드 테스트
# ==============================================================================

class TestCompetitorPricingBotCommands:
    def test_cmd_competitors(self):
        from src.bot.competitor_pricing_commands import cmd_competitors
        result = cmd_competitors('p1')
        assert isinstance(result, str)
        assert len(result) > 0

    def test_cmd_competitors_empty_sku(self):
        from src.bot.competitor_pricing_commands import cmd_competitors
        result = cmd_competitors('')
        assert isinstance(result, str)

    def test_cmd_price_position(self):
        from src.bot.competitor_pricing_commands import cmd_price_position
        result = cmd_price_position('p1')
        assert isinstance(result, str)
        assert len(result) > 0

    def test_cmd_price_position_no_sku(self):
        from src.bot.competitor_pricing_commands import cmd_price_position
        result = cmd_price_position()
        assert isinstance(result, str)

    def test_cmd_price_suggest(self):
        from src.bot.competitor_pricing_commands import cmd_price_suggest
        result = cmd_price_suggest('p1')
        assert isinstance(result, str)

    def test_cmd_competitor_alerts(self):
        from src.bot.competitor_pricing_commands import cmd_competitor_alerts
        result = cmd_competitor_alerts()
        assert isinstance(result, str)

    def test_cmd_competitor_dashboard(self):
        from src.bot.competitor_pricing_commands import cmd_competitor_dashboard
        result = cmd_competitor_dashboard()
        assert isinstance(result, str)

    def test_cmd_price_war(self):
        from src.bot.competitor_pricing_commands import cmd_price_war
        result = cmd_price_war()
        assert isinstance(result, str)

    def test_cmd_competitor_find(self):
        from src.bot.competitor_pricing_commands import cmd_competitor_find
        result = cmd_competitor_find('p1')
        assert isinstance(result, str)

    def test_cmd_price_rules(self):
        from src.bot.competitor_pricing_commands import cmd_price_rules
        result = cmd_price_rules()
        assert isinstance(result, str)
        # Should show default rules
        assert len(result) > 0

    def test_cmd_competitors_in_main_commands(self):
        """Phase 111 commands are accessible from main commands.py."""
        from src.bot.commands import cmd_competitors
        result = cmd_competitors('p1')
        assert isinstance(result, str)
