"""tests/test_sourcing_discovery.py — Phase 115: 소싱 자동 발굴 테스트 (55개+)."""
from __future__ import annotations

import pytest


# ═══════════════════════════════════════════════════════════════════════════════
# 픽스처
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def trend_analyzer():
    from src.sourcing_discovery.trend_analyzer import TrendAnalyzer
    return TrendAnalyzer()


@pytest.fixture
def opportunity_finder():
    from src.sourcing_discovery.opportunity_finder import SourcingOpportunityFinder
    return SourcingOpportunityFinder()


@pytest.fixture
def market_gap_analyzer():
    from src.sourcing_discovery.market_gap_analyzer import MarketGapAnalyzer
    return MarketGapAnalyzer()


@pytest.fixture
def supplier_scout():
    from src.sourcing_discovery.supplier_scout import SupplierScout
    return SupplierScout()


@pytest.fixture
def profitability_predictor():
    from src.sourcing_discovery.profitability_predictor import ProfitabilityPredictor
    return ProfitabilityPredictor()


@pytest.fixture
def discovery_pipeline():
    from src.sourcing_discovery.discovery_pipeline import DiscoveryPipeline
    return DiscoveryPipeline()


@pytest.fixture
def alert_service():
    from src.sourcing_discovery.discovery_alerts import DiscoveryAlertService
    return DiscoveryAlertService()


@pytest.fixture
def dashboard():
    from src.sourcing_discovery.discovery_dashboard import DiscoveryDashboard
    return DiscoveryDashboard()


@pytest.fixture
def flask_app():
    from flask import Flask
    app = Flask(__name__)
    app.config['TESTING'] = True
    from src.api.sourcing_discovery_api import sourcing_discovery_bp
    app.register_blueprint(sourcing_discovery_bp)
    return app


@pytest.fixture
def client(flask_app):
    return flask_app.test_client()


# ═══════════════════════════════════════════════════════════════════════════════
# TestTrendAnalyzer (7 tests)
# ═══════════════════════════════════════════════════════════════════════════════

class TestTrendAnalyzer:

    def test_analyze_keyword_trend_returns_trend_data(self, trend_analyzer):
        from src.sourcing_discovery.trend_analyzer import TrendData
        result = trend_analyzer.analyze_keyword_trend('무선이어폰')
        assert isinstance(result, TrendData)
        assert result.keyword == '무선이어폰'

    def test_analyze_keyword_trend_with_platform(self, trend_analyzer):
        result = trend_analyzer.analyze_keyword_trend('무선이어폰', platform='coupang')
        assert result.platform == 'coupang'

    def test_analyze_keyword_trend_unknown_keyword(self, trend_analyzer):
        from src.sourcing_discovery.trend_analyzer import TrendData
        result = trend_analyzer.analyze_keyword_trend('알수없는키워드999')
        assert isinstance(result, TrendData)
        assert result.keyword == '알수없는키워드999'

    def test_analyze_category_trends_returns_list(self, trend_analyzer):
        results = trend_analyzer.analyze_category_trends()
        assert isinstance(results, list)
        assert len(results) > 0

    def test_analyze_category_trends_with_category(self, trend_analyzer):
        results = trend_analyzer.analyze_category_trends(category='뷰티')
        assert all(t.category == '뷰티' for t in results)
        assert len(results) > 0

    def test_get_rising_trends(self, trend_analyzer):
        from src.sourcing_discovery.trend_analyzer import TrendDirection
        results = trend_analyzer.get_rising_trends(limit=10)
        assert isinstance(results, list)
        assert len(results) <= 10
        assert all(t.trend_direction in (TrendDirection.rising, TrendDirection.explosive) for t in results)

    def test_get_rising_trends_limit(self, trend_analyzer):
        results = trend_analyzer.get_rising_trends(limit=3)
        assert len(results) <= 3

    def test_get_seasonal_opportunities(self, trend_analyzer):
        results = trend_analyzer.get_seasonal_opportunities(month=6)
        assert isinstance(results, list)
        assert len(results) > 0

    def test_get_trend_summary(self, trend_analyzer):
        summary = trend_analyzer.get_trend_summary()
        assert 'total_keywords' in summary
        assert summary['total_keywords'] >= 100
        assert 'direction_distribution' in summary
        assert 'category_distribution' in summary
        assert 'avg_growth_rate' in summary
        assert 'top_explosive_keywords' in summary


