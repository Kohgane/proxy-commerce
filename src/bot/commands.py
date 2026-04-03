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


def cmd_order_alerts(args: str = 'status') -> str:
    """/order_alerts [status] — 최근 주문 알림 요약 또는 상태 조회."""
    sub = args.strip().lower()
    try:
        from ..order_alerts.order_tracker import OrderTracker
        tracker = OrderTracker()
        recent = tracker.get_alerted_orders(limit=10)
        data = {
            'sub': sub,
            'orders': recent,
            'total': len(recent),
        }
        return format_message('order_alerts', data, label=sub)
    except Exception as exc:
        logger.error("cmd_order_alerts 오류: %s", exc)
        return format_message('error', f'주문 알림 조회 실패: {exc}')


def cmd_settlement(args: str = 'today') -> str:
    """/settlement [today|week|month] — 기간별 정산 요약."""
    period = args.strip().lower()
    try:
        from ..payments.settlement import SettlementCalculator
        calc = SettlementCalculator()
        summary = calc.summarize([])
        summary['period'] = period
        return format_message('settlement', summary, label=period)
    except Exception as exc:
        logger.error("cmd_settlement 오류: %s", exc)
        return format_message('error', f'정산 조회 실패: {exc}')


def cmd_tracking(tracking_number: str = '') -> str:
    """/tracking <운송장번호> — 배송 추적."""
    tn = tracking_number.strip()
    if not tn:
        return format_message('error', '운송장 번호를 입력해 주세요. 예: /tracking 1234567890')
    try:
        from ..shipping.tracker import ShipmentTracker
        tracker = ShipmentTracker()
        record = tracker.get_status(tn)
        if record is None:
            return format_message('error', f'등록되지 않은 운송장 번호: {tn}')
        return format_message('tracking', record)
    except Exception as exc:
        logger.error("cmd_tracking 오류: %s", exc)
        return format_message('error', f'배송 추적 실패: {exc}')


def cmd_cs_list(args: str = '') -> str:
    """/cs_list — CS 티켓 목록."""
    status_filter = args.strip() or None
    try:
        from ..customer_service.ticket_manager import TicketManager
        manager = TicketManager()
        tickets = manager.list_tickets(status=status_filter)
        return format_message('cs_tickets', tickets, label=status_filter or '전체')
    except Exception as exc:
        logger.error("cmd_cs_list 오류: %s", exc)
        return format_message('error', f'CS 티켓 목록 조회 실패: {exc}')


def cmd_cs_reply(args: str = '') -> str:
    """/cs_reply <ticket_id> <message> — CS 티켓 답변."""
    parts = args.strip().split(' ', 1)
    if len(parts) < 2 or not parts[0] or not parts[1]:
        return format_message('error', '사용법: /cs_reply <ticket_id> <message>')
    ticket_id, content = parts[0], parts[1]
    try:
        from ..customer_service.ticket_manager import TicketManager
        manager = TicketManager()
        msg = manager.add_message(ticket_id, sender='agent', content=content)
        if msg is None:
            return format_message('error', f'티켓을 찾을 수 없습니다: {ticket_id}')
        return format_message('cs_reply', msg)
    except Exception as exc:
        logger.error("cmd_cs_reply 오류: %s", exc)
        return format_message('error', f'CS 답변 전송 실패: {exc}')


def cmd_analytics(args: str = 'sales') -> str:
    """/analytics [sales|customers|products] — 분석 데이터."""
    mode = args.strip().lower() or 'sales'
    try:
        if mode == 'sales':
            from ..analytics.sales_analytics import SalesAnalytics
            data = SalesAnalytics().daily_summary()
        elif mode == 'customers':
            from ..analytics.customer_analytics import CustomerAnalytics
            data = {'message': 'RFM 분석은 POST /api/v1/analytics/customers/rfm 를 사용하세요.'}
        elif mode == 'products':
            from ..analytics.product_analytics import ProductAnalytics
            data = {'message': 'ABC 분류는 POST /api/v1/analytics/products/abc 를 사용하세요.'}
        else:
            data = {'error': f'알 수 없는 분석 유형: {mode}. sales|customers|products 중 선택하세요.'}
        return format_message('analytics', data, label=mode)
    except Exception as exc:
        logger.error("cmd_analytics 오류: %s", exc)
        return format_message('error', f'분석 데이터 조회 실패: {exc}')


def cmd_sync_inventory() -> str:
    """/sync_inventory — 재고 동기화 실행."""
    try:
        from ..inventory_sync.sync_manager import InventorySyncManager
        manager = InventorySyncManager()
        result = manager.sync_all_channels()
        return format_message('sync_inventory', result)
    except Exception as exc:
        logger.error("cmd_sync_inventory 오류: %s", exc)
        return format_message('error', f'재고 동기화 실패: {exc}')


def cmd_stock_status(sku: str = '') -> str:
    """/stock_status [sku] — 재고 상태 조회."""
    try:
        from ..inventory_sync.sync_manager import InventorySyncManager
        manager = InventorySyncManager()
        if sku:
            result = manager.sync_sku(sku.strip())
        else:
            result = manager.get_sync_status()
        return format_message('stock_status', result, label=sku or '전체')
    except Exception as exc:
        logger.error("cmd_stock_status 오류: %s", exc)
        return format_message('error', f'재고 상태 조회 실패: {exc}')


def cmd_translate(product_id: str = '') -> str:
    """/translate <product_id> — 상품 번역 요청."""
    pid = product_id.strip()
    if not pid:
        return format_message('error', '사용법: /translate <product_id>')
    try:
        from ..translation.translator import TranslationManager
        manager = TranslationManager()
        req = manager.create_request(pid, f'Product {pid}', 'en', 'ko')
        return format_message('translate', req)
    except Exception as exc:
        logger.error("cmd_translate 오류: %s", exc)
        return format_message('error', f'번역 요청 실패: {exc}')


def cmd_translation_status() -> str:
    """/translation_status — 번역 요청 목록."""
    try:
        from ..translation.translator import TranslationManager
        manager = TranslationManager()
        requests = manager.get_all()
        return format_message('translation_status', requests)
    except Exception as exc:
        logger.error("cmd_translation_status 오류: %s", exc)
        return format_message('error', f'번역 상태 조회 실패: {exc}')


def cmd_reprice(sku: str = '') -> str:
    """/reprice [sku] — 자동 가격 산정 실행."""
    try:
        from ..pricing_engine.auto_pricer import AutoPricer
        pricer = AutoPricer()
        skus = [sku.strip()] if sku.strip() else None
        result = pricer.run(skus=skus, dry_run=True)
        return format_message('reprice', result, label=sku or '전체')
    except Exception as exc:
        logger.error("cmd_reprice 오류: %s", exc)
        return format_message('error', f'가격 산정 실패: {exc}')


def cmd_price_history(sku: str = '') -> str:
    """/price_history <sku> — 가격 이력 조회."""
    sku = sku.strip()
    if not sku:
        return format_message('error', '사용법: /price_history <sku>')
    try:
        from ..pricing_engine.price_history import PriceHistory
        history = PriceHistory()
        data = history.get_history(sku)
        change_rate = history.get_change_rate(sku)
        return format_message('price_history', data, label=sku, change_rate=change_rate)
    except Exception as exc:
        logger.error("cmd_price_history 오류: %s", exc)
        return format_message('error', f'가격 이력 조회 실패: {exc}')


def cmd_suppliers() -> str:
    """/suppliers — 공급자 목록 조회."""
    try:
        from ..suppliers.supplier_manager import SupplierManager
        manager = SupplierManager()
        suppliers = manager.list_all(active_only=True)
        return format_message('suppliers', suppliers)
    except Exception as exc:
        logger.error("cmd_suppliers 오류: %s", exc)
        return format_message('error', f'공급자 목록 조회 실패: {exc}')


def cmd_supplier_score(supplier_id: str = '') -> str:
    """/supplier_score <supplier_id> — 공급자 점수 조회."""
    sid = supplier_id.strip()
    if not sid:
        return format_message('error', '사용법: /supplier_score <supplier_id>')
    try:
        from ..suppliers.scoring import SupplierScoring
        scoring = SupplierScoring()
        score = scoring.calculate_score(80, 75, 70)
        grade = scoring.get_grade(score)
        data = {'supplier_id': sid, 'score': score, 'grade': grade}
        return format_message('supplier_score', data)
    except Exception as exc:
        logger.error("cmd_supplier_score 오류: %s", exc)
        return format_message('error', f'공급자 점수 조회 실패: {exc}')


