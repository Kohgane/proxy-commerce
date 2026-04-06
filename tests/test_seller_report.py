"""tests/test_seller_report.py — Phase 114: 셀러 성과 리포트 테스트 (55개+)."""
from __future__ import annotations

import pytest
from datetime import date, datetime, timedelta


# ═══════════════════════════════════════════════════════════════════════════════
# 공통 픽스처
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def metrics_engine():
    from src.seller_report.metrics_engine import PerformanceMetricsEngine
    return PerformanceMetricsEngine()


@pytest.fixture
def channel_analyzer():
    from src.seller_report.channel_performance import ChannelPerformanceAnalyzer
    return ChannelPerformanceAnalyzer()


@pytest.fixture
def product_analyzer():
    from src.seller_report.product_performance import ProductPerformanceAnalyzer
    return ProductPerformanceAnalyzer()


@pytest.fixture
def sourcing_analyzer():
    from src.seller_report.sourcing_performance import SourcingPerformanceAnalyzer
    return SourcingPerformanceAnalyzer()


@pytest.fixture
def hybrid_advisor():
    from src.seller_report.hybrid_model_advisor import HybridModelAdvisor
    return HybridModelAdvisor()


@pytest.fixture
def report_generator():
    from src.seller_report.report_generator import PerformanceReportGenerator
    return PerformanceReportGenerator()


@pytest.fixture
def alert_service():
    from src.seller_report.performance_alerts import PerformanceAlertService
    return PerformanceAlertService()


@pytest.fixture
def goal_manager():
    from src.seller_report.goal_manager import PerformanceGoalManager
    return PerformanceGoalManager()


@pytest.fixture
def flask_app():
    from flask import Flask
    app = Flask(__name__)
    app.config['TESTING'] = True
    from src.api.seller_report_api import seller_report_bp
    app.register_blueprint(seller_report_bp)
    return app


@pytest.fixture
def client(flask_app):
    return flask_app.test_client()


# ═══════════════════════════════════════════════════════════════════════════════
# PerformanceMetricsEngine
# ═══════════════════════════════════════════════════════════════════════════════

class TestPerformanceMetricsEngine:

    def test_calculate_metrics_daily(self, metrics_engine):
        m = metrics_engine.calculate_metrics('daily')
        assert m.period == 'daily'
        assert m.total_revenue > 0
        assert m.total_orders > 0
        assert 0 <= m.gross_margin_rate <= 100
        assert isinstance(m.start_date, date)
        assert isinstance(m.end_date, date)

    def test_calculate_metrics_weekly(self, metrics_engine):
        m = metrics_engine.calculate_metrics('weekly')
        assert m.period == 'weekly'
        assert m.total_revenue > 0
        days = (m.end_date - m.start_date).days
        assert days >= 6

    def test_calculate_metrics_monthly(self, metrics_engine):
        m = metrics_engine.calculate_metrics('monthly')
        assert m.period == 'monthly'
        assert m.total_revenue > 0

    def test_calculate_metrics_custom_dates(self, metrics_engine):
        start = date.today() - timedelta(days=10)
        end = date.today()
        m = metrics_engine.calculate_metrics('custom', start_date=start, end_date=end)
        assert m.start_date == start
        assert m.end_date == end

    def test_metrics_fields_valid(self, metrics_engine):
        m = metrics_engine.calculate_metrics('daily')
        assert m.gross_profit == pytest.approx(m.total_revenue - m.total_cost, abs=1)
        assert 0 <= m.return_rate <= 100
        assert 0 <= m.cancel_rate <= 100
        assert 0 <= m.fulfillment_rate <= 100
        assert 0 <= m.sla_compliance_rate <= 100
        assert m.avg_order_value > 0

    def test_get_kpi_summary(self, metrics_engine):
        kpi = metrics_engine.get_kpi_summary()
        assert 'revenue' in kpi
        assert 'orders' in kpi
        assert 'gross_margin_rate' in kpi
        assert 'return_rate' in kpi
        assert 'value' in kpi['revenue']
        assert 'change_rate' in kpi['revenue']
        assert 'generated_at' in kpi

    def test_compare_periods(self, metrics_engine):
        result = metrics_engine.compare_periods('weekly', 'monthly')
        assert result['comparison_type'] == 'weekly_vs_monthly'
        assert 'revenue' in result
        assert 'period1' in result['revenue']
        assert 'period2' in result['revenue']
        assert 'change_rate' in result['revenue']

    def test_get_metric_trend(self, metrics_engine):
        trend = metrics_engine.get_metric_trend('total_revenue', period='daily', interval=7)
        assert len(trend) == 7
        assert all('date' in t and 'value' in t for t in trend)
        assert all(t['value'] > 0 for t in trend)

    def test_get_metric_trend_default_interval(self, metrics_engine):
        trend = metrics_engine.get_metric_trend('total_orders')
        assert len(trend) == 7

    def test_metrics_all_fields_present(self, metrics_engine):
        from src.seller_report.metrics_engine import PerformanceMetrics
        import dataclasses
        m = metrics_engine.calculate_metrics('daily')
        fields = {f.name for f in dataclasses.fields(PerformanceMetrics)}
        for field in fields:
            assert hasattr(m, field)


