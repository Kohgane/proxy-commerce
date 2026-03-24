"""텔레그램 봇 커맨드 구현 — dashboard, fx, inventory 모듈 연동."""

import logging
import os
from datetime import date

from .formatters import format_message

logger = logging.getLogger(__name__)


def cmd_status() -> str:
    """/status — 미완료 주문 현황 요약."""
    try:
        from ..dashboard.order_status import OrderStatusTracker
        tracker = OrderStatusTracker()
        stats = tracker.get_stats()
        pending = tracker.get_pending_orders()
        return format_message('status', stats, pending=pending)
    except Exception as exc:
        logger.error("cmd_status 오류: %s", exc)
        return format_message('error', f'주문 현황 조회 실패: {exc}')


def cmd_revenue(period: str = 'today') -> str:
    """/revenue [today|week|month] — 매출 요약."""
    period = period.strip().lower()
    try:
        from ..dashboard.revenue_report import RevenueReporter
        reporter = RevenueReporter()

        if period == 'today':
            data = reporter.daily_revenue()
            label = f"오늘 ({date.today().isoformat()})"
        elif period == 'week':
            data = reporter.weekly_revenue()
            label = "이번 주"
        elif period == 'month':
            data = reporter.monthly_revenue()
            label = f"이번 달 ({date.today().strftime('%Y-%m')})"
        else:
            return format_message('error', f'유효하지 않은 기간: {period}\n사용법: /revenue [today|week|month]')

        return format_message('revenue', data, label=label)
    except Exception as exc:
        logger.error("cmd_revenue 오류: %s", exc)
        return format_message('error', f'매출 조회 실패: {exc}')


def cmd_stock(filter_type: str = 'low') -> str:
    """/stock [low|all] — 재고 현황."""
    filter_type = filter_type.strip().lower()
    try:
        from ..inventory.inventory_sync import InventorySync
        sync = InventorySync()
        rows = sync._get_active_rows()

        low_threshold = int(os.getenv('LOW_STOCK_THRESHOLD', '3'))

        if filter_type == 'low':
            items = [r for r in rows if int(r.get('stock', 0)) <= low_threshold]
            label = f"저재고 상품 (임계값: {low_threshold})"
        else:
            items = rows
            label = "전체 재고"

        return format_message('stock', items, label=label)
    except Exception as exc:
        logger.error("cmd_stock 오류: %s", exc)
        return format_message('error', f'재고 조회 실패: {exc}')


def cmd_fx() -> str:
    """/fx — 현재 환율 + 변동률."""
    try:
        from ..fx.provider import FXProvider
        from ..fx.history import FXHistory
        provider = FXProvider()
        rates = provider.get_rates()

        # 이전 환율 비교 (이력 있는 경우)
        prev_rates = None
        try:
            history = FXHistory()
            prev_rates = history.get_latest_rates()
        except Exception:
            pass  # 이력 없으면 변동률 생략

        return format_message('fx', rates, prev_rates=prev_rates)
    except Exception as exc:
        logger.error("cmd_fx 오류: %s", exc)
        return format_message('error', f'환율 조회 실패: {exc}')


def cmd_reviews(period: str = 'today') -> str:
    """/reviews [today|week|month] — 리뷰 요약."""
    period = period.strip().lower()
    valid = ('today', 'week', 'month')
    if period not in valid:
        period = 'today'

    days_map = {'today': 1, 'week': 7, 'month': 30}
    days = days_map[period]

    try:
        from ..reviews.collector import ReviewCollector
        from ..reviews.analyzer import ReviewAnalyzer
        collector = ReviewCollector()
        analyzer = ReviewAnalyzer()
        reviews = collector.get_reviews()
        summary = analyzer.generate_review_summary(reviews=reviews, days=days)
        return format_message('reviews', summary, label=period)
    except Exception as exc:
        logger.error("cmd_reviews 오류: %s", exc)
        return format_message('error', f'리뷰 조회 실패: {exc}')