def cmd_po_create(args: str = '') -> str:
    """/po_create <supplier_id> <sku> <qty> — 발주서 생성."""
    parts = args.strip().split()
    if len(parts) < 3:
        return format_message('error', '사용법: /po_create <supplier_id> <sku> <qty>')
    supplier_id, sku = parts[0], parts[1]
    try:
        qty = int(parts[2])
    except ValueError:
        return format_message('error', f'수량은 숫자여야 합니다: {parts[2]}')
    try:
        from ..suppliers.purchase_order import PurchaseOrderManager
        manager = PurchaseOrderManager()
        order = manager.create(supplier_id, sku, qty)
        return format_message('po_create', order)
    except Exception as exc:
        logger.error("cmd_po_create 오류: %s", exc)
        return format_message('error', f'발주서 생성 실패: {exc}')


def cmd_returns() -> str:
    """/returns — 최근 반품 요청 목록."""
    try:
        from ..returns.return_manager import ReturnManager
        manager = ReturnManager()
        items = manager.list_all()
        return format_message('returns', items)
    except Exception as exc:
        logger.error("cmd_returns 오류: %s", exc)
        return format_message('error', f'반품 목록 조회 실패: {exc}')


def cmd_return_approve(return_id: str = '') -> str:
    """/return_approve <id> — 반품 요청 승인."""
    rid = return_id.strip()
    if not rid:
        return format_message('error', '사용법: /return_approve <id>')
    try:
        from ..returns.return_manager import ReturnManager
        manager = ReturnManager()
        record = manager.update_status(rid, 'approved', '봇에서 승인')
        if record is None:
            return format_message('error', f'반품 요청 없음: {rid}')
        return format_message('returns', [record], label='승인')
    except ValueError as exc:
        return format_message('error', str(exc))
    except Exception as exc:
        logger.error("cmd_return_approve 오류: %s", exc)
        return format_message('error', f'반품 승인 실패: {exc}')


def cmd_return_inspect(args: str = '') -> str:
    """/return_inspect <id> <grade> — 검수 등급 설정."""
    parts = args.strip().split()
    if len(parts) < 2:
        return format_message('error', '사용법: /return_inspect <id> <grade>')
    return_id, grade = parts[0], parts[1].upper()
    try:
        from ..returns.inspection import InspectionService
        from ..returns.return_manager import ReturnManager
        inspector = InspectionService()
        grade_info = inspector.get_grade_info(grade)
        if grade_info is None:
            return format_message('error', f'유효하지 않은 등급: {grade} (A/B/C/D)')
        manager = ReturnManager()
        record = manager.set_inspection(return_id, grade, grade_info['refund_pct'])
        if record is None:
            return format_message('error', f'반품 요청 없음: {return_id}')
        return format_message('returns', [record], label=f'검수 등급: {grade}')
    except Exception as exc:
        logger.error("cmd_return_inspect 오류: %s", exc)
        return format_message('error', f'검수 등급 설정 실패: {exc}')


def cmd_coupons() -> str:
    """/coupons — 활성 쿠폰 목록."""
    try:
        from ..coupons.coupon_manager import CouponManager
        manager = CouponManager()
        coupons = manager.list_all(active_only=True)
        return format_message('coupons', coupons)
    except Exception as exc:
        logger.error("cmd_coupons 오류: %s", exc)
        return format_message('error', f'쿠폰 목록 조회 실패: {exc}')


def cmd_coupon_create(args: str = '') -> str:
    """/coupon_create — 샘플 쿠폰 생성."""
    try:
        from ..coupons.coupon_manager import CouponManager
        from ..coupons.code_generator import CodeGenerator
        gen = CodeGenerator()
        code = gen.generate(prefix='BOT')
        manager = CouponManager()
        coupon = manager.create({
            'code': code,
            'type': 'percentage',
            'value': 10,
            'min_order_amount': 10000,
        })
        return format_message('coupons', [coupon], label='생성됨')
    except Exception as exc:
        logger.error("cmd_coupon_create 오류: %s", exc)
        return format_message('error', f'쿠폰 생성 실패: {exc}')


def cmd_coupon_validate(code: str = '') -> str:
    """/coupon_validate <code> — 쿠폰 코드 유효성 확인."""
    code = code.strip()
    if not code:
        return format_message('error', '사용법: /coupon_validate <code>')
    try:
        from ..coupons.coupon_manager import CouponManager
        manager = CouponManager()
        result = manager.validate(code)
        return format_message('coupons', [result.get('coupon')] if result.get('coupon') else [],
                              label=result.get('reason', ''))
    except Exception as exc:
        logger.error("cmd_coupon_validate 오류: %s", exc)
        return format_message('error', f'쿠폰 검증 실패: {exc}')


def cmd_categories() -> str:
    """/categories — 최상위 카테고리 목록."""
    try:
        from ..categories.category_manager import CategoryManager
        manager = CategoryManager()
        cats = manager.list_top_level()
        return format_message('categories', cats)
    except Exception as exc:
        logger.error("cmd_categories 오류: %s", exc)
        return format_message('error', f'카테고리 목록 조회 실패: {exc}')


def cmd_add_tag(args: str = '') -> str:
    """/add_tag <product_id> <tag> — 상품에 태그 추가."""
    parts = args.strip().split(None, 1)
    if len(parts) < 2:
        return format_message('error', '사용법: /add_tag <product_id> <tag>')
    product_id, tag_name = parts[0], parts[1]
    try:
        from ..categories.tag_manager import TagManager
        manager = TagManager()
        tag = manager.get_tag_by_name(tag_name) or manager.create_tag(tag_name)
        manager.add_tag_to_product(product_id, tag['id'])
        return format_message('categories', [tag], label=f'{product_id}에 태그 추가됨')
    except Exception as exc:
        logger.error("cmd_add_tag 오류: %s", exc)
        return format_message('error', f'태그 추가 실패: {exc}')


def cmd_jobs() -> str:
    """/jobs — 등록된 작업 목록."""
    try:
        from ..scheduler.job_scheduler import JobScheduler
        scheduler = JobScheduler()
        jobs = scheduler.list_all()
        return format_message('jobs', jobs)
    except Exception as exc:
        logger.error("cmd_jobs 오류: %s", exc)
        return format_message('error', f'작업 목록 조회 실패: {exc}')


def cmd_job_run(name: str = '') -> str:
    """/job_run <name> — 작업 수동 실행."""
    name = name.strip()
    if not name:
        return format_message('error', '사용법: /job_run <name>')
    try:
        from ..scheduler.job_scheduler import JobScheduler
        from ..scheduler.job_registry import JobRegistry
        registry = JobRegistry()
        func = registry.get(name)
        if func is None:
            return format_message('error', f'등록되지 않은 작업: {name}')
        scheduler = JobScheduler()
        job = scheduler.every_minutes(name, func, 60)
        result = scheduler.run_job(job['id'])
        return format_message('jobs', [result], label=name)
    except Exception as exc:
        logger.error("cmd_job_run 오류: %s", exc)
        return format_message('error', f'작업 실행 실패: {exc}')


def cmd_job_history(name: str = '') -> str:
    """/job_history <name> — 작업 실행 이력."""
    name = name.strip()
    if not name:
        return format_message('error', '사용법: /job_history <name>')
    try:
        from ..scheduler.job_history import JobHistory
        history = JobHistory()
        records = history.get_by_name(name)
        return format_message('jobs', records, label=f'{name} 이력')
    except Exception as exc:
        logger.error("cmd_job_history 오류: %s", exc)
        return format_message('error', f'작업 이력 조회 실패: {exc}')


def cmd_audit_log() -> str:
    """/audit_log — 최근 감사 로그."""
    try:
        from ..audit.audit_store import AuditStore
        store = AuditStore()
        records = store.get_recent(10)
        return format_message('audit_log', records)
    except Exception as exc:
        logger.error("cmd_audit_log 오류: %s", exc)
        return format_message('error', f'감사 로그 조회 실패: {exc}')


def cmd_audit_search(keyword: str = '') -> str:
    """/audit_search <keyword> — 감사 로그 검색."""
    keyword = keyword.strip()
    if not keyword:
        return format_message('error', '사용법: /audit_search <keyword>')
    try:
        from ..audit.audit_store import AuditStore
        from ..audit.audit_query import AuditQuery
        store = AuditStore()
        query = AuditQuery(store=store)
        results = query.search(keyword)
        return format_message('audit_log', results, label=keyword)
    except Exception as exc:
        logger.error("cmd_audit_search 오류: %s", exc)
        return format_message('error', f'감사 로그 검색 실패: {exc}')