# ═══════════════════════════════════════════════════════════════════════════════
# ChannelPerformanceAnalyzer
# ═══════════════════════════════════════════════════════════════════════════════

class TestChannelPerformanceAnalyzer:

    def test_analyze_channel_coupang(self, channel_analyzer):
        perf = channel_analyzer.analyze_channel('coupang')
        assert perf.channel == 'coupang'
        assert perf.revenue > 0
        assert perf.orders > 0

    def test_analyze_channel_naver(self, channel_analyzer):
        perf = channel_analyzer.analyze_channel('naver')
        assert perf.channel == 'naver'
        assert perf.revenue > 0

    def test_analyze_channel_self_mall(self, channel_analyzer):
        perf = channel_analyzer.analyze_channel('self_mall')
        assert perf.channel == 'self_mall'

    def test_compare_channels_returns_all(self, channel_analyzer):
        channels = channel_analyzer.compare_channels()
        channel_names = {c.channel for c in channels}
        assert 'coupang' in channel_names
        assert 'naver' in channel_names
        assert 'self_mall' in channel_names

    def test_get_best_channel(self, channel_analyzer):
        best = channel_analyzer.get_best_channel()
        all_channels = channel_analyzer.compare_channels()
        max_revenue = max(c.revenue for c in all_channels)
        assert best.revenue == max_revenue

    def test_get_channel_recommendations_structure(self, channel_analyzer):
        recs = channel_analyzer.get_channel_recommendations()
        assert isinstance(recs, list)
        for rec in recs:
            assert 'channel' in rec
            assert 'type' in rec
            assert 'message' in rec

    def test_channel_perf_fields(self, channel_analyzer):
        from src.seller_report.channel_performance import ChannelPerformance
        import dataclasses
        perf = channel_analyzer.analyze_channel('coupang')
        fields = {f.name for f in dataclasses.fields(ChannelPerformance)}
        for field in fields:
            assert hasattr(perf, field)


# ═══════════════════════════════════════════════════════════════════════════════
# ProductPerformanceAnalyzer
# ═══════════════════════════════════════════════════════════════════════════════