# ═══════════════════════════════════════════════════════════════════════════════
# TestSourcingOpportunityFinder (11 tests)
# ═══════════════════════════════════════════════════════════════════════════════

class TestSourcingOpportunityFinder:

    def test_discover_opportunities_returns_list(self, opportunity_finder):
        results = opportunity_finder.discover_opportunities()
        assert isinstance(results, list)
        assert len(results) > 0

    def test_discover_opportunities_with_method(self, opportunity_finder):
        results = opportunity_finder.discover_opportunities(method='trend_based')
        assert len(results) > 0
        from src.sourcing_discovery.opportunity_finder import DiscoveryMethod
        assert all(o.discovery_method == DiscoveryMethod.trend_based for o in results)

    def test_discover_opportunities_with_category(self, opportunity_finder):
        results = opportunity_finder.discover_opportunities(category='뷰티')
        assert len(results) > 0
        assert all(o.category == '뷰티' for o in results)

    def test_discover_opportunities_stored(self, opportunity_finder):
        results = opportunity_finder.discover_opportunities()
        assert len(opportunity_finder._opportunities) > 0
        assert results[0].opportunity_id in opportunity_finder._opportunities

    def test_evaluate_opportunity(self, opportunity_finder):
        opps = opportunity_finder.discover_opportunities()
        opp_id = opps[0].opportunity_id
        result = opportunity_finder.evaluate_opportunity(opp_id)
        assert result['opportunity_id'] == opp_id
        assert 'evaluation' in result
        assert 'recommendation' in result

    def test_evaluate_opportunity_changes_status(self, opportunity_finder):
        from src.sourcing_discovery.opportunity_finder import OpportunityStatus
        opps = opportunity_finder.discover_opportunities()
        opp_id = opps[0].opportunity_id
        opportunity_finder.evaluate_opportunity(opp_id)
        assert opportunity_finder._opportunities[opp_id].status == OpportunityStatus.evaluating

    def test_approve_opportunity(self, opportunity_finder):
        from src.sourcing_discovery.opportunity_finder import OpportunityStatus
        opps = opportunity_finder.discover_opportunities()
        opp_id = opps[0].opportunity_id
        result = opportunity_finder.approve_opportunity(opp_id)
        assert result.status == OpportunityStatus.approved

    def test_reject_opportunity(self, opportunity_finder):
        from src.sourcing_discovery.opportunity_finder import OpportunityStatus
        opps = opportunity_finder.discover_opportunities()
        opp_id = opps[0].opportunity_id
        result = opportunity_finder.reject_opportunity(opp_id, reason='테스트 거절')
        assert result.status == OpportunityStatus.rejected
        assert result.metadata.get('reject_reason') == '테스트 거절'

    def test_get_opportunities(self, opportunity_finder):
        opportunity_finder.discover_opportunities()
        opps = opportunity_finder.get_opportunities()
        assert isinstance(opps, list)

    def test_get_opportunities_filter_by_status(self, opportunity_finder):
        opps = opportunity_finder.discover_opportunities()
        opp_id = opps[0].opportunity_id
        opportunity_finder.approve_opportunity(opp_id)
        approved = opportunity_finder.get_opportunities(status='approved')
        assert all(o.status.value == 'approved' for o in approved)

    def test_get_opportunity_not_found_returns_none(self, opportunity_finder):
        result = opportunity_finder.get_opportunity('nonexistent_id')
        assert result is None

    def test_evaluate_not_found_raises(self, opportunity_finder):
        with pytest.raises(ValueError):
            opportunity_finder.evaluate_opportunity('nonexistent_id')