def cmd_wishlist(user_id: str = '') -> str:
    """/wishlist — 내 위시리스트 목록."""
    user_id = user_id.strip() or 'default'
    try:
        from ..wishlist.wishlist_manager import WishlistManager
        mgr = WishlistManager()
        lists = mgr.list_wishlists(user_id)
        return format_message('wishlist', lists, label=user_id)
    except Exception as exc:
        logger.error("cmd_wishlist 오류: %s", exc)
        return format_message('error', f'위시리스트 조회 실패: {exc}')


def cmd_wish_add(product_id: str = '', user_id: str = 'default') -> str:
    """/wish_add <product_id> — 위시리스트에 상품 추가."""
    product_id = product_id.strip()
    if not product_id:
        return format_message('error', '사용법: /wish_add <product_id>')
    try:
        from ..wishlist.wishlist_manager import WishlistManager
        mgr = WishlistManager()
        lists = mgr.list_wishlists(user_id)
        if not lists:
            wl = mgr.create_wishlist(user_id, '기본')
        else:
            wl = lists[0]
        item = mgr.add_item(wl['id'], product_id)
        return format_message('wishlist', [item], label=f'추가됨: {product_id}')
    except Exception as exc:
        logger.error("cmd_wish_add 오류: %s", exc)
        return format_message('error', f'위시리스트 추가 실패: {exc}')


def cmd_wish_watch(product_id: str = '', target_price: str = '') -> str:
    """/wish_watch <product_id> <target_price> — 가격 감시 등록."""
    product_id = product_id.strip()
    target_price = target_price.strip()
    if not product_id or not target_price:
        return format_message('error', '사용법: /wish_watch <product_id> <target_price>')
    try:
        from ..wishlist.price_watch import PriceWatch
        pw = PriceWatch()
        watch = pw.watch('default', product_id, float(target_price))
        return format_message('wishlist', [watch], label=f'가격 감시: {product_id}')
    except Exception as exc:
        logger.error("cmd_wish_watch 오류: %s", exc)
        return format_message('error', f'가격 감시 등록 실패: {exc}')


def cmd_bundles() -> str:
    """/bundles — 번들 목록."""
    try:
        from ..bundles.bundle_manager import BundleManager
        mgr = BundleManager()
        bundles = mgr.list_all(status='active')
        return format_message('bundles', bundles)
    except Exception as exc:
        logger.error("cmd_bundles 오류: %s", exc)
        return format_message('error', f'번들 목록 조회 실패: {exc}')


def cmd_bundle_create(name: str = '', bundle_type: str = 'fixed') -> str:
    """/bundle_create [name] — 번들 생성."""
    name = name.strip() or '새 번들'
    try:
        from ..bundles.bundle_manager import BundleManager
        mgr = BundleManager()
        bundle = mgr.create({'name': name, 'type': bundle_type})
        return format_message('bundles', [bundle], label='생성됨')
    except Exception as exc:
        logger.error("cmd_bundle_create 오류: %s", exc)
        return format_message('error', f'번들 생성 실패: {exc}')


def cmd_bundle_price(bundle_id: str = '') -> str:
    """/bundle_price <bundle_id> — 번들 가격 조회."""
    bundle_id = bundle_id.strip()
    if not bundle_id:
        return format_message('error', '사용법: /bundle_price <bundle_id>')
    try:
        from ..bundles.bundle_manager import BundleManager
        from ..bundles.pricing import BundlePricing
        mgr = BundleManager()
        bundle = mgr.get(bundle_id)
        if bundle is None:
            return format_message('error', f'번들 없음: {bundle_id}')
        pricing = BundlePricing()
        result = pricing.calculate(bundle.get('items', []))
        return format_message('bundles', [result], label=bundle_id)
    except Exception as exc:
        logger.error("cmd_bundle_price 오류: %s", exc)
        return format_message('error', f'번들 가격 조회 실패: {exc}')


def cmd_convert(amount: str = '', from_currency: str = 'USD', to_currency: str = 'KRW') -> str:
    """/convert <amount> <from> <to> — 통화 변환."""
    amount = amount.strip()
    if not amount:
        return format_message('error', '사용법: /convert <amount> <from> <to>')
    try:
        from ..multicurrency.conversion import CurrencyConverter
        from ..multicurrency.display import CurrencyDisplay
        converter = CurrencyConverter()
        display = CurrencyDisplay()
        result = converter.convert(float(amount), from_currency, to_currency)
        formatted = display.format(result, to_currency)
        return format_message('currency', {
            'amount': amount,
            'from': from_currency,
            'to': to_currency,
            'result': result,
            'formatted': formatted,
        })
    except Exception as exc:
        logger.error("cmd_convert 오류: %s", exc)
        return format_message('error', f'통화 변환 실패: {exc}')


def cmd_payment_status(payment_id: str = '') -> str:
    """/payment_status <payment_id> — 결제 상태 조회."""
    payment_id = payment_id.strip()
    if not payment_id:
        return format_message('error', '사용법: /payment_status <payment_id>')
    try:
        return format_message('payment_status', {'payment_id': payment_id, 'status': 'unknown'})
    except Exception as exc:
        logger.error("cmd_payment_status 오류: %s", exc)
        return format_message('error', f'결제 상태 조회 실패: {exc}')


def cmd_images(product_id: str = '') -> str:
    """/images <product_id> — 상품 이미지 갤러리."""
    product_id = product_id.strip()
    if not product_id:
        return format_message('error', '사용법: /images <product_id>')
    try:
        from ..images.image_manager import ImageManager
        mgr = ImageManager()
        images = mgr.list_all(product_id=product_id)
        return format_message('images', images, label=product_id)
    except Exception as exc:
        logger.error("cmd_images 오류: %s", exc)
        return format_message('error', f'이미지 목록 조회 실패: {exc}')


def cmd_image_upload(product_id: str = '', url: str = '') -> str:
    """/image_upload <product_id> <url> — 이미지 등록."""
    product_id = product_id.strip()
    url = url.strip()
    if not product_id or not url:
        return format_message('error', '사용법: /image_upload <product_id> <url>')
    try:
        from ..images.image_manager import ImageManager
        mgr = ImageManager()
        image = mgr.register(url, product_id=product_id)
        return format_message('images', [image], label=f'등록됨: {product_id}')
    except Exception as exc:
        logger.error("cmd_image_upload 오류: %s", exc)
        return format_message('error', f'이미지 등록 실패: {exc}')


def cmd_profile(user_id: str = '') -> str:
    """/profile — 내 프로필."""
    user_id = user_id.strip() or 'default'
    try:
        from ..users.user_manager import UserManager
        mgr = UserManager()
        user = mgr.get(user_id)
        if user is None:
            return format_message('error', f'사용자 없음: {user_id}')
        return format_message('user_profile', user)
    except Exception as exc:
        logger.error("cmd_profile 오류: %s", exc)
        return format_message('error', f'프로필 조회 실패: {exc}')


def cmd_address_add(user_id: str = 'default', **kwargs) -> str:
    """/address_add — 배송지 추가."""
    try:
        from ..users.address_book import AddressBook
        book = AddressBook()
        address = book.add(user_id, kwargs)
        return format_message('user_addresses', [address], label='추가됨')
    except Exception as exc:
        logger.error("cmd_address_add 오류: %s", exc)
        return format_message('error', f'배송지 추가 실패: {exc}')


def cmd_my_activity(user_id: str = '') -> str:
    """/my_activity — 최근 활동 로그."""
    user_id = user_id.strip() or 'default'
    try:
        from ..users.activity_log import ActivityLog
        log = ActivityLog()
        records = log.get_recent(user_id, n=10)
        return format_message('user_activity', records, label=user_id)
    except Exception as exc:
        logger.error("cmd_my_activity 오류: %s", exc)
        return format_message('error', f'활동 로그 조회 실패: {exc}')


def cmd_search(keyword: str = '') -> str:
    """/search <keyword> — 상품/문서 검색."""
    keyword = keyword.strip()
    if not keyword:
        return format_message('error', '사용법: /search <keyword>')
    try:
        from ..search.search_engine import SearchEngine
        from ..search.autocomplete import Autocomplete
        engine = SearchEngine()
        ac = Autocomplete()
        ac.record_query(keyword)
        results = engine.search(keyword, limit=10)
        return format_message('search_results', results, label=keyword)
    except Exception as exc:
        logger.error("cmd_search 오류: %s", exc)
        return format_message('error', f'검색 실패: {exc}')


def cmd_popular_searches() -> str:
    """/popular_searches — 인기 검색어."""
    try:
        from ..search.search_analytics import SearchAnalytics
        analytics = SearchAnalytics()
        popular = analytics.get_popular_queries()
        return format_message('popular_searches', popular)
    except Exception as exc:
        logger.error("cmd_popular_searches 오류: %s", exc)
        return format_message('error', f'인기 검색어 조회 실패: {exc}')