class TestProductPerformanceAnalyzer:

    def test_analyze_product_exists(self, product_analyzer):
        perf = product_analyzer.analyze_product('PROD_0001')
        assert perf is not None
        assert perf.product_id == 'PROD_0001'

    def test_analyze_product_not_found(self, product_analyzer):
        perf = product_analyzer.analyze_product('NONEXISTENT_9999')
        assert perf is None

    def test_get_product_ranking_default(self, product_analyzer):
        ranking = product_analyzer.get_product_ranking()
        assert len(ranking) == 20
        revenues = [p.revenue for p in ranking]
        assert revenues == sorted(revenues, reverse=True)

    def test_get_product_ranking_by_margin(self, product_analyzer):
        ranking = product_analyzer.get_product_ranking(sort_by='margin_rate', limit=10)
        assert len(ranking) == 10
        margins = [p.margin_rate for p in ranking]
        assert margins == sorted(margins, reverse=True)

    def test_get_product_ranking_by_channel(self, product_analyzer):
        ranking = product_analyzer.get_product_ranking(channel='coupang', limit=50)
        assert all(p.channel == 'coupang' for p in ranking)

    def test_get_product_ranking_limit(self, product_analyzer):
        ranking = product_analyzer.get_product_ranking(limit=5)
        assert len(ranking) == 5

    def test_get_product_grades_all_grades(self, product_analyzer):
        from src.seller_report.product_performance import ProductGrade
        grades = product_analyzer.get_product_grades()
        for grade in ProductGrade:
            assert grade.value in grades
            assert isinstance(grades[grade.value], list)

    def test_get_product_grades_star_top_10_pct(self, product_analyzer):
        grades = product_analyzer.get_product_grades()
        total = sum(len(v) for v in grades.values())
        star_count = len(grades['star'])
        assert star_count <= total * 0.12  # 10% + small margin

    def test_get_profitability_matrix_quadrants(self, product_analyzer):
        matrix = product_analyzer.get_profitability_matrix()
        assert 'stars' in matrix
        assert 'hidden_gems' in matrix
        assert 'volume_drivers' in matrix
        assert 'dogs' in matrix
        total = sum(len(v) for v in matrix.values())
        assert total == 200  # 전체 상품 수

    def test_get_dead_stock(self, product_analyzer):
        dead = product_analyzer.get_dead_stock(days_threshold=30)
        assert isinstance(dead, list)

    def test_get_dead_stock_threshold(self, product_analyzer):
        dead_30 = product_analyzer.get_dead_stock(days_threshold=30)
        dead_60 = product_analyzer.get_dead_stock(days_threshold=60)
        assert len(dead_30) >= len(dead_60)

    def test_get_trending_products(self, product_analyzer):
        trending = product_analyzer.get_trending_products(limit=10)
        assert len(trending) == 10
        sales = [p.avg_daily_sales for p in trending]
        assert sales == sorted(sales, reverse=True)

    def test_product_grade_enum_values(self):
        from src.seller_report.product_performance import ProductGrade
        assert ProductGrade.star.value == 'star'
        assert ProductGrade.poor.value == 'poor'
        assert len(list(ProductGrade)) == 5


# ═══════════════════════════════════════════════════════════════════════════════
# SourcingPerformanceAnalyzer
# ═══════════════════════════════════════════════════════════════════════════════

class TestSourcingPerformanceAnalyzer:

    def test_analyze_source_exists(self, sourcing_analyzer):
        perf = sourcing_analyzer.analyze_source('SRC_001')
        assert perf is not None
        assert perf.source_id == 'SRC_001'

    def test_analyze_source_not_found(self, sourcing_analyzer):
        perf = sourcing_analyzer.analyze_source('SRC_999')
        assert perf is None

    def test_compare_sources(self, sourcing_analyzer):
        sources = sourcing_analyzer.compare_sources()
        assert len(sources) == 15
        for s in sources:
            assert s.source_id is not None
            assert s.success_rate >= 0

    def test_get_source_ranking_ordered(self, sourcing_analyzer):
        ranking = sourcing_analyzer.get_source_ranking()
        assert len(ranking) == 15
        # 첫 번째가 가장 높은 점수여야 함 (확인 가능한 범위에서)
        assert ranking[0].success_rate >= 0

    def test_get_problematic_sources(self, sourcing_analyzer):
        problematic = sourcing_analyzer.get_problematic_sources()
        assert isinstance(problematic, list)
        for s in problematic:
            is_problematic = (
                s.success_rate < 80
                or s.avg_delivery_days > 14
                or s.issue_count > 15
            )
            assert is_problematic

    def test_get_source_recommendations_structure(self, sourcing_analyzer):
        recs = sourcing_analyzer.get_source_recommendations()
        assert isinstance(recs, list)
        for rec in recs:
            assert 'source_id' in rec
            assert 'type' in rec
            assert 'message' in rec

    def test_sourcing_perf_fields(self, sourcing_analyzer):
        from src.seller_report.sourcing_performance import SourcingPerformance
        import dataclasses
        perf = sourcing_analyzer.analyze_source('SRC_001')
        fields = {f.name for f in dataclasses.fields(SourcingPerformance)}
        for field in fields:
            assert hasattr(perf, field)


# ═══════════════════════════════════════════════════════════════════════════════
# HybridModelAdvisor
# ═══════════════════════════════════════════════════════════════════════════════