def cmd_promo(sub: str = 'active') -> str:
    """/promo [list|active] — 프로모션 현황."""
    sub = sub.strip().lower()
    active_only = sub != 'list'

    try:
        from ..promotions.engine import PromotionEngine
        engine = PromotionEngine()
        promos = engine.get_promotions(active_only=active_only)
        label = "활성 프로모션" if active_only else "전체 프로모션"
        return format_message('promos', promos, label=label)
    except Exception as exc:
        logger.error("cmd_promo 오류: %s", exc)
        return format_message('error', f'프로모션 조회 실패: {exc}')


def cmd_customers(sub: str = 'summary') -> str:
    """/customers [vip|at_risk|summary] — 고객 세그먼트 요약."""
    sub = sub.strip().lower()

    try:
        from ..crm.customer_profile import CustomerProfileManager
        from ..crm.segmentation import CustomerSegmentation
        manager = CustomerProfileManager()
        segmentation = CustomerSegmentation()

        if sub == 'summary':
            customers = manager.get_all_customers()
            summary = segmentation.get_segment_summary(customers=customers)
            return format_message('customer_segments', summary)
        elif sub == 'vip':
            customers = manager.get_all_customers(segment='VIP')
            return format_message('customer_list', customers, label='VIP')
        elif sub == 'at_risk':
            customers = manager.get_all_customers(segment='AT_RISK')
            return format_message('customer_list', customers, label='이탈 위험')
        else:
            return format_message('error', f'유효하지 않은 옵션: {sub}\n사용법: /customers [vip|at_risk|summary]')
    except Exception as exc:
        logger.error("cmd_customers 오류: %s", exc)
        return format_message('error', f'고객 조회 실패: {exc}')


def cmd_help() -> str:
    """/help — 도움말."""
    return (
        "*🤖 Proxy Commerce 봇 도움말*\n\n"
        "사용 가능한 커맨드:\n\n"
        "📦 `/status` — 미완료 주문 현황 요약\n"
        "💰 `/revenue [today|week|month]` — 매출 요약\n"
        "  예) `/revenue week`\n\n"
        "📊 `/stock [low|all]` — 재고 현황\n"
        "  예) `/stock low` (저재고만 표시)\n\n"
        "💱 `/fx` — 현재 환율 + 변동률\n"
        "⭐ `/reviews [today|week|month]` — 리뷰 요약\n"
        "🎯 `/promo [list|active]` — 프로모션 현황\n"
        "👥 `/customers [vip|at_risk|summary]` — 고객 세그먼트 요약\n"
        "📣 `/campaign [list|active]` — 캠페인 현황\n"
        "📊 `/report [sales|inventory|customers|marketing]` — 리포트 생성\n"
        "🧪 `/abtest [list|<실험명>]` — A/B 테스트 결과\n"
        "🏪 `/competitor [sku]` — 경쟁사 가격 비교\n"
        "  SKU 없으면 전체 가격 경쟁력 요약\n"
        "🔮 `/forecast [sku]` — 수요 예측 + 재고 소진 예상일\n"
        "  SKU 없으면 14일 내 소진 위험 상품 목록\n"
        "📈 `/trends [top|declining]` — 상품 트렌드 요약\n"
        "⚙️ `/rules [list|stats]` — 자동화 규칙 현황\n"
        "❓ `/help` — 이 도움말\n"
    )


def cmd_campaign(args: str = 'list') -> str:
    """/campaign [list|active] — 캠페인 현황."""
    sub = args.strip().lower()
    active_only = sub == 'active'

    try:
        from ..marketing.campaign_manager import CampaignManager
        manager = CampaignManager()
        status_filter = 'active' if active_only else None
        campaigns = manager.get_campaigns(status=status_filter)
        label = "활성 캠페인" if active_only else "전체 캠페인"
        return format_message('campaigns', campaigns, label=label)
    except Exception as exc:
        logger.error("cmd_campaign 오류: %s", exc)
        return format_message('error', f'캠페인 조회 실패: {exc}')


def cmd_report(args: str = 'sales today') -> str:
    """/report [sales|inventory|customers|marketing] — 리포트 생성."""
    parts = args.strip().lower().split()
    report_type = parts[0] if parts else 'sales'

    try:
        from ..reporting.report_builder import ReportBuilder
        builder = ReportBuilder()
        report = builder.generate_report(report_type)
        return format_message('report', report, label=report_type)
    except Exception as exc:
        logger.error("cmd_report 오류: %s", exc)
        return format_message('error', f'리포트 생성 실패: {exc}')