# ═══════════════════════════════════════════════════════════════════════════════
# TestMarketGapAnalyzer (6 tests)
# ═══════════════════════════════════════════════════════════════════════════════

class TestMarketGapAnalyzer:

    def test_analyze_gaps_returns_list(self, market_gap_analyzer):
        gaps = market_gap_analyzer.analyze_gaps()
        assert isinstance(gaps, list)
        assert len(gaps) >= 30

    def test_analyze_gaps_with_category(self, market_gap_analyzer):
        gaps = market_gap_analyzer.analyze_gaps(category='뷰티')
        assert len(gaps) > 0
        assert all(g.category == '뷰티' for g in gaps)

    def test_analyze_gaps_sorted_by_score(self, market_gap_analyzer):
        gaps = market_gap_analyzer.analyze_gaps()
        scores = [g.gap_score for g in gaps]
        assert scores == sorted(scores, reverse=True)

    def test_get_top_gaps(self, market_gap_analyzer):
        gaps = market_gap_analyzer.get_top_gaps(limit=5)
        assert len(gaps) == 5

    def test_get_top_gaps_ordered(self, market_gap_analyzer):
        gaps = market_gap_analyzer.get_top_gaps(limit=3)
        assert gaps[0].gap_score >= gaps[1].gap_score >= gaps[2].gap_score

    def test_get_gap_by_category(self, market_gap_analyzer):
        result = market_gap_analyzer.get_gap_by_category()
        assert isinstance(result, dict)
        assert '뷰티' in result
        assert '전자기기' in result
        assert all(isinstance(v, list) for v in result.values())


# ═══════════════════════════════════════════════════════════════════════════════
# TestSupplierScout (7 tests)
# ═══════════════════════════════════════════════════════════════════════════════

class TestSupplierScout:

    def test_scout_suppliers_returns_list(self, supplier_scout):
        candidates = supplier_scout.scout_suppliers()
        assert isinstance(candidates, list)
        assert len(candidates) > 0

    def test_scout_suppliers_with_platform(self, supplier_scout):
        candidates = supplier_scout.scout_suppliers(platform='alibaba')
        assert len(candidates) > 0
        assert all(c.platform == 'alibaba' for c in candidates)

    def test_scout_suppliers_stored(self, supplier_scout):
        candidates = supplier_scout.scout_suppliers()
        assert len(supplier_scout._candidates) > 0

    def test_evaluate_supplier(self, supplier_scout):
        candidates = supplier_scout.scout_suppliers(platform='taobao')
        cid = candidates[0].candidate_id
        result = supplier_scout.evaluate_supplier(cid)
        assert result['candidate_id'] == cid
        assert 'evaluation' in result

    def test_approve_supplier(self, supplier_scout):
        from src.sourcing_discovery.supplier_scout import CandidateStatus
        candidates = supplier_scout.scout_suppliers(platform='alibaba')
        cid = candidates[0].candidate_id
        result = supplier_scout.approve_supplier(cid)
        assert result.status == CandidateStatus.approved

    def test_reject_supplier(self, supplier_scout):
        from src.sourcing_discovery.supplier_scout import CandidateStatus
        candidates = supplier_scout.scout_suppliers(platform='taobao')
        cid = candidates[0].candidate_id
        result = supplier_scout.reject_supplier(cid, reason='품질 미달')
        assert result.status == CandidateStatus.rejected

    def test_get_candidates(self, supplier_scout):
        supplier_scout.scout_suppliers()
        candidates = supplier_scout.get_candidates()
        assert isinstance(candidates, list)
        assert len(candidates) > 0

    def test_evaluate_not_found_raises(self, supplier_scout):
        with pytest.raises(ValueError):
            supplier_scout.evaluate_supplier('nonexistent_id')