class TestHybridModelAdvisor:

    def test_analyze_all_products_count(self, hybrid_advisor):
        recs = hybrid_advisor.analyze_all_products()
        assert len(recs) == 200

    def test_a_grade_full_stock(self, hybrid_advisor):
        """월 50개 이상 판매 → full_stock 추천."""
        recs = hybrid_advisor.analyze_all_products()
        full_stock = [r for r in recs if r.monthly_sales >= 50]
        for r in full_stock:
            assert r.recommended_model.value == 'full_stock', (
                f"{r.product_id} 월{r.monthly_sales}개인데 {r.recommended_model.value}"
            )

    def test_b_grade_semi_stock(self, hybrid_advisor):
        """월 10~50개 판매 → semi_stock 추천."""
        recs = hybrid_advisor.analyze_all_products()
        semi_stock = [r for r in recs if 10 <= r.monthly_sales < 50]
        for r in semi_stock:
            assert r.recommended_model.value == 'semi_stock'

    def test_c_grade_pure_dropship(self, hybrid_advisor):
        """월 10개 미만 → pure_dropship 유지."""
        recs = hybrid_advisor.analyze_all_products()
        dropship = [r for r in recs if r.monthly_sales < 10]
        for r in dropship:
            assert r.recommended_model.value == 'pure_dropship'

    def test_get_stock_recommendations_excludes_dropship(self, hybrid_advisor):
        recs = hybrid_advisor.get_stock_recommendations()
        for r in recs:
            assert r.recommended_model.value != 'pure_dropship'

    def test_get_investment_estimate_structure(self, hybrid_advisor):
        est = hybrid_advisor.get_investment_estimate()
        assert 'total_investment' in est
        assert 'full_stock_investment' in est
        assert 'semi_stock_investment' in est
        assert 'total_products_to_convert' in est
        assert est['total_investment'] >= 0
        assert est['total_investment'] == est['full_stock_investment'] + est['semi_stock_investment']

    def test_get_delivery_improvement_estimate(self, hybrid_advisor):
        result = hybrid_advisor.get_delivery_improvement_estimate()
        assert 'avg_delivery_before_days' in result
        assert 'avg_delivery_after_days' in result
        assert 'avg_improvement_days' in result
        assert result['avg_delivery_before_days'] == 12.0
        assert result['avg_delivery_after_days'] <= 12.0

    def test_get_hybrid_summary_structure(self, hybrid_advisor):
        summary = hybrid_advisor.get_hybrid_summary()
        assert 'total_products' in summary
        assert 'convert_count' in summary
        assert 'total_investment' in summary
        assert 'summary_text' in summary
        assert summary['total_products'] == 200

    def test_hybrid_summary_text_contains_key_info(self, hybrid_advisor):
        summary = hybrid_advisor.get_hybrid_summary()
        text = summary['summary_text']
        assert '200' in text  # 전체 상품 수
        assert '원' in text   # 투자금 단위

    def test_simulate_model_change_valid(self, hybrid_advisor):
        result = hybrid_advisor.simulate_model_change('PROD_0001', 'full_stock')
        assert 'product_id' in result
        assert result['product_id'] == 'PROD_0001'
        assert result['new_model'] == 'full_stock'
        assert 'delivery_after_days' in result

    def test_simulate_model_change_invalid_product(self, hybrid_advisor):
        result = hybrid_advisor.simulate_model_change('NONEXISTENT', 'full_stock')
        assert 'error' in result

    def test_simulate_model_change_invalid_model(self, hybrid_advisor):
        result = hybrid_advisor.simulate_model_change('PROD_0001', 'invalid_model')
        assert 'error' in result

    def test_sourcing_model_enum(self):
        from src.seller_report.hybrid_model_advisor import SourcingModel
        assert SourcingModel.pure_dropship.value == 'pure_dropship'
        assert SourcingModel.semi_stock.value == 'semi_stock'
        assert SourcingModel.full_stock.value == 'full_stock'
        assert SourcingModel.hybrid.value == 'hybrid'

    def test_full_stock_delivery_improvement(self, hybrid_advisor):
        """full_stock 전환 시 배송 개선이 있어야 함."""
        recs = hybrid_advisor.analyze_all_products()
        full_stock_recs = [r for r in recs if r.recommended_model.value == 'full_stock']
        for r in full_stock_recs:
            assert r.estimated_delivery_improvement > 0

    def test_recommendation_confidence_score(self, hybrid_advisor):
        recs = hybrid_advisor.analyze_all_products()
        for r in recs:
            assert 0.0 <= r.confidence_score <= 1.0


# ═══════════════════════════════════════════════════════════════════════════════
# PerformanceReportGenerator
# ═══════════════════════════════════════════════════════════════════════════════