# ─────────────────────────────────────────────────────────────
# Phase 49: 멀티테넌시
# ─────────────────────────────────────────────────────────────

def cmd_tenant_info(tenant_id: str = '') -> str:
    """/tenant_info [tenant_id] — 테넌트 정보."""
    tenant_id = tenant_id.strip()
    try:
        from ..tenancy.tenant_manager import TenantManager
        from ..tenancy.tenant_config import TenantConfig
        mgr = TenantManager()
        cfg = TenantConfig()
        if tenant_id:
            tenant = mgr.get(tenant_id)
            if tenant is None:
                return format_message('error', f'테넌트 없음: {tenant_id}')
            config = cfg.get(tenant_id)
            return format_message('tenant_info', {'tenant': tenant, 'config': config})
        else:
            tenants = mgr.list(active_only=True)
            return format_message('tenant_info', {'tenants': tenants})
    except Exception as exc:
        logger.error("cmd_tenant_info 오류: %s", exc)
        return format_message('error', f'테넌트 정보 조회 실패: {exc}')


def cmd_tenant_usage(tenant_id: str = '') -> str:
    """/tenant_usage [tenant_id] — 테넌트 사용량."""
    tenant_id = tenant_id.strip()
    try:
        from ..tenancy.usage_tracker import UsageTracker
        tracker = UsageTracker()
        if tenant_id:
            usage = tracker.get(tenant_id)
            return format_message('tenant_usage', usage, label=tenant_id)
        else:
            summary = tracker.summary()
            return format_message('tenant_usage', summary, label='전체')
    except Exception as exc:
        logger.error("cmd_tenant_usage 오류: %s", exc)
        return format_message('error', f'테넌트 사용량 조회 실패: {exc}')


# ─────────────────────────────────────────────────────────────
# Phase 50: A/B 테스트 엔진
# ─────────────────────────────────────────────────────────────

def cmd_experiment_list() -> str:
    """/experiment_list — 실험 목록."""
    try:
        from ..ab_testing.experiment_manager import ExperimentManager
        mgr = ExperimentManager()
        experiments = mgr.list()
        return format_message('experiment_list', experiments)
    except Exception as exc:
        logger.error("cmd_experiment_list 오류: %s", exc)
        return format_message('error', f'실험 목록 조회 실패: {exc}')


def cmd_experiment_result(experiment_id: str = '') -> str:
    """/experiment_result <id> — 실험 결과."""
    experiment_id = experiment_id.strip()
    if not experiment_id:
        return format_message('error', '사용법: /experiment_result <experiment_id>')
    try:
        from ..ab_testing.experiment_manager import ExperimentManager
        from ..ab_testing.metrics_tracker import MetricsTracker
        from ..ab_testing.statistical_analyzer import StatisticalAnalyzer
        from ..ab_testing.experiment_report import ExperimentReport
        mgr = ExperimentManager()
        exp = mgr.get(experiment_id)
        if exp is None:
            return format_message('error', f'실험 없음: {experiment_id}')
        tracker = MetricsTracker()
        metrics = tracker.get_metrics(experiment_id)
        reporter = ExperimentReport()
        report = reporter.generate(exp, metrics)
        return format_message('experiment_result', report)
    except Exception as exc:
        logger.error("cmd_experiment_result 오류: %s", exc)
        return format_message('error', f'실험 결과 조회 실패: {exc}')


# ─────────────────────────────────────────────────────────────
# Phase 51: 웹훅 관리
# ─────────────────────────────────────────────────────────────

def cmd_webhook_list() -> str:
    """/webhook_list — 웹훅 목록."""
    try:
        from ..webhook_manager.webhook_registry import WebhookRegistry
        registry = WebhookRegistry()
        webhooks = registry.list()
        return format_message('webhook_list', webhooks)
    except Exception as exc:
        logger.error("cmd_webhook_list 오류: %s", exc)
        return format_message('error', f'웹훅 목록 조회 실패: {exc}')


def cmd_webhook_test(webhook_id: str = '') -> str:
    """/webhook_test <id> — 웹훅 테스트."""
    webhook_id = webhook_id.strip()
    if not webhook_id:
        return format_message('error', '사용법: /webhook_test <webhook_id>')
    try:
        from ..webhook_manager.webhook_registry import WebhookRegistry
        from ..webhook_manager.webhook_dispatcher import WebhookDispatcher
        registry = WebhookRegistry()
        dispatcher = WebhookDispatcher(registry=registry)
        result = dispatcher.test_webhook(webhook_id)
        return format_message('webhook_test', result, label=webhook_id)
    except KeyError:
        return format_message('error', f'웹훅 없음: {webhook_id}')
    except Exception as exc:
        logger.error("cmd_webhook_test 오류: %s", exc)
        return format_message('error', f'웹훅 테스트 실패: {exc}')


# ─────────────────────────────────────────────────────────────
# Phase 54: 성능 벤치마크
# ─────────────────────────────────────────────────────────────

def cmd_benchmark_run(url: str = '') -> str:
    """/benchmark_run [url] — 벤치마크 실행 (모의)."""
    url = url.strip() or 'http://localhost:8000/health'
    try:
        from ..benchmark.load_profile import LoadProfile
        from ..benchmark.benchmark_runner import BenchmarkRunner
        from ..benchmark.benchmark_report import BenchmarkReport
        profile = LoadProfile(name='bot_benchmark', concurrent_users=5,
                              duration_seconds=1, target_url=url)
        runner = BenchmarkRunner()
        report = runner.run_mock(profile)
        reporter = BenchmarkReport()
        return format_message('benchmark_result', report, label=url)
    except Exception as exc:
        logger.error("cmd_benchmark_run 오류: %s", exc)
        return format_message('error', f'벤치마크 실행 실패: {exc}')


def cmd_benchmark_results() -> str:
    """/benchmark_results — 벤치마크 결과 목록."""
    try:
        from ..benchmark.regression_detector import RegressionDetector
        detector = RegressionDetector()
        history = detector.get_history()
        return format_message('benchmark_results', history)
    except Exception as exc:
        logger.error("cmd_benchmark_results 오류: %s", exc)
        return format_message('error', f'벤치마크 결과 조회 실패: {exc}')


# ─────────────────────────────────────────────────────────────
# Phase 55: 파일 스토리지
# ─────────────────────────────────────────────────────────────

def cmd_storage_usage(owner_id: str = '') -> str:
    """/storage_usage [owner_id] — 스토리지 사용량."""
    owner_id = owner_id.strip() or 'default'
    try:
        from ..storage.storage_quota import StorageQuota
        quota = StorageQuota()
        summary = quota.get_summary(owner_id)
        return format_message('storage_usage', summary)
    except Exception as exc:
        logger.error("cmd_storage_usage 오류: %s", exc)
        return format_message('error', f'스토리지 사용량 조회 실패: {exc}')


def cmd_storage_quota(owner_id: str = '', quota_mb: str = '') -> str:
    """/storage_quota [owner_id] [quota_mb] — 스토리지 할당량 설정/조회."""
    owner_id = owner_id.strip() or 'default'
    try:
        from ..storage.storage_quota import StorageQuota
        quota = StorageQuota()
        if quota_mb.strip():
            bytes_limit = int(quota_mb.strip()) * 1024 * 1024
            quota.set_quota(owner_id, bytes_limit)
        summary = quota.get_summary(owner_id)
        return format_message('storage_quota', summary)
    except Exception as exc:
        logger.error("cmd_storage_quota 오류: %s", exc)
        return format_message('error', f'스토리지 할당량 설정 실패: {exc}')


# ─────────────────────────────────────────────────────────────
# Phase 56: 이메일 서비스
# ─────────────────────────────────────────────────────────────

def cmd_email_stats() -> str:
    """/email_stats — 이메일 발송 통계."""
    try:
        from ..email_service.email_tracker import EmailTracker
        tracker = EmailTracker()
        stats = tracker.get_stats()
        return format_message('email_stats', stats)
    except Exception as exc:
        logger.error("cmd_email_stats 오류: %s", exc)
        return format_message('error', f'이메일 통계 조회 실패: {exc}')