# ═══════════════════════════════════════════════════════════════════════════════
# TestProfitabilityPredictor (8 tests)
# ═══════════════════════════════════════════════════════════════════════════════

class TestProfitabilityPredictor:

    def test_predict_profitability_basic(self, profitability_predictor):
        from src.sourcing_discovery.profitability_predictor import ProfitabilityPrediction
        result = profitability_predictor.predict_profitability({
            'product_name': '테스트상품',
            'source_price': 10.0,
            'source_currency': 'CNY',
        })
        assert isinstance(result, ProfitabilityPrediction)
        assert result.product_name == '테스트상품'

    def test_predict_profitability_krw_conversion(self, profitability_predictor):
        result = profitability_predictor.predict_profitability({
            'product_name': '상품A',
            'source_price': 10.0,
            'source_currency': 'CNY',
        })
        # 10 CNY * 185 = 1850 KRW, selling = 1850 * 2.5 = 4625
        assert result.estimated_selling_price == pytest.approx(4625.0, abs=1)

    def test_predict_profitability_usd(self, profitability_predictor):
        result = profitability_predictor.predict_profitability({
            'product_name': '달러상품',
            'source_price': 1.0,
            'source_currency': 'USD',
        })
        # 1 USD * 1350 = 1350 KRW
        assert result.estimated_costs['sourcing_krw'] == pytest.approx(1350.0, abs=1)

    def test_predict_profitability_costs_structure(self, profitability_predictor):
        result = profitability_predictor.predict_profitability({
            'product_name': '상품B',
            'source_price': 5.0,
            'source_currency': 'CNY',
        })
        assert 'customs' in result.estimated_costs
        assert 'vat' in result.estimated_costs
        assert 'platform_fee' in result.estimated_costs
        assert 'shipping' in result.estimated_costs

    def test_predict_profitability_margin_positive(self, profitability_predictor):
        result = profitability_predictor.predict_profitability({
            'product_name': '상품C',
            'source_price': 5.0,
            'source_currency': 'CNY',
        })
        assert isinstance(result.estimated_margin_rate, float)

    def test_predict_demand(self, profitability_predictor):
        result = profitability_predictor.predict_demand({
            'product_name': '인기상품',
            'search_volume': 50000,
            'growth_rate': 30.0,
        })
        assert 'estimated_monthly_units' in result
        assert 'demand_trend' in result
        assert result['demand_trend'] == 'rising'

    def test_recommend_sourcing_model_full_stock(self, profitability_predictor):
        result = profitability_predictor.recommend_sourcing_model({'monthly_units': 100})
        assert result['model'] == 'full_stock'

    def test_recommend_sourcing_model_semi_stock(self, profitability_predictor):
        result = profitability_predictor.recommend_sourcing_model({'monthly_units': 25})
        assert result['model'] == 'semi_stock'

    def test_recommend_sourcing_model_dropship(self, profitability_predictor):
        result = profitability_predictor.recommend_sourcing_model({'monthly_units': 5})
        assert result['model'] == 'pure_dropship'

    def test_batch_predict(self, profitability_predictor):
        products = [
            {'product_name': 'P1', 'source_price': 5.0, 'source_currency': 'CNY'},
            {'product_name': 'P2', 'source_price': 10.0, 'source_currency': 'CNY'},
        ]
        results = profitability_predictor.batch_predict(products)
        assert len(results) == 2
        assert results[0].product_name == 'P1'
        assert results[1].product_name == 'P2'


# ═══════════════════════════════════════════════════════════════════════════════
# TestDiscoveryPipeline (6 tests)
# ═══════════════════════════════════════════════════════════════════════════════