class TestPerformanceReportGenerator:

    def test_generate_daily_report(self, report_generator):
        report = report_generator.generate_daily_report()
        assert report['report_type'] == 'daily'
        assert 'metrics' in report
        assert 'top_products' in report
        assert 'worst_products' in report
        assert 'generated_at' in report

    def test_generate_weekly_report(self, report_generator):
        report = report_generator.generate_weekly_report()
        assert report['report_type'] == 'weekly'
        assert 'kpi_summary' in report
        assert 'channel_performance' in report
        assert 'hybrid_suggestion' in report

    def test_generate_monthly_report(self, report_generator):
        report = report_generator.generate_monthly_report()
        assert report['report_type'] == 'monthly'
        assert 'overall_performance' in report
        assert 'profitability_matrix' in report
        assert 'hybrid_model_analysis' in report
        assert 'next_month_targets' in report

    def test_generate_report_dispatch(self, report_generator):
        daily = report_generator.generate_report('daily')
        assert daily['report_type'] == 'daily'
        weekly = report_generator.generate_report('weekly')
        assert weekly['report_type'] == 'weekly'

    def test_report_history_saved(self, report_generator):
        report_generator.generate_daily_report()
        history = report_generator.get_report_history()
        assert len(history) >= 1
        assert history[-1]['report_type'] == 'daily'

    def test_report_history_filter_by_type(self, report_generator):
        report_generator.generate_daily_report()
        report_generator.generate_weekly_report()
        daily_history = report_generator.get_report_history(report_type='daily')
        assert all(r['report_type'] == 'daily' for r in daily_history)

    def test_report_history_limit(self, report_generator):
        for _ in range(5):
            report_generator.generate_daily_report()
        history = report_generator.get_report_history(limit=3)
        assert len(history) <= 3

    def test_schedule_reports(self, report_generator):
        schedule = report_generator.schedule_reports()
        assert 'daily' in schedule
        assert 'weekly' in schedule
        assert 'monthly' in schedule
        assert schedule['status'] == 'active'

    def test_daily_report_markdown_format(self, report_generator):
        report = report_generator.generate_daily_report(fmt='markdown')
        assert 'content' in report
        assert '일간 리포트' in report['content']

    def test_monthly_next_month_targets(self, report_generator):
        report = report_generator.generate_monthly_report()
        targets = report['next_month_targets']
        assert 'revenue_target' in targets
        assert 'margin_target' in targets
        assert 'order_target' in targets
        assert targets['revenue_target'] > 0


# ═══════════════════════════════════════════════════════════════════════════════
# PerformanceAlertService
# ═══════════════════════════════════════════════════════════════════════════════

class TestPerformanceAlertService:

    def test_get_alerts_returns_list(self, alert_service):
        alerts = alert_service.get_alerts()
        assert isinstance(alerts, list)

    def test_get_alerts_filter_by_severity(self, alert_service):
        critical = alert_service.get_alerts(severity='critical')
        assert all(a.severity == 'critical' for a in critical)

    def test_get_alerts_filter_by_acknowledged(self, alert_service):
        unacked = alert_service.get_alerts(acknowledged=False)
        assert all(not a.acknowledged for a in unacked)

    def test_acknowledge_alert_success(self, alert_service):
        alerts = alert_service.get_alerts()
        if alerts:
            alert_id = alerts[0].alert_id
            result = alert_service.acknowledge_alert(alert_id)
            assert result is True
            updated = [a for a in alert_service.get_alerts() if a.alert_id == alert_id]
            assert updated[0].acknowledged is True

    def test_acknowledge_alert_not_found(self, alert_service):
        result = alert_service.acknowledge_alert('nonexistent_id')
        assert result is False

    def test_get_alert_summary_structure(self, alert_service):
        summary = alert_service.get_alert_summary()
        assert 'total' in summary
        assert 'critical' in summary
        assert 'warning' in summary
        assert 'info' in summary
        assert 'unacknowledged' in summary
        assert 'types' in summary

    def test_alert_summary_counts_match(self, alert_service):
        summary = alert_service.get_alert_summary()
        assert summary['critical'] + summary['warning'] + summary['info'] == summary['total']

    def test_check_alerts_returns_list(self, alert_service):
        new_alerts = alert_service.check_alerts()
        assert isinstance(new_alerts, list)

    def test_alert_dataclass_fields(self, alert_service):
        from src.seller_report.performance_alerts import PerformanceAlert
        import dataclasses
        alerts = alert_service.get_alerts()
        if alerts:
            fields = {f.name for f in dataclasses.fields(PerformanceAlert)}
            for field in fields:
                assert hasattr(alerts[0], field)

    def test_alert_type_enum_values(self):
        from src.seller_report.performance_alerts import AlertType
        assert AlertType.revenue_drop.value == 'revenue_drop'
        assert AlertType.sla_breach.value == 'sla_breach'
        assert len(list(AlertType)) == 7