def cmd_email_send(to: str = '', template: str = '') -> str:
    """/email_send <to> <template> — 이메일 발송."""
    to = to.strip()
    template = template.strip() or 'order_confirm'
    if not to:
        return format_message('error', '사용법: /email_send <to> <template>')
    try:
        from ..email_service.smtp_provider import SMTPProvider
        from ..email_service.email_queue import EmailQueue
        provider = SMTPProvider()
        queue = EmailQueue()
        email_id = queue.enqueue(to, template, {'name': '사용자', 'order_id': 'ORD-001', 'total': '0'})
        results = queue.process_queue(provider)
        return format_message('email_send', {'email_id': email_id, 'results': results})
    except Exception as exc:
        logger.error("cmd_email_send 오류: %s", exc)
        return format_message('error', f'이메일 발송 실패: {exc}')


# ─────────────────────────────────────────────────────────────
# Phase 57: 검색 엔진
# ─────────────────────────────────────────────────────────────

def cmd_search_popular() -> str:
    """/search_popular — 인기 검색어 조회."""
    try:
        from ..search.search_analytics import SearchAnalytics
        analytics = SearchAnalytics()
        popular = analytics.get_popular_queries(limit=5)
        return format_message('search_popular', popular)
    except Exception as exc:
        logger.error("cmd_search_popular 오류: %s", exc)
        return format_message('error', f'인기 검색어 조회 실패: {exc}')


# ─────────────────────────────────────────────────────────────
# Phase 58: 작업 파이프라인
# ─────────────────────────────────────────────────────────────

def cmd_pipeline_run(name: str = '') -> str:
    """/pipeline_run <name> — 파이프라인 실행."""
    name = name.strip() or 'default'
    try:
        from ..pipeline.pipeline_builder import PipelineBuilder
        from ..pipeline.pipeline_executor import PipelineExecutor
        from ..pipeline.stages.collect_stage import CollectStage
        from ..pipeline.stages.translate_stage import TranslateStage
        builder = PipelineBuilder(name=name)
        builder.add_stage(CollectStage()).add_stage(TranslateStage())
        pipeline = builder.build()
        executor = PipelineExecutor()
        results = executor.execute(pipeline, {})
        return format_message('pipeline_run', {'name': name, 'results': {k: v.to_dict() for k, v in results.items()}})
    except Exception as exc:
        logger.error("cmd_pipeline_run 오류: %s", exc)
        return format_message('error', f'파이프라인 실행 실패: {exc}')


def cmd_pipeline_status() -> str:
    """/pipeline_status — 파이프라인 상태 조회."""
    try:
        from ..pipeline.pipeline_monitor import PipelineMonitor
        monitor = PipelineMonitor()
        stats = monitor.get_all_stats()
        return format_message('pipeline_status', stats)
    except Exception as exc:
        logger.error("cmd_pipeline_status 오류: %s", exc)
        return format_message('error', f'파이프라인 상태 조회 실패: {exc}')


# ─────────────────────────────────────────────────────────────
# Phase 59: 피쳐 플래그
# ─────────────────────────────────────────────────────────────

def cmd_flag_list() -> str:
    """/flag_list — 피쳐 플래그 목록."""
    try:
        from ..feature_flags.feature_flag_manager import FeatureFlagManager
        manager = FeatureFlagManager()
        flags = manager.list_flags()
        return format_message('flag_list', flags)
    except Exception as exc:
        logger.error("cmd_flag_list 오류: %s", exc)
        return format_message('error', f'플래그 목록 조회 실패: {exc}')


def cmd_flag_toggle(name: str = '') -> str:
    """/flag_toggle <name> — 피쳐 플래그 토글."""
    name = name.strip()
    if not name:
        return format_message('error', '사용법: /flag_toggle <name>')
    try:
        from ..feature_flags.feature_flag_manager import FeatureFlagManager
        manager = FeatureFlagManager()
        try:
            flag = manager.get_flag(name)
            if flag is None:
                flag = manager.create_flag(name, enabled=True)
            else:
                flag = manager.update_flag(name, enabled=not flag.get('enabled', False))
        except KeyError:
            flag = manager.create_flag(name, enabled=True)
        return format_message('flag_toggle', flag)
    except Exception as exc:
        logger.error("cmd_flag_toggle 오류: %s", exc)
        return format_message('error', f'플래그 토글 실패: {exc}')


# ─────────────────────────────────────────────────────────────
# Phase 60: 외부 연동
# ─────────────────────────────────────────────────────────────

def cmd_integration_list() -> str:
    """/integration_list — 연동 목록."""
    try:
        from ..integrations.integration_registry import IntegrationRegistry
        from ..integrations.slack_connector import SlackConnector
        from ..integrations.google_sheets_connector import GoogleSheetsConnector
        from ..integrations.shopify_connector import ShopifyConnector
        registry = IntegrationRegistry()
        for c in [SlackConnector(), GoogleSheetsConnector(), ShopifyConnector()]:
            registry.register(c)
        return format_message('integration_list', {'integrations': registry.list_all()})
    except Exception as exc:
        logger.error("cmd_integration_list 오류: %s", exc)
        return format_message('error', f'연동 목록 조회 실패: {exc}')


def cmd_integration_sync(name: str = '') -> str:
    """/integration_sync <name> — 연동 동기화."""
    name = name.strip()
    if not name:
        return format_message('error', '사용법: /integration_sync <name>')
    try:
        from ..integrations.integration_registry import IntegrationRegistry
        from ..integrations.slack_connector import SlackConnector
        from ..integrations.google_sheets_connector import GoogleSheetsConnector
        from ..integrations.shopify_connector import ShopifyConnector
        registry = IntegrationRegistry()
        for c in [SlackConnector(), GoogleSheetsConnector(), ShopifyConnector()]:
            registry.register(c)
        connector = registry.get(name)
        if connector is None:
            return format_message('error', f'연동 없음: {name}')
        result = connector.sync()
        return format_message('integration_sync', {'name': name, 'result': result})
    except Exception as exc:
        logger.error("cmd_integration_sync 오류: %s", exc)
        return format_message('error', f'연동 동기화 실패: {exc}')


# ─────────────────────────────────────────────────────────────
# Phase 61: 백업/복원
# ─────────────────────────────────────────────────────────────

def cmd_backup_create() -> str:
    """/backup_create — 백업 생성."""
    try:
        from ..backup.backup_manager import BackupManager
        from ..backup.full_backup import FullBackup
        manager = BackupManager()
        entry = manager.create({"timestamp": "now"}, strategy=FullBackup())
        return format_message('backup_create', entry)
    except Exception as exc:
        logger.error("cmd_backup_create 오류: %s", exc)
        return format_message('error', f'백업 생성 실패: {exc}')


def cmd_backup_list() -> str:
    """/backup_list — 백업 목록."""
    try:
        from ..backup.backup_manager import BackupManager
        manager = BackupManager()
        backups = manager.list_backups()
        return format_message('backup_list', backups)
    except Exception as exc:
        logger.error("cmd_backup_list 오류: %s", exc)
        return format_message('error', f'백업 목록 조회 실패: {exc}')


def cmd_backup_restore(backup_id: str = '') -> str:
    """/backup_restore <id> — 백업 복원."""
    backup_id = backup_id.strip()
    if not backup_id:
        return format_message('error', '사용법: /backup_restore <id>')
    try:
        from ..backup.backup_manager import BackupManager
        manager = BackupManager()
        restored = manager.restore(backup_id)
        return format_message('backup_restore', {'backup_id': backup_id, 'restored': restored})
    except KeyError:
        return format_message('error', f'백업 없음: {backup_id}')
    except Exception as exc:
        logger.error("cmd_backup_restore 오류: %s", exc)
        return format_message('error', f'백업 복원 실패: {exc}')


# ─────────────────────────────────────────────────────────────
# Phase 62: 레이트 리미팅
# ─────────────────────────────────────────────────────────────

def cmd_ratelimit_status() -> str:
    """/ratelimit_status — 레이트 리밋 상태."""
    try:
        from ..rate_limiting.rate_limit_policy import RateLimitPolicy
        from ..rate_limiting.sliding_window_limiter import SlidingWindowLimiter
        from ..rate_limiting.rate_limit_dashboard import RateLimitDashboard
        policy = RateLimitPolicy()
        limiter = SlidingWindowLimiter()
        dashboard = RateLimitDashboard(limiter=limiter, policy=policy)
        stats = dashboard.get_stats()
        return format_message('ratelimit_status', stats)
    except Exception as exc:
        logger.error("cmd_ratelimit_status 오류: %s", exc)
        return format_message('error', f'레이트 리밋 상태 조회 실패: {exc}')