def cmd_abtest(args: str = 'list') -> str:
    """/abtest [list|<실험명>] — A/B 테스트 결과."""
    experiment_name = args.strip()
    if not experiment_name or experiment_name.lower() == 'list':
        return format_message('abtest', {}, label='A/B 테스트 목록')

    try:
        from ..marketing.ab_testing import ABTestManager
        manager = ABTestManager()
        results = manager.get_results(experiment_name)
        return format_message('abtest', results, label=experiment_name)
    except Exception as exc:
        logger.error("cmd_abtest 오류: %s", exc)
        return format_message('error', f'A/B 테스트 조회 실패: {exc}')


def cmd_competitor(args: str = '') -> str:
    """/competitor [sku] — 특정 SKU 경쟁사 가격 비교."""
    sku = args.strip()
    try:
        from ..competitor.price_tracker import CompetitorPriceTracker
        tracker = CompetitorPriceTracker()
        if sku:
            data = tracker.get_price_comparison(sku)
        else:
            overpriced = tracker.get_overpriced_items(threshold_pct=10)
            underpriced = tracker.get_underpriced_items(threshold_pct=10)
            data = {'overpriced': overpriced, 'underpriced': underpriced}
        return format_message('competitor', data, label=sku or '전체')
    except Exception as exc:
        logger.error("cmd_competitor 오류: %s", exc)
        return format_message('error', f'경쟁사 가격 조회 실패: {exc}')


def cmd_forecast(args: str = '') -> str:
    """/forecast [sku] — 수요 예측 + 재고 소진 예상일."""
    sku = args.strip()
    try:
        from ..forecasting.demand_predictor import DemandPredictor
        from ..forecasting.stock_optimizer import StockOptimizer
        predictor = DemandPredictor()
        optimizer = StockOptimizer()
        if sku:
            forecast = predictor.predict_demand(sku, days_ahead=30)
            at_risk = optimizer.get_stockout_risk(days_horizon=14)
            sku_risk = next((r for r in at_risk if r['sku'] == sku), None)
            data = {'forecast': forecast, 'stockout_risk': sku_risk}
        else:
            at_risk = optimizer.get_stockout_risk(days_horizon=14)
            data = {'stockout_risk': at_risk}
        return format_message('forecast', data, label=sku or '소진 위험')
    except Exception as exc:
        logger.error("cmd_forecast 오류: %s", exc)
        return format_message('error', f'수요 예측 조회 실패: {exc}')


def cmd_trends(args: str = 'top') -> str:
    """/trends [top|declining] — 상품 트렌드 요약."""
    sub = args.strip().lower()
    try:
        from ..forecasting.trend_analyzer import TrendAnalyzer
        analyzer = TrendAnalyzer()
        trends = analyzer.analyze_trends(period_days=30)
        if sub == 'declining':
            items = [t for t in trends if t.get('trend') == 'falling']
            label = '하락 추세'
        else:
            items = [t for t in trends if t.get('grade') in ('Star', 'Cash Cow')][:10]
            label = '상위 상품'
        return format_message('trends', items, label=label)
    except Exception as exc:
        logger.error("cmd_trends 오류: %s", exc)
        return format_message('error', f'트렌드 조회 실패: {exc}')


def cmd_rules(args: str = 'list') -> str:
    """/rules [list|stats] — 자동화 규칙 현황."""
    sub = args.strip().lower()
    try:
        from ..automation.rule_engine import RuleEngine
        engine = RuleEngine()
        rules = engine.get_rules(enabled_only=False)
        if sub == 'stats':
            enabled = sum(1 for r in rules if str(r.get('enabled', '1')) in ('1', 'true', 'True'))
            data = {
                'total': len(rules),
                'enabled': enabled,
                'disabled': len(rules) - enabled,
                'by_trigger': {},
            }
            for r in rules:
                trigger = r.get('trigger', 'unknown')
                data['by_trigger'][trigger] = data['by_trigger'].get(trigger, 0) + 1
        else:
            data = rules
        return format_message('rules', data, label=sub)
    except Exception as exc:
        logger.error("cmd_rules 오류: %s", exc)
        return format_message('error', f'자동화 규칙 조회 실패: {exc}')