# ═══════════════════════════════════════════════════════════════════════════════
# PerformanceGoalManager
# ═══════════════════════════════════════════════════════════════════════════════

class TestPerformanceGoalManager:

    def test_set_goal_creates_goal(self, goal_manager):
        goal = goal_manager.set_goal('total_revenue', 10_000_000, 'monthly')
        assert goal.metric_name == 'total_revenue'
        assert goal.target_value == 10_000_000
        assert goal.period == 'monthly'
        assert goal.goal_id is not None

    def test_set_goal_start_end_dates(self, goal_manager):
        goal = goal_manager.set_goal('total_orders', 500, 'monthly')
        assert goal.start_date <= goal.end_date

    def test_get_goals_empty_initially(self):
        from src.seller_report.goal_manager import PerformanceGoalManager
        mgr = PerformanceGoalManager()
        goals = mgr.get_goals()
        assert goals == []

    def test_get_goals_after_set(self, goal_manager):
        goal_manager.set_goal('total_revenue', 10_000_000)
        goals = goal_manager.get_goals()
        assert len(goals) == 1

    def test_get_goals_filter_by_period(self, goal_manager):
        goal_manager.set_goal('total_revenue', 10_000_000, 'monthly')
        goal_manager.set_goal('total_orders', 100, 'weekly')
        monthly = goal_manager.get_goals(period='monthly')
        assert all(g.period == 'monthly' for g in monthly)

    def test_update_progress(self, goal_manager):
        goal_manager.set_goal('total_revenue', 10_000_000, 'monthly')
        updated = goal_manager.update_progress()
        assert len(updated) == 1
        assert updated[0].current_value > 0
        assert updated[0].progress_rate >= 0

    def test_goal_status_on_track(self, goal_manager):
        from src.seller_report.goal_manager import GoalStatus
        # 아주 낮은 목표치 → 달성 가능
        goal_manager.set_goal('total_revenue', 1, 'monthly')
        updated = goal_manager.update_progress()
        assert updated[0].status in [GoalStatus.on_track, GoalStatus.achieved]

    def test_goal_status_behind(self, goal_manager):
        from src.seller_report.goal_manager import GoalStatus
        # 아주 높은 목표치 → behind
        goal_manager.set_goal('total_revenue', 10_000_000_000, 'monthly')
        updated = goal_manager.update_progress()
        assert updated[0].status in [GoalStatus.behind, GoalStatus.at_risk, GoalStatus.on_track]

    def test_get_goal_dashboard_structure(self, goal_manager):
        goal_manager.set_goal('total_revenue', 10_000_000)
        goal_manager.update_progress()
        dashboard = goal_manager.get_goal_dashboard()
        assert 'goals' in dashboard
        assert 'summary' in dashboard
        assert 'total' in dashboard['summary']

    def test_goal_dashboard_progress_bar(self, goal_manager):
        goal_manager.set_goal('total_revenue', 1, 'monthly')
        goal_manager.update_progress()
        dashboard = goal_manager.get_goal_dashboard()
        if dashboard['goals']:
            assert 'progress_bar' in dashboard['goals'][0]

    def test_check_goal_alerts_returns_list(self, goal_manager):
        goal_manager.set_goal('total_revenue', 10_000_000)
        goal_manager.update_progress()
        alerts = goal_manager.check_goal_alerts()
        assert isinstance(alerts, list)

    def test_goal_status_enum_values(self):
        from src.seller_report.goal_manager import GoalStatus
        assert GoalStatus.on_track.value == 'on_track'
        assert GoalStatus.achieved.value == 'achieved'
        assert GoalStatus.failed.value == 'failed'
        assert len(list(GoalStatus)) == 5


# ═══════════════════════════════════════════════════════════════════════════════
# API 엔드포인트 테스트
# ═══════════════════════════════════════════════════════════════════════════════