def cmd_ratelimit_policy(endpoint: str = '') -> str:
    """/ratelimit_policy <endpoint> — 레이트 리밋 정책 조회."""
    endpoint = endpoint.strip()
    try:
        from ..rate_limiting.rate_limit_policy import RateLimitPolicy
        policy = RateLimitPolicy()
        if endpoint:
            p = policy.get_policy(endpoint)
            return format_message('ratelimit_policy', p or {'endpoint': endpoint, 'error': '정책 없음'})
        return format_message('ratelimit_policy', {'policies': policy.list_policies()})
    except Exception as exc:
        logger.error("cmd_ratelimit_policy 오류: %s", exc)
        return format_message('error', f'레이트 리밋 정책 조회 실패: {exc}')


# ─────────────────────────────────────────────────────────────
# Phase 63: CMS
# ─────────────────────────────────────────────────────────────

def cmd_cms_list() -> str:
    """/cms_list — CMS 콘텐츠 목록."""
    try:
        from ..cms.content_manager import ContentManager
        manager = ContentManager()
        items = manager.list_all()
        return format_message('cms_list', items)
    except Exception as exc:
        logger.error("cmd_cms_list 오류: %s", exc)
        return format_message('error', f'CMS 목록 조회 실패: {exc}')


def cmd_cms_publish(content_id: str = '') -> str:
    """/cms_publish <id> — 콘텐츠 발행."""
    content_id = content_id.strip()
    if not content_id:
        return format_message('error', '사용법: /cms_publish <id>')
    try:
        from ..cms.content_manager import ContentManager
        from ..cms.content_publisher import ContentPublisher
        manager = ContentManager()
        publisher = ContentPublisher(manager=manager)
        result = publisher.publish(content_id)
        return format_message('cms_publish', result)
    except KeyError:
        return format_message('error', f'콘텐츠 없음: {content_id}')
    except Exception as exc:
        logger.error("cmd_cms_publish 오류: %s", exc)
        return format_message('error', f'콘텐츠 발행 실패: {exc}')


def cmd_cms_draft(content_id: str = '') -> str:
    """/cms_draft <id> — 콘텐츠 초안으로 전환."""
    content_id = content_id.strip()
    if not content_id:
        return format_message('error', '사용법: /cms_draft <id>')
    try:
        from ..cms.content_manager import ContentManager
        from ..cms.content_publisher import ContentPublisher
        manager = ContentManager()
        publisher = ContentPublisher(manager=manager)
        result = publisher.unpublish(content_id)
        return format_message('cms_draft', result)
    except KeyError:
        return format_message('error', f'콘텐츠 없음: {content_id}')
    except Exception as exc:
        logger.error("cmd_cms_draft 오류: %s", exc)
        return format_message('error', f'콘텐츠 초안 전환 실패: {exc}')


# ─────────────────────────────────────────────────────────────
# Phase 64: 이벤트 소싱
# ─────────────────────────────────────────────────────────────

def cmd_events_recent() -> str:
    """/events_recent — 최근 이벤트 목록."""
    try:
        from ..event_sourcing.event_store import EventStore
        store = EventStore()
        events = store.get_all()[-10:]
        return format_message('events_recent', [e.to_dict() for e in events])
    except Exception as exc:
        logger.error("cmd_events_recent 오류: %s", exc)
        return format_message('error', f'이벤트 조회 실패: {exc}')


def cmd_events_replay(aggregate_id: str = '') -> str:
    """/events_replay <aggregate_id> — 이벤트 리플레이."""
    aggregate_id = aggregate_id.strip()
    if not aggregate_id:
        return format_message('error', '사용법: /events_replay <aggregate_id>')
    try:
        from ..event_sourcing.event_store import EventStore
        from ..event_sourcing.event_replay import EventReplay
        store = EventStore()
        replay = EventReplay()
        events = store.get_events(aggregate_id)
        replayed = replay.replay(events)
        return format_message('events_replay', {
            'aggregate_id': aggregate_id,
            'events': [e.to_dict() for e in replayed],
        })
    except Exception as exc:
        logger.error("cmd_events_replay 오류: %s", exc)
        return format_message('error', f'이벤트 리플레이 실패: {exc}')


# ─────────────────────────────────────────────────────────────
# Phase 65: 캐시 계층
# ─────────────────────────────────────────────────────────────

def cmd_cache_stats() -> str:
    """/cache_stats — 캐시 통계."""
    try:
        from ..cache_layer.cache_stats import CacheStats
        stats = CacheStats()
        return format_message('cache_stats', stats.get_stats())
    except Exception as exc:
        logger.error("cmd_cache_stats 오류: %s", exc)
        return format_message('error', f'캐시 통계 조회 실패: {exc}')


def cmd_cache_clear(pattern: str = '') -> str:
    """/cache_clear [pattern] — 캐시 초기화."""
    try:
        from ..cache_layer.cache_manager import CacheManager
        from ..cache_layer.cache_invalidator import CacheInvalidator
        manager = CacheManager()
        if pattern.strip():
            invalidator = CacheInvalidator(manager)
            count = invalidator.invalidate_by_pattern(pattern.strip())
            return format_message('cache_clear', {'pattern': pattern, 'invalidated': count})
        manager.clear()
        return format_message('cache_clear', {'pattern': '*', 'invalidated': -1})
    except Exception as exc:
        logger.error("cmd_cache_clear 오류: %s", exc)
        return format_message('error', f'캐시 초기화 실패: {exc}')


# ─────────────────────────────────────────────────────────────
# Phase 66: 워크플로 엔진
# ─────────────────────────────────────────────────────────────

def cmd_workflow_list() -> str:
    """/workflow_list — 워크플로 목록."""
    try:
        from ..workflow.workflow_engine import WorkflowEngine
        from ..workflow.workflows.order_workflow import OrderWorkflow
        from ..workflow.workflows.return_workflow import ReturnWorkflow
        engine = WorkflowEngine()
        engine.register(OrderWorkflow.build())
        engine.register(ReturnWorkflow.build())
        return format_message('workflow_list', engine.list_definitions())
    except Exception as exc:
        logger.error("cmd_workflow_list 오류: %s", exc)
        return format_message('error', f'워크플로 목록 조회 실패: {exc}')


def cmd_workflow_start(name: str = '') -> str:
    """/workflow_start <name> — 워크플로 시작."""
    name = name.strip()
    if not name:
        return format_message('error', '사용법: /workflow_start <name>')
    try:
        from ..workflow.workflow_engine import WorkflowEngine
        from ..workflow.workflows.order_workflow import OrderWorkflow
        from ..workflow.workflows.return_workflow import ReturnWorkflow
        engine = WorkflowEngine()
        engine.register(OrderWorkflow.build())
        engine.register(ReturnWorkflow.build())
        instance = engine.start(name)
        return format_message('workflow_start', instance.to_dict())
    except KeyError:
        return format_message('error', f'워크플로 없음: {name}')
    except Exception as exc:
        logger.error("cmd_workflow_start 오류: %s", exc)
        return format_message('error', f'워크플로 시작 실패: {exc}')


def cmd_workflow_status(instance_id: str = '') -> str:
    """/workflow_status <instance_id> — 워크플로 상태."""
    instance_id = instance_id.strip()
    if not instance_id:
        return format_message('error', '사용법: /workflow_status <instance_id>')
    try:
        from ..workflow.workflow_engine import WorkflowEngine
        engine = WorkflowEngine()
        status_data = engine.get_status(instance_id)
        if status_data is None:
            return format_message('error', f'인스턴스 없음: {instance_id}')
        return format_message('workflow_status', status_data)
    except Exception as exc:
        logger.error("cmd_workflow_status 오류: %s", exc)
        return format_message('error', f'워크플로 상태 조회 실패: {exc}')


# ─────────────────────────────────────────────────────────────
# Phase 67: 실시간 대시보드 커맨드
# ─────────────────────────────────────────────────────────────

def cmd_realtime_status() -> str:
    """/realtime_status — 실시간 연결 상태."""
    try:
        from ..realtime.connection_manager import ConnectionManager
        mgr = ConnectionManager()
        return format_message('realtime_status', mgr.get_stats())
    except Exception as exc:
        logger.error("cmd_realtime_status 오류: %s", exc)
        return format_message('error', f'실시간 상태 조회 실패: {exc}')


def cmd_realtime_metrics() -> str:
    """/realtime_metrics — 실시간 대시보드 메트릭."""
    try:
        from ..realtime.dashboard_metrics import DashboardMetrics
        metrics = DashboardMetrics()
        return format_message('realtime_metrics', metrics.collect())
    except Exception as exc:
        logger.error("cmd_realtime_metrics 오류: %s", exc)
        return format_message('error', f'실시간 메트릭 조회 실패: {exc}')


# ─────────────────────────────────────────────────────────────
# Phase 68: 데이터 교환 커맨드
# ─────────────────────────────────────────────────────────────