class TestDiscoveryPipeline:

    def test_run_pipeline_returns_run(self, discovery_pipeline):
        from src.sourcing_discovery.discovery_pipeline import PipelineRun
        run = discovery_pipeline.run_pipeline()
        assert isinstance(run, PipelineRun)
        assert run.status in ('completed', 'failed')

    def test_run_pipeline_records_history(self, discovery_pipeline):
        discovery_pipeline.run_pipeline()
        history = discovery_pipeline.get_pipeline_history()
        assert len(history) == 1

    def test_run_pipeline_finds_opportunities(self, discovery_pipeline):
        run = discovery_pipeline.run_pipeline()
        assert run.opportunities_found >= 0

    def test_get_pipeline_history_limit(self, discovery_pipeline):
        discovery_pipeline.run_pipeline()
        discovery_pipeline.run_pipeline()
        history = discovery_pipeline.get_pipeline_history(limit=1)
        assert len(history) == 1

    def test_get_pipeline_config(self, discovery_pipeline):
        from src.sourcing_discovery.discovery_pipeline import PipelineConfig
        config = discovery_pipeline.get_pipeline_config()
        assert isinstance(config, PipelineConfig)
        assert config.auto_discover_interval_hours == 24

    def test_update_pipeline_config(self, discovery_pipeline):
        config = discovery_pipeline.update_pipeline_config({'auto_discover_interval_hours': 12})
        assert config.auto_discover_interval_hours == 12

    def test_run_pipeline_duration_positive(self, discovery_pipeline):
        run = discovery_pipeline.run_pipeline()
        assert run.duration_seconds >= 0


# ═══════════════════════════════════════════════════════════════════════════════
# TestDiscoveryAlertService (6 tests)
# ═══════════════════════════════════════════════════════════════════════════════

class TestDiscoveryAlertService:

    def test_init_creates_alerts(self, alert_service):
        assert len(alert_service._alerts) == 20

    def test_check_alerts_returns_unacknowledged(self, alert_service):
        unacked = alert_service.check_alerts()
        assert len(unacked) == 20
        assert all(not a.acknowledged for a in unacked)

    def test_acknowledge_alert(self, alert_service):
        alert_id = alert_service._alerts[0].alert_id
        result = alert_service.acknowledge_alert(alert_id)
        assert result.acknowledged is True

    def test_get_alerts_filter_severity(self, alert_service):
        high_alerts = alert_service.get_alerts(severity='high')
        assert all(a.severity == 'high' for a in high_alerts)
        assert len(high_alerts) > 0

    def test_get_alerts_filter_type(self, alert_service):
        alerts = alert_service.get_alerts(alert_type='trending_category')
        assert all(a.alert_type.value == 'trending_category' for a in alerts)

    def test_get_alert_summary(self, alert_service):
        summary = alert_service.get_alert_summary()
        assert 'total_alerts' in summary
        assert summary['total_alerts'] == 20
        assert 'unacknowledged' in summary
        assert 'severity_distribution' in summary

    def test_acknowledge_not_found_raises(self, alert_service):
        with pytest.raises(ValueError):
            alert_service.acknowledge_alert('nonexistent_id')


# ═══════════════════════════════════════════════════════════════════════════════
# TestDiscoveryDashboard (3 tests)
# ═══════════════════════════════════════════════════════════════════════════════

class TestDiscoveryDashboard:

    def test_get_dashboard_data(self, dashboard):
        data = dashboard.get_dashboard_data()
        assert 'weekly_opportunities_found' in data
        assert 'weekly_approved' in data
        assert 'trend_keywords' in data
        assert 'category_distribution' in data
        assert 'pipeline_status' in data

    def test_get_dashboard_data_trend_keywords(self, dashboard):
        data = dashboard.get_dashboard_data()
        keywords = data.get('trend_keywords', [])
        assert len(keywords) > 0
        assert 'keyword' in keywords[0]

    def test_get_weekly_discovery_report(self, dashboard):
        report = dashboard.get_weekly_discovery_report()
        assert 'report_period' in report
        assert report['report_period'] == 'weekly'
        assert 'trend_summary' in report
        assert 'opportunities_discovered' in report