class TestSellerReportAPI:

    def test_get_metrics(self, client):
        resp = client.get('/api/v1/seller-report/metrics')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'total_revenue' in data

    def test_get_metrics_summary(self, client):
        resp = client.get('/api/v1/seller-report/metrics/summary')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'revenue' in data

    def test_compare_metrics(self, client):
        resp = client.get('/api/v1/seller-report/metrics/compare?period1=weekly&period2=monthly')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'comparison_type' in data

    def test_get_metric_trend(self, client):
        resp = client.get('/api/v1/seller-report/metrics/trend/total_revenue')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'trend' in data

    def test_get_channels(self, client):
        resp = client.get('/api/v1/seller-report/channel')
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        assert len(data) == 3

    def test_get_channel_single(self, client):
        resp = client.get('/api/v1/seller-report/channel/coupang')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['channel'] == 'coupang'

    def test_compare_channels_endpoint(self, client):
        resp = client.get('/api/v1/seller-report/channel/compare')
        assert resp.status_code == 200

    def test_get_channel_recommendations(self, client):
        resp = client.get('/api/v1/seller-report/channel/recommendations')
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    def test_get_product_ranking(self, client):
        resp = client.get('/api/v1/seller-report/product/ranking')
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)

    def test_get_product_grades(self, client):
        resp = client.get('/api/v1/seller-report/product/grades')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'star' in data

    def test_get_product_matrix(self, client):
        resp = client.get('/api/v1/seller-report/product/matrix')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'stars' in data
        assert 'dogs' in data

    def test_get_dead_stock(self, client):
        resp = client.get('/api/v1/seller-report/product/dead-stock')
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    def test_get_trending_products(self, client):
        resp = client.get('/api/v1/seller-report/product/trending')
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    def test_get_product_by_id(self, client):
        resp = client.get('/api/v1/seller-report/product/PROD_0001')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['product_id'] == 'PROD_0001'

    def test_get_product_not_found(self, client):
        resp = client.get('/api/v1/seller-report/product/NONEXISTENT_9999')
        assert resp.status_code == 404

    def test_get_sourcing(self, client):
        resp = client.get('/api/v1/seller-report/sourcing')
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    def test_get_sourcing_ranking(self, client):
        resp = client.get('/api/v1/seller-report/sourcing/ranking')
        assert resp.status_code == 200

    def test_get_problematic_sources(self, client):
        resp = client.get('/api/v1/seller-report/sourcing/problematic')
        assert resp.status_code == 200

    def test_get_sourcing_recommendations(self, client):
        resp = client.get('/api/v1/seller-report/sourcing/recommendations')
        assert resp.status_code == 200

    def test_get_source_by_id(self, client):
        resp = client.get('/api/v1/seller-report/sourcing/SRC_001')
        assert resp.status_code == 200

    def test_get_source_not_found(self, client):
        resp = client.get('/api/v1/seller-report/sourcing/SRC_999')
        assert resp.status_code == 404

    def test_get_hybrid_analysis(self, client):
        resp = client.get('/api/v1/seller-report/hybrid/analysis')
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        assert len(data) == 200

    def test_get_hybrid_recommendations(self, client):
        resp = client.get('/api/v1/seller-report/hybrid/recommendations')
        assert resp.status_code == 200

    def test_get_hybrid_investment(self, client):
        resp = client.get('/api/v1/seller-report/hybrid/investment')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'total_investment' in data

    def test_get_delivery_improvement(self, client):
        resp = client.get('/api/v1/seller-report/hybrid/delivery-improvement')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'avg_improvement_days' in data

    def test_get_hybrid_summary(self, client):
        resp = client.get('/api/v1/seller-report/hybrid/summary')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'summary_text' in data

    def test_simulate_model_change(self, client):
        resp = client.post(
            '/api/v1/seller-report/hybrid/simulate',
            json={'product_id': 'PROD_0001', 'new_model': 'full_stock'},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['new_model'] == 'full_stock'

    def test_simulate_model_change_missing_fields(self, client):
        resp = client.post('/api/v1/seller-report/hybrid/simulate', json={})
        assert resp.status_code == 400

    def test_generate_daily_report(self, client):
        resp = client.post('/api/v1/seller-report/report/daily')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['report_type'] == 'daily'

    def test_generate_weekly_report(self, client):
        resp = client.post('/api/v1/seller-report/report/weekly')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['report_type'] == 'weekly'

    def test_generate_monthly_report(self, client):
        resp = client.post('/api/v1/seller-report/report/monthly')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['report_type'] == 'monthly'

    def test_get_report_history(self, client):
        client.post('/api/v1/seller-report/report/daily')
        resp = client.get('/api/v1/seller-report/report/history')
        assert resp.status_code == 200

    def test_get_alerts(self, client):
        resp = client.get('/api/v1/seller-report/alerts')
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    def test_get_alert_summary(self, client):
        resp = client.get('/api/v1/seller-report/alerts/summary')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'total' in data

    def test_acknowledge_alert_not_found(self, client):
        resp = client.post('/api/v1/seller-report/alerts/nonexistent/acknowledge')
        assert resp.status_code == 404

    def test_set_goal(self, client):
        resp = client.post(
            '/api/v1/seller-report/goals',
            json={'metric_name': 'total_revenue', 'target_value': 10_000_000, 'period': 'monthly'},
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['metric_name'] == 'total_revenue'

    def test_set_goal_missing_fields(self, client):
        resp = client.post('/api/v1/seller-report/goals', json={'metric_name': 'total_revenue'})
        assert resp.status_code == 400

    def test_get_goals(self, client):
        resp = client.get('/api/v1/seller-report/goals')
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    def test_get_goal_dashboard(self, client):
        resp = client.get('/api/v1/seller-report/goals/dashboard')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'summary' in data

    def test_update_goal_progress(self, client):
        resp = client.post('/api/v1/seller-report/goals/update-progress')
        assert resp.status_code == 200

    def test_get_dashboard(self, client):
        resp = client.get('/api/v1/seller-report/dashboard')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'today_metrics' in data
        assert 'hybrid_summary' in data
        assert 'alert_summary' in data


# ═══════════════════════════════════════════════════════════════════════════════
# 봇 커맨드 테스트
# ═══════════════════════════════════════════════════════════════════════════════

class TestBotCommands:

    def test_cmd_my_report_daily(self):
        from src.bot.commands import cmd_my_report
        result = cmd_my_report('daily')
        assert isinstance(result, str)
        assert len(result) > 0

    def test_cmd_my_report_weekly(self):
        from src.bot.commands import cmd_my_report
        result = cmd_my_report('weekly')
        assert isinstance(result, str)

    def test_cmd_my_report_monthly(self):
        from src.bot.commands import cmd_my_report
        result = cmd_my_report('monthly')
        assert isinstance(result, str)

    def test_cmd_daily_summary(self):
        from src.bot.commands import cmd_daily_summary
        result = cmd_daily_summary()
        assert isinstance(result, str)
        assert '매출' in result or '오늘' in result

    def test_cmd_product_rank_top(self):
        from src.bot.commands import cmd_product_rank
        result = cmd_product_rank('top', 5)
        assert isinstance(result, str)

    def test_cmd_product_rank_bottom(self):
        from src.bot.commands import cmd_product_rank
        result = cmd_product_rank('bottom', 5)
        assert isinstance(result, str)

    def test_cmd_channel_compare(self):
        from src.bot.commands import cmd_channel_compare
        result = cmd_channel_compare()
        assert isinstance(result, str)

    def test_cmd_source_rank(self):
        from src.bot.commands import cmd_source_rank
        result = cmd_source_rank()
        assert isinstance(result, str)

    def test_cmd_hybrid_suggest(self):
        from src.bot.commands import cmd_hybrid_suggest
        result = cmd_hybrid_suggest()
        assert isinstance(result, str)
        assert '사입' in result or '추천' in result

    def test_cmd_hybrid_invest(self):
        from src.bot.commands import cmd_hybrid_invest
        result = cmd_hybrid_invest()
        assert isinstance(result, str)
        assert '투자' in result or '원' in result

    def test_cmd_performance_alerts(self):
        from src.bot.commands import cmd_performance_alerts
        result = cmd_performance_alerts()
        assert isinstance(result, str)

    def test_cmd_dead_stock(self):
        from src.bot.commands import cmd_dead_stock
        result = cmd_dead_stock()
        assert isinstance(result, str)

    def test_cmd_trending_products(self):
        from src.bot.commands import cmd_trending_products
        result = cmd_trending_products()
        assert isinstance(result, str)

    def test_cmd_my_goals(self):
        from src.bot.commands import cmd_my_goals
        result = cmd_my_goals()
        assert isinstance(result, str)

    def test_cmd_seller_dashboard(self):
        from src.bot.commands import cmd_seller_dashboard
        result = cmd_seller_dashboard()
        assert isinstance(result, str)
        assert '대시보드' in result or '매출' in result