def cmd_export(type_: str = '', format_: str = '') -> str:
    """/export <type> <format> — 데이터 내보내기."""
    type_ = type_.strip() or 'orders'
    format_ = format_.strip() or 'json'
    try:
        from ..data_exchange.export_manager import ExportManager
        mgr = ExportManager()
        result = mgr.export([], format_=format_)
        return format_message('export', result)
    except Exception as exc:
        logger.error("cmd_export 오류: %s", exc)
        return format_message('error', f'내보내기 실패: {exc}')


def cmd_import_status() -> str:
    """/import_status — 가져오기 현황."""
    try:
        from ..data_exchange.bulk_operation import BulkOperation
        bulk = BulkOperation()
        return format_message('import_status', bulk.list_jobs())
    except Exception as exc:
        logger.error("cmd_import_status 오류: %s", exc)
        return format_message('error', f'가져오기 현황 조회 실패: {exc}')


# ─────────────────────────────────────────────────────────────
# Phase 69: 규칙 엔진 커맨드
# ─────────────────────────────────────────────────────────────

def cmd_rules_list() -> str:
    """/rules_list — 규칙 목록."""
    try:
        from ..rules_engine.rules_engine import RulesEngine
        engine = RulesEngine()
        return format_message('rules_list', engine.list_rules())
    except Exception as exc:
        logger.error("cmd_rules_list 오류: %s", exc)
        return format_message('error', f'규칙 목록 조회 실패: {exc}')


def cmd_rules_test(rule_id: str = '', data_json: str = '') -> str:
    """/rules_test <rule_id> <data_json> — 규칙 테스트."""
    rule_id = rule_id.strip()
    if not rule_id:
        return format_message('error', '사용법: /rules_test <rule_id> [data_json]')
    try:
        import json
        from ..rules_engine.rules_engine import RulesEngine
        engine = RulesEngine()
        context = json.loads(data_json) if data_json.strip() else {}
        result = engine.evaluate('default', context)
        return format_message('rules_test', {'rule_id': rule_id, 'results': result})
    except Exception as exc:
        logger.error("cmd_rules_test 오류: %s", exc)
        return format_message('error', f'규칙 테스트 실패: {exc}')


# ─────────────────────────────────────────────────────────────
# Phase 70: KPI 커맨드
# ─────────────────────────────────────────────────────────────

def cmd_kpi_summary() -> str:
    """/kpi_summary — KPI 전체 요약."""
    try:
        from ..kpi.kpi_manager import KPIManager
        mgr = KPIManager()
        data = mgr.calculate_all({})
        return format_message('kpi_summary', data)
    except Exception as exc:
        logger.error("cmd_kpi_summary 오류: %s", exc)
        return format_message('error', f'KPI 요약 조회 실패: {exc}')


def cmd_kpi_detail(name: str = '') -> str:
    """/kpi_detail <name> — KPI 상세."""
    name = name.strip()
    if not name:
        return format_message('error', '사용법: /kpi_detail <name>')
    try:
        from ..kpi.kpi_manager import KPIManager
        mgr = KPIManager()
        kpi = mgr.get(name)
        if kpi is None:
            return format_message('error', f'KPI 없음: {name}')
        return format_message('kpi_detail', kpi.to_dict())
    except Exception as exc:
        logger.error("cmd_kpi_detail 오류: %s", exc)
        return format_message('error', f'KPI 상세 조회 실패: {exc}')


def cmd_kpi_alerts() -> str:
    """/kpi_alerts — KPI 알림 목록."""
    try:
        from ..kpi.kpi_alert import KPIAlert
        alert = KPIAlert()
        return format_message('kpi_alerts', alert.get_alerts())
    except Exception as exc:
        logger.error("cmd_kpi_alerts 오류: %s", exc)
        return format_message('error', f'KPI 알림 조회 실패: {exc}')


# ─────────────────────────────────────────────────────────────
# Phase 71: 마켓플레이스 동기화 커맨드
# ─────────────────────────────────────────────────────────────

def cmd_sync_marketplace(name: str = '') -> str:
    """/sync_marketplace <name> — 마켓플레이스 동기화."""
    name = name.strip() or 'coupang'
    try:
        from ..marketplace_sync.sync_manager import MarketplaceSyncManager
        mgr = MarketplaceSyncManager()
        job = mgr.sync(name)
        return format_message('sync_marketplace', job.to_dict())
    except Exception as exc:
        logger.error("cmd_sync_marketplace 오류: %s", exc)
        return format_message('error', f'마켓플레이스 동기화 실패: {exc}')


def cmd_sync_status() -> str:
    """/sync_status — 동기화 현황."""
    try:
        from ..marketplace_sync.sync_manager import MarketplaceSyncManager
        mgr = MarketplaceSyncManager()
        return format_message('sync_status', mgr.get_status())
    except Exception as exc:
        logger.error("cmd_sync_status 오류: %s", exc)
        return format_message('error', f'동기화 현황 조회 실패: {exc}')


def cmd_sync_logs() -> str:
    """/sync_logs — 동기화 로그."""
    try:
        from ..marketplace_sync.sync_log import SyncLog
        log = SyncLog()
        return format_message('sync_logs', log.get_summary())
    except Exception as exc:
        logger.error("cmd_sync_logs 오류: %s", exc)
        return format_message('error', f'동기화 로그 조회 실패: {exc}')


# ─────────────────────────────────────────────────────────────
# Phase 72: 보안 강화 커맨드
# ─────────────────────────────────────────────────────────────

def cmd_security_audit() -> str:
    """/security_audit — 보안 감사 로그."""
    try:
        from ..security.security_audit import SecurityAudit
        audit = SecurityAudit()
        return format_message('security_audit', audit.get_logs())
    except Exception as exc:
        logger.error("cmd_security_audit 오류: %s", exc)
        return format_message('error', f'보안 감사 로그 조회 실패: {exc}')


def cmd_security_sessions() -> str:
    """/security_sessions — 활성 세션 목록."""
    try:
        from ..security.session_manager import SessionManager
        mgr = SessionManager()
        return format_message('security_sessions', mgr.get_active_sessions())
    except Exception as exc:
        logger.error("cmd_security_sessions 오류: %s", exc)
        return format_message('error', f'세션 목록 조회 실패: {exc}')


def cmd_ip_block(ip: str = '') -> str:
    """/ip_block <ip> — IP 차단."""
    ip = ip.strip()
    if not ip:
        return format_message('error', '사용법: /ip_block <ip>')
    try:
        from ..security.ip_filter import IPFilter
        f = IPFilter()
        f.add_blacklist(ip)
        return format_message('ip_block', {'ip': ip, 'action': 'blocked', 'allowed': f.is_allowed(ip)})
    except Exception as exc:
        logger.error("cmd_ip_block 오류: %s", exc)
        return format_message('error', f'IP 차단 실패: {exc}')


# ─────────────────────────────────────────────────────────────
# Phase 73: 고객 세그먼트 커맨드
# ─────────────────────────────────────────────────────────────

def cmd_segments() -> str:
    """/segments — 세그먼트 목록."""
    try:
        from ..segmentation import SegmentManager
        mgr = SegmentManager()
        return format_message('segments_list', mgr.list())
    except Exception as exc:
        logger.error("cmd_segments 오류: %s", exc)
        return format_message('error', f'세그먼트 목록 조회 실패: {exc}')


def cmd_segment_detail(name: str = '') -> str:
    """/segment_detail <name> — 세그먼트 상세."""
    name = name.strip()
    if not name:
        return format_message('error', '사용법: /segment_detail <name>')
    try:
        from ..segmentation import SegmentManager
        mgr = SegmentManager()
        seg = mgr.get(name)
        if seg is None:
            return format_message('error', f'세그먼트 없음: {name}')
        return format_message('segment_detail', seg)
    except Exception as exc:
        logger.error("cmd_segment_detail 오류: %s", exc)
        return format_message('error', f'세그먼트 상세 조회 실패: {exc}')


def cmd_segment_export(name: str = '') -> str:
    """/segment_export <name> — 세그먼트 CSV 내보내기."""
    name = name.strip()
    if not name:
        return format_message('error', '사용법: /segment_export <name>')
    try:
        from ..segmentation import SegmentManager, SegmentExporter
        mgr = SegmentManager()
        if mgr.get(name) is None:
            return format_message('error', f'세그먼트 없음: {name}')
        customer_ids = mgr.get_customers(name)
        customers = [{'customer_id': cid} for cid in customer_ids]
        exporter = SegmentExporter()
        result = exporter.export_segment(name, customers)
        return format_message('segment_export', result)
    except Exception as exc:
        logger.error("cmd_segment_export 오류: %s", exc)
        return format_message('error', f'세그먼트 내보내기 실패: {exc}')