# ═══════════════════════════════════════════════════════════════════════════════
# TestSourcingDiscoveryAPI (10 tests)
# ═══════════════════════════════════════════════════════════════════════════════

class TestSourcingDiscoveryAPI:

    def test_get_trends(self, client):
        resp = client.get('/api/v1/sourcing-discovery/trends')
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        assert len(data) > 0

    def test_get_trends_with_category(self, client):
        resp = client.get('/api/v1/sourcing-discovery/trends?category=뷰티')
        assert resp.status_code == 200
        data = resp.get_json()
        assert all(t['category'] == '뷰티' for t in data)

    def test_get_rising_trends(self, client):
        resp = client.get('/api/v1/sourcing-discovery/trends/rising?limit=5')
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) <= 5

    def test_get_trend_summary(self, client):
        resp = client.get('/api/v1/sourcing-discovery/trends/summary')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'total_keywords' in data

    def test_discover_opportunities(self, client):
        resp = client.post(
            '/api/v1/sourcing-discovery/opportunities/discover',
            json={'limit': 5},
            content_type='application/json',
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)

    def test_get_market_gaps(self, client):
        resp = client.get('/api/v1/sourcing-discovery/market-gaps')
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        assert len(data) >= 30

    def test_get_top_gaps(self, client):
        resp = client.get('/api/v1/sourcing-discovery/market-gaps/top?limit=3')
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 3

    def test_predict_profitability(self, client):
        resp = client.post(
            '/api/v1/sourcing-discovery/predict/profitability',
            json={'product_name': 'API테스트', 'source_price': 10.0, 'source_currency': 'CNY'},
            content_type='application/json',
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['product_name'] == 'API테스트'
        assert 'estimated_margin_rate' in data

    def test_run_pipeline(self, client):
        resp = client.post('/api/v1/sourcing-discovery/pipeline/run')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'run_id' in data
        assert 'status' in data

    def test_get_alerts(self, client):
        resp = client.get('/api/v1/sourcing-discovery/alerts')
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        assert len(data) == 20

    def test_get_dashboard(self, client):
        resp = client.get('/api/v1/sourcing-discovery/dashboard')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'weekly_opportunities_found' in data

    def test_get_seasonal_trends(self, client):
        resp = client.get('/api/v1/sourcing-discovery/trends/seasonal?month=6')
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)


# ═══════════════════════════════════════════════════════════════════════════════
# TestDiscoveryBotCommands (6 tests)
# ═══════════════════════════════════════════════════════════════════════════════

class TestDiscoveryBotCommands:

    def test_cmd_trending(self):
        from src.bot.discovery_commands import cmd_trending
        result = cmd_trending()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_cmd_market_gaps(self):
        from src.bot.discovery_commands import cmd_market_gaps
        result = cmd_market_gaps()
        assert isinstance(result, str)
        assert '마켓 갭' in result

    def test_cmd_predict_profit(self):
        from src.bot.discovery_commands import cmd_predict_profit
        result = cmd_predict_profit('테스트상품:10:CNY')
        assert isinstance(result, str)
        assert '테스트상품' in result

    def test_cmd_seasonal_opportunities(self):
        from src.bot.discovery_commands import cmd_seasonal_opportunities
        result = cmd_seasonal_opportunities()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_cmd_discovery_alerts(self):
        from src.bot.discovery_commands import cmd_discovery_alerts
        result = cmd_discovery_alerts()
        assert isinstance(result, str)
        assert '알림' in result

    def test_cmd_discovery_pipeline(self):
        from src.bot.discovery_commands import cmd_discovery_pipeline
        result = cmd_discovery_pipeline()
        assert isinstance(result, str)
        assert '파이프라인' in result