# ─────────────────────────────────────────────────────────────
# Phase 74: 동적 폼 빌더 커맨드
# ─────────────────────────────────────────────────────────────

def cmd_forms_list() -> str:
    """/forms_list — 폼 목록."""
    try:
        from ..form_builder import FormManager
        mgr = FormManager()
        return format_message('forms_list', mgr.list())
    except Exception as exc:
        logger.error("cmd_forms_list 오류: %s", exc)
        return format_message('error', f'폼 목록 조회 실패: {exc}')


def cmd_form_submissions(form_id: str = '') -> str:
    """/form_submissions <form_id> — 폼 제출 목록."""
    form_id = form_id.strip()
    if not form_id:
        return format_message('error', '사용법: /form_submissions <form_id>')
    try:
        from ..form_builder import FormSubmission
        store = FormSubmission()
        submissions = store.list_by_form(form_id)
        return format_message('form_submissions', {'form_id': form_id, 'submissions': submissions})
    except Exception as exc:
        logger.error("cmd_form_submissions 오류: %s", exc)
        return format_message('error', f'폼 제출 목록 조회 실패: {exc}')


# ─────────────────────────────────────────────────────────────
# Phase 75: 워크플로 엔진 커맨드
# ─────────────────────────────────────────────────────────────

def cmd_workflows() -> str:
    """/workflows — 워크플로 목록."""
    try:
        from ..workflow_engine import WorkflowEngine
        engine = WorkflowEngine()
        return format_message('workflow_engine_list', engine.list_definitions())
    except Exception as exc:
        logger.error("cmd_workflows 오류: %s", exc)
        return format_message('error', f'워크플로 목록 조회 실패: {exc}')


def cmd_workflow_start_engine(name: str = '') -> str:
    """/workflow_start <name> — 워크플로 시작."""
    name = name.strip()
    if not name:
        return format_message('error', '사용법: /workflow_start <name>')
    try:
        from ..workflow_engine import WorkflowEngine
        engine = WorkflowEngine()
        instance = engine.start(name)
        return format_message('workflow_engine_start', instance.to_dict())
    except Exception as exc:
        logger.error("cmd_workflow_start_engine 오류: %s", exc)
        return format_message('error', f'워크플로 시작 실패: {exc}')


def cmd_workflow_status_engine(instance_id: str = '') -> str:
    """/workflow_status <id> — 워크플로 인스턴스 상태."""
    instance_id = instance_id.strip()
    if not instance_id:
        return format_message('error', '사용법: /workflow_status <id>')
    try:
        from ..workflow_engine import WorkflowEngine
        engine = WorkflowEngine()
        instance = engine.get_instance(instance_id)
        if instance is None:
            return format_message('error', f'인스턴스 없음: {instance_id}')
        return format_message('workflow_engine_status', instance.to_dict())
    except Exception as exc:
        logger.error("cmd_workflow_status_engine 오류: %s", exc)
        return format_message('error', f'워크플로 상태 조회 실패: {exc}')


# ─────────────────────────────────────────────────────────────
# Phase 76: 파일 스토리지 커맨드
# ─────────────────────────────────────────────────────────────

def cmd_files_list() -> str:
    """/files_list — 파일 목록."""
    try:
        from ..file_storage import StorageManager
        mgr = StorageManager()
        files = mgr.list()
        return format_message('files_list', [f.to_dict() for f in files])
    except Exception as exc:
        logger.error("cmd_files_list 오류: %s", exc)
        return format_message('error', f'파일 목록 조회 실패: {exc}')


def cmd_file_quota(owner_id: str = 'default') -> str:
    """/file_quota — 스토리지 사용량."""
    owner_id = owner_id.strip() or 'default'
    try:
        from ..file_storage import StorageManager
        mgr = StorageManager()
        return format_message('file_quota', mgr.get_quota(owner_id))
    except Exception as exc:
        logger.error("cmd_file_quota 오류: %s", exc)
        return format_message('error', f'스토리지 사용량 조회 실패: {exc}')


def cmd_file_delete(key: str = '') -> str:
    """/file_delete <key> — 파일 삭제."""
    key = key.strip()
    if not key:
        return format_message('error', '사용법: /file_delete <key>')
    try:
        from ..file_storage import StorageManager
        mgr = StorageManager()
        mgr.delete(key)
        return format_message('file_delete', {'key': key, 'deleted': True})
    except Exception as exc:
        logger.error("cmd_file_delete 오류: %s", exc)
        return format_message('error', f'파일 삭제 실패: {exc}')


# ─────────────────────────────────────────────────────────────
# Phase 77: 이벤트 소싱 커맨드
# ─────────────────────────────────────────────────────────────

def cmd_events_list(aggregate_id: str = '') -> str:
    """/events_list <aggregate_id> — 이벤트 목록."""
    aggregate_id = aggregate_id.strip()
    try:
        from ..event_sourcing import EventStore
        store = EventStore()
        if aggregate_id:
            events = store.get_events(aggregate_id)
        else:
            events = store.get_all()
        return format_message('events_list', [e.to_dict() for e in events])
    except Exception as exc:
        logger.error("cmd_events_list 오류: %s", exc)
        return format_message('error', f'이벤트 목록 조회 실패: {exc}')


def cmd_event_replay(aggregate_id: str = '') -> str:
    """/event_replay <aggregate_id> — 이벤트 리플레이."""
    aggregate_id = aggregate_id.strip()
    if not aggregate_id:
        return format_message('error', '사용법: /event_replay <aggregate_id>')
    try:
        from ..event_sourcing import EventStore, EventReplay
        store = EventStore()
        replay = EventReplay()
        events = store.get_events(aggregate_id)
        replayed = replay.replay(events)
        return format_message('event_replay', {
            'aggregate_id': aggregate_id,
            'replayed_count': len(replayed),
        })
    except Exception as exc:
        logger.error("cmd_event_replay 오류: %s", exc)
        return format_message('error', f'이벤트 리플레이 실패: {exc}')


# ─────────────────────────────────────────────────────────────
# Phase 78: 피처 플래그 고도화 커맨드
# ─────────────────────────────────────────────────────────────

def cmd_flags() -> str:
    """/flags — 피처 플래그 목록."""
    try:
        from ..feature_flags import FeatureFlagManager
        mgr = FeatureFlagManager()
        return format_message('flag_list', mgr.list_flags())
    except Exception as exc:
        logger.error("cmd_flags 오류: %s", exc)
        return format_message('error', f'피처 플래그 목록 조회 실패: {exc}')


def cmd_flag_toggle(name: str = '') -> str:
    """/flag_toggle <name> — 플래그 토글."""
    name = name.strip()
    if not name:
        return format_message('error', '사용법: /flag_toggle <name>')
    try:
        from ..feature_flags import FeatureFlagManager
        mgr = FeatureFlagManager()
        flag = mgr.get_flag(name)
        if flag is None:
            return format_message('error', f'플래그 없음: {name}')
        updated = mgr.update_flag(name, enabled=not flag['enabled'])
        return format_message('flag_toggle', updated)
    except Exception as exc:
        logger.error("cmd_flag_toggle 오류: %s", exc)
        return format_message('error', f'플래그 토글 실패: {exc}')


def cmd_flag_evaluate(name: str = '', user_id: str = '') -> str:
    """/flag_evaluate <name> <user_id> — 플래그 평가."""
    name = name.strip()
    user_id = user_id.strip()
    if not name:
        return format_message('error', '사용법: /flag_evaluate <name> <user_id>')
    try:
        from ..feature_flags import (
            FeatureFlagManager, FeatureFlag, TargetingRule, FlagEvaluatorAdvanced
        )
        mgr = FeatureFlagManager()
        flag_data = mgr.get_flag(name)
        if flag_data is None:
            return format_message('error', f'플래그 없음: {name}')
        rules = [TargetingRule(**r) for r in flag_data.get('rules', [])]
        flag = FeatureFlag(
            name=flag_data['name'],
            enabled=flag_data.get('enabled', False),
            rules=rules,
            rollout_percentage=flag_data.get('rollout_percentage', 100.0),
        )
        evaluator = FlagEvaluatorAdvanced()
        result = evaluator.evaluate(flag, user_id=user_id)
        return format_message('flag_evaluate', {'flag_name': name, 'user_id': user_id, **result})
    except Exception as exc:
        logger.error("cmd_flag_evaluate 오류: %s", exc)
        return format_message('error', f'플래그 평가 실패: {exc}')
