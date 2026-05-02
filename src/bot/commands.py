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


# ---------------------------------------------------------------------------
# Phase 79: 리뷰 분석 명령어
# ---------------------------------------------------------------------------

def cmd_review_stats(product_id: str = '') -> str:
    """/review_stats <product_id> — 리뷰 통계 조회."""
    product_id = product_id.strip() or 'p001'
    try:
        from ..review_analytics import ReviewAnalyzer
        analyzer = ReviewAnalyzer()
        result = analyzer.analyze(product_id)
        return format_message('review_stats', result)
    except Exception as exc:
        logger.error("cmd_review_stats 오류: %s", exc)
        return format_message('error', f'리뷰 통계 조회 실패: {exc}')


def cmd_review_sentiment(text: str = '') -> str:
    """/review_sentiment <text> — 리뷰 감성 분석."""
    text = text.strip()
    if not text:
        return format_message('error', '사용법: /review_sentiment <text>')
    try:
        from ..review_analytics import SentimentAnalyzer
        analyzer = SentimentAnalyzer()
        result = analyzer.analyze_text(text)
        return format_message('review_sentiment', result)
    except Exception as exc:
        logger.error("cmd_review_sentiment 오류: %s", exc)
        return format_message('error', f'감성 분석 실패: {exc}')


# ---------------------------------------------------------------------------
# Phase 80: 배송비 계산기 명령어
# ---------------------------------------------------------------------------

def cmd_shipping_calc(weight_g: str = '500', zone: str = 'domestic') -> str:
    """/shipping_calc <weight_g> <zone> — 배송비 계산."""
    try:
        from ..shipping_calculator import ShippingCalculator
        calc = ShippingCalculator()
        result = calc.calculate(weight_g=float(weight_g), zone=zone)
        return format_message('shipping_calc', result)
    except Exception as exc:
        logger.error("cmd_shipping_calc 오류: %s", exc)
        return format_message('error', f'배송비 계산 실패: {exc}')


def cmd_shipping_zones() -> str:
    """/shipping_zones — 배송 구역 목록 조회."""
    try:
        from ..shipping_calculator import ShippingZone
        zones = ShippingZone().list_zones()
        return format_message('shipping_zones', zones)
    except Exception as exc:
        logger.error("cmd_shipping_zones 오류: %s", exc)
        return format_message('error', f'배송 구역 조회 실패: {exc}')


# ---------------------------------------------------------------------------
# Phase 81: 알림 템플릿 명령어
# ---------------------------------------------------------------------------

def cmd_templates_list() -> str:
    """/templates_list — 알림 템플릿 목록 조회."""
    try:
        from ..notification_templates import TemplateManager
        mgr = TemplateManager()
        templates = mgr.list()
        return format_message('templates_list', templates)
    except Exception as exc:
        logger.error("cmd_templates_list 오류: %s", exc)
        return format_message('error', f'템플릿 목록 조회 실패: {exc}')


def cmd_template_preview(name: str = '') -> str:
    """/template_preview <name> — 템플릿 미리보기."""
    name = name.strip()
    if not name:
        return format_message('error', '사용법: /template_preview <name>')
    try:
        from ..notification_templates import TemplateManager, TemplatePreview
        mgr = TemplateManager()
        tmpl = mgr.get(name)
        if tmpl is None:
            return format_message('error', f'템플릿 없음: {name}')
        preview = TemplatePreview()
        result = preview.preview(tmpl)
        return format_message('template_preview', result)
    except Exception as exc:
        logger.error("cmd_template_preview 오류: %s", exc)
        return format_message('error', f'템플릿 미리보기 실패: {exc}')


# ---------------------------------------------------------------------------
# Phase 82: 결제 복구 명령어
# ---------------------------------------------------------------------------

def cmd_payment_failures() -> str:
    """/payment_failures — 결제 실패 목록 조회."""
    try:
        from ..payment_recovery import PaymentRecoveryManager
        mgr = PaymentRecoveryManager()
        failures = mgr.list_failures()
        return format_message('payment_failures', failures)
    except Exception as exc:
        logger.error("cmd_payment_failures 오류: %s", exc)
        return format_message('error', f'결제 실패 목록 조회 실패: {exc}')


def cmd_payment_retry(payment_id: str = '') -> str:
    """/payment_retry <payment_id> — 결제 재시도."""
    payment_id = payment_id.strip()
    if not payment_id:
        return format_message('error', '사용법: /payment_retry <payment_id>')
    try:
        from ..payment_recovery import PaymentRecoveryManager
        mgr = PaymentRecoveryManager()
        result = mgr.retry(payment_id)
        return format_message('payment_retry', result)
    except KeyError:
        return format_message('error', f'결제 없음: {payment_id}')
    except Exception as exc:
        logger.error("cmd_payment_retry 오류: %s", exc)
        return format_message('error', f'결제 재시도 실패: {exc}')


# ---------------------------------------------------------------------------
# Phase 83: 상품 추천 명령어
# ---------------------------------------------------------------------------

def cmd_recommendations(user_id: str = '') -> str:
    """/recommendations <user_id> — 추천 상품 조회."""
    user_id = user_id.strip() or 'anonymous'
    try:
        from ..recommendation import RecommendationEngine
        engine = RecommendationEngine()
        result = engine.recommend(user_id)
        return format_message('recommendations', result)
    except Exception as exc:
        logger.error("cmd_recommendations 오류: %s", exc)
        return format_message('error', f'추천 상품 조회 실패: {exc}')


def cmd_trending_products() -> str:
    """/trending_products — 트렌딩 상품 조회."""
    try:
        from ..recommendation import RecommendationEngine
        engine = RecommendationEngine()
        result = engine.trending()
        return format_message('trending_products', result)
    except Exception as exc:
        logger.error("cmd_trending_products 오류: %s", exc)
        return format_message('error', f'트렌딩 상품 조회 실패: {exc}')


# ---------------------------------------------------------------------------
# Phase 84: 주문 분할/병합 명령어
# ---------------------------------------------------------------------------

def cmd_order_split(order_id: str = '', strategy: str = 'supplier') -> str:
    """/order_split <order_id> <strategy> — 주문 분할."""
    order_id = order_id.strip()
    if not order_id:
        return format_message('error', '사용법: /order_split <order_id> [strategy]')
    try:
        from ..order_management import OrderSplitter
        splitter = OrderSplitter()
        result = splitter.split(order_id, strategy=strategy)
        return format_message('order_split', result)
    except Exception as exc:
        logger.error("cmd_order_split 오류: %s", exc)
        return format_message('error', f'주문 분할 실패: {exc}')


def cmd_order_merge(order_ids_str: str = '') -> str:
    """/order_merge <id1,id2,...> — 주문 병합."""
    order_ids_str = order_ids_str.strip()
    if not order_ids_str:
        return format_message('error', '사용법: /order_merge <id1,id2,...>')
    try:
        from ..order_management import OrderMerger
        order_ids = [oid.strip() for oid in order_ids_str.split(',')]
        merger = OrderMerger()
        result = merger.merge(order_ids)
        return format_message('order_merge', result)
    except Exception as exc:
        logger.error("cmd_order_merge 오류: %s", exc)
        return format_message('error', f'주문 병합 실패: {exc}')


def cmd_sub_orders(order_id: str = '') -> str:
    """/sub_orders <order_id> — 하위 주문 목록 조회."""
    order_id = order_id.strip()
    if not order_id:
        return format_message('error', '사용법: /sub_orders <order_id>')
    try:
        from ..order_management import SplitHistory
        history = SplitHistory()
        result = history.get_sub_orders(order_id)
        return format_message('sub_orders', result)
    except Exception as exc:
        logger.error("cmd_sub_orders 오류: %s", exc)
        return format_message('error', f'하위 주문 조회 실패: {exc}')


# ---------------------------------------------------------------------------
# Phase 85: 재고 입출고 이력 명령어
# ---------------------------------------------------------------------------

def cmd_stock_in(sku: str = '', qty: str = '') -> str:
    """/stock_in <sku> <qty> — 재고 입고 처리."""
    sku = sku.strip()
    qty_str = qty.strip()
    if not sku or not qty_str:
        return format_message('error', '사용법: /stock_in <sku> <qty>')
    try:
        from ..inventory_transactions import TransactionManager
        mgr = TransactionManager()
        tx = mgr.create(sku=sku, tx_type='inbound', quantity=int(qty_str), reason='manual_stock_in')
        return format_message('stock_in', {'transaction_id': tx.transaction_id, 'sku': tx.sku, 'quantity': tx.quantity})
    except Exception as exc:
        logger.error("cmd_stock_in 오류: %s", exc)
        return format_message('error', f'재고 입고 실패: {exc}')


def cmd_stock_out(sku: str = '', qty: str = '') -> str:
    """/stock_out <sku> <qty> — 재고 출고 처리."""
    sku = sku.strip()
    qty_str = qty.strip()
    if not sku or not qty_str:
        return format_message('error', '사용법: /stock_out <sku> <qty>')
    try:
        from ..inventory_transactions import TransactionManager
        mgr = TransactionManager()
        tx = mgr.create(sku=sku, tx_type='outbound', quantity=int(qty_str), reason='manual_stock_out')
        return format_message('stock_out', {'transaction_id': tx.transaction_id, 'sku': tx.sku, 'quantity': tx.quantity})
    except Exception as exc:
        logger.error("cmd_stock_out 오류: %s", exc)
        return format_message('error', f'재고 출고 실패: {exc}')


def cmd_stock_ledger(sku: str = '') -> str:
    """/stock_ledger <sku> — SKU 재고 원장 조회."""
    sku = sku.strip()
    if not sku:
        return format_message('error', '사용법: /stock_ledger <sku>')
    try:
        from ..inventory_transactions import TransactionManager, StockLedger
        mgr = TransactionManager()
        ledger = StockLedger(mgr)
        result = ledger.snapshot(sku)
        return format_message('stock_ledger', result)
    except Exception as exc:
        logger.error("cmd_stock_ledger 오류: %s", exc)
        return format_message('error', f'재고 원장 조회 실패: {exc}')


# ---------------------------------------------------------------------------
# Phase 86: 고객 세그멘테이션 명령어
# ---------------------------------------------------------------------------

def cmd_segments_list() -> str:
    """/segments_list — 세그먼트 목록 조회."""
    try:
        from ..customer_segmentation import SegmentManager
        mgr = SegmentManager()
        segments = mgr.list()
        return format_message('segments_list', segments)
    except Exception as exc:
        logger.error("cmd_segments_list 오류: %s", exc)
        return format_message('error', f'세그먼트 목록 조회 실패: {exc}')


def cmd_segment_stats(segment_id: str = '') -> str:
    """/segment_stats <segment_id> — 세그먼트 통계 조회."""
    segment_id = segment_id.strip()
    if not segment_id:
        return format_message('error', '사용법: /segment_stats <segment_id>')
    try:
        from ..customer_segmentation import SegmentManager, SegmentAnalyzer
        mgr = SegmentManager()
        seg = mgr.get(segment_id)
        if not seg:
            return format_message('error', f'세그먼트 없음: {segment_id}')
        analyzer = SegmentAnalyzer()
        result = analyzer.analyze(segment_id, [])
        return format_message('segment_stats', result)
    except Exception as exc:
        logger.error("cmd_segment_stats 오류: %s", exc)
        return format_message('error', f'세그먼트 통계 조회 실패: {exc}')


# ---------------------------------------------------------------------------
# Phase 87: 상품 비교 명령어
# ---------------------------------------------------------------------------

def cmd_compare(product_id1: str = '', product_id2: str = '') -> str:
    """/compare <product_id1> <product_id2> — 상품 비교."""
    product_id1 = product_id1.strip()
    product_id2 = product_id2.strip()
    if not product_id1 or not product_id2:
        return format_message('error', '사용법: /compare <product_id1> <product_id2>')
    try:
        from ..product_comparison import ComparisonEngine
        engine = ComparisonEngine()
        products = [{'product_id': product_id1}, {'product_id': product_id2}]
        result = engine.compare(products)
        return format_message('compare', result)
    except Exception as exc:
        logger.error("cmd_compare 오류: %s", exc)
        return format_message('error', f'상품 비교 실패: {exc}')


def cmd_comparison_history() -> str:
    """/comparison_history — 비교 이력 조회."""
    try:
        from ..product_comparison import ComparisonHistory
        history = ComparisonHistory()
        result = history.list()
        return format_message('comparison_history', result)
    except Exception as exc:
        logger.error("cmd_comparison_history 오류: %s", exc)
        return format_message('error', f'비교 이력 조회 실패: {exc}')


# ---------------------------------------------------------------------------
# Phase 88: 이메일 마케팅 명령어
# ---------------------------------------------------------------------------

def cmd_campaigns_list() -> str:
    """/campaigns_list — 이메일 캠페인 목록 조회."""
    try:
        from ..email_marketing import CampaignManager
        mgr = CampaignManager()
        camps = mgr.list()
        return format_message('campaigns_list', camps)
    except Exception as exc:
        logger.error("cmd_campaigns_list 오류: %s", exc)
        return format_message('error', f'캠페인 목록 조회 실패: {exc}')


def cmd_campaign_stats(campaign_id: str = '') -> str:
    """/campaign_stats <campaign_id> — 캠페인 통계 조회."""
    campaign_id = campaign_id.strip()
    if not campaign_id:
        return format_message('error', '사용법: /campaign_stats <campaign_id>')
    try:
        from ..email_marketing import CampaignManager, CampaignAnalytics
        mgr = CampaignManager()
        c = mgr.get(campaign_id)
        if not c:
            return format_message('error', f'캠페인 없음: {campaign_id}')
        analytics = CampaignAnalytics()
        result = analytics.stats(c)
        return format_message('campaign_stats', result)
    except Exception as exc:
        logger.error("cmd_campaign_stats 오류: %s", exc)
        return format_message('error', f'캠페인 통계 조회 실패: {exc}')


def cmd_campaign_send(campaign_id: str = '') -> str:
    """/campaign_send <campaign_id> — 캠페인 발송."""
    campaign_id = campaign_id.strip()
    if not campaign_id:
        return format_message('error', '사용법: /campaign_send <campaign_id>')
    try:
        from ..email_marketing import CampaignManager
        mgr = CampaignManager()
        result = mgr.send(campaign_id)
        return format_message('campaign_send', result)
    except Exception as exc:
        logger.error("cmd_campaign_send 오류: %s", exc)
        return format_message('error', f'캠페인 발송 실패: {exc}')


# ---------------------------------------------------------------------------
# Phase 89: 창고 관리 명령어
# ---------------------------------------------------------------------------

def cmd_warehouses() -> str:
    """/warehouses — 창고 목록 조회."""
    try:
        from ..warehouse import WarehouseManager
        mgr = WarehouseManager()
        whs = mgr.list()
        return format_message('warehouses', whs)
    except Exception as exc:
        logger.error("cmd_warehouses 오류: %s", exc)
        return format_message('error', f'창고 목록 조회 실패: {exc}')


def cmd_warehouse_status(warehouse_id: str = '') -> str:
    """/warehouse_status <id> — 창고 현황 조회."""
    warehouse_id = warehouse_id.strip()
    if not warehouse_id:
        return format_message('error', '사용법: /warehouse_status <id>')
    try:
        from ..warehouse import WarehouseManager, WarehouseReport
        mgr = WarehouseManager()
        wh = mgr.get(warehouse_id)
        if not wh:
            return format_message('error', f'창고 없음: {warehouse_id}')
        report = WarehouseReport()
        result = report.status(wh)
        return format_message('warehouse_status', result)
    except Exception as exc:
        logger.error("cmd_warehouse_status 오류: %s", exc)
        return format_message('error', f'창고 현황 조회 실패: {exc}')


def cmd_picking_order(order_id: str = '') -> str:
    """/picking_order <order_id> — 피킹 주문 생성."""
    order_id = order_id.strip()
    if not order_id:
        return format_message('error', '사용법: /picking_order <order_id>')
    try:
        from ..warehouse import PickingOrder
        picking = PickingOrder()
        result = picking.create(order_id=order_id, items=[])
        return format_message('picking_order', result)
    except Exception as exc:
        logger.error("cmd_picking_order 오류: %s", exc)
        return format_message('error', f'피킹 주문 생성 실패: {exc}')


# ---------------------------------------------------------------------------
# Phase 90: 세금 계산 명령어
# ---------------------------------------------------------------------------

def cmd_tax_calc(amount: str = '', country: str = 'KR') -> str:
    """/tax_calc <amount> <country> — 세금 계산."""
    amount = amount.strip()
    if not amount:
        return format_message('error', '사용법: /tax_calc <amount> <country>')
    try:
        from ..tax_engine import TaxCalculator
        calc = TaxCalculator()
        result = calc.calculate(float(amount), context={'country': country.strip()})
        return format_message('tax_calc', result)
    except Exception as exc:
        logger.error("cmd_tax_calc 오류: %s", exc)
        return format_message('error', f'세금 계산 실패: {exc}')


def cmd_customs(amount: str = '', origin: str = 'US') -> str:
    """/customs <amount> <origin> — 관세 계산."""
    amount = amount.strip()
    if not amount:
        return format_message('error', '사용법: /customs <amount> <origin>')
    try:
        from ..tax_engine import CrossBorderTax
        cb = CrossBorderTax()
        result = cb.calculate(float(amount), origin_country=origin.strip())
        return format_message('customs', result)
    except Exception as exc:
        logger.error("cmd_customs 오류: %s", exc)
        return format_message('error', f'관세 계산 실패: {exc}')


# ---------------------------------------------------------------------------
# Phase 91: 분쟁 관리 명령어
# ---------------------------------------------------------------------------

def cmd_disputes() -> str:
    """/disputes — 열린 분쟁 목록."""
    try:
        from ..disputes.dispute_manager import DisputeManager
        mgr = DisputeManager()
        disputes = mgr.list(status='opened')
        if not disputes:
            return format_message('info', '열린 분쟁이 없습니다.')
        lines = [f"• [{d.dispute_id[:8]}] {d.dispute_type.value} | {d.order_id}" for d in disputes]
        return format_message('info', f"열린 분쟁 {len(disputes)}건:\n" + "\n".join(lines))
    except Exception as exc:
        logger.error("cmd_disputes 오류: %s", exc)
        return format_message('error', f'분쟁 목록 조회 실패: {exc}')


def cmd_dispute_create(order_id: str = '', dispute_type: str = '', reason: str = '') -> str:
    """/dispute_create <order_id> <type> <reason> — 분쟁 생성."""
    order_id = order_id.strip()
    dispute_type = dispute_type.strip()
    reason = reason.strip()
    if not order_id or not dispute_type or not reason:
        return format_message('error', '사용법: /dispute_create <order_id> <type> <reason>')
    try:
        from ..disputes.dispute_manager import DisputeManager
        mgr = DisputeManager()
        dispute = mgr.create(
            order_id=order_id,
            customer_id='bot',
            reason=reason,
            dispute_type=dispute_type,
        )
        return format_message('info', f"분쟁 생성 완료: {dispute.dispute_id}")
    except Exception as exc:
        logger.error("cmd_dispute_create 오류: %s", exc)
        return format_message('error', f'분쟁 생성 실패: {exc}')


def cmd_dispute_resolve(dispute_id: str = '', decision: str = '') -> str:
    """/dispute_resolve <dispute_id> <decision> — 분쟁 해결."""
    dispute_id = dispute_id.strip()
    decision = decision.strip()
    if not dispute_id or not decision:
        return format_message('error', '사용법: /dispute_resolve <dispute_id> <decision>')
    try:
        from ..disputes.dispute_manager import DisputeManager
        mgr = DisputeManager()
        dispute = mgr.transition(dispute_id, decision)
        return format_message('info', f"분쟁 상태 변경: {dispute.dispute_id} → {dispute.status.value}")
    except Exception as exc:
        logger.error("cmd_dispute_resolve 오류: %s", exc)
        return format_message('error', f'분쟁 해결 실패: {exc}')


# ---------------------------------------------------------------------------
# Phase 93: 글로벌 커머스 명령어
# ---------------------------------------------------------------------------

def cmd_import_order(source: str = '', product_url: str = '') -> str:
    """/import_order <source> <product_url> — 수입 주문 생성."""
    source = source.strip()
    product_url = product_url.strip()
    if not source or not product_url:
        return format_message('error', '사용법: /import_order <source_country> <product_url>')
    try:
        from ..global_commerce.trade.import_manager import ImportManager
        mgr = ImportManager()
        order = mgr.create(
            product_url=product_url,
            source_country=source,
        )
        return format_message('info',
                               f"수입 주문 생성 완료: {order.order_id}\n"
                               f"출처: {order.source_country} | 상태: {order.status.value}")
    except Exception as exc:
        logger.error("cmd_import_order 오류: %s", exc)
        return format_message('error', f'수입 주문 생성 실패: {exc}')


def cmd_customs_calc(price: str = '', country: str = '', hs_code: str = 'DEFAULT') -> str:
    """/customs_calc <price_usd> <country> <hs_code> — 관세 계산."""
    price = price.strip()
    country = country.strip()
    if not price or not country:
        return format_message('error', '사용법: /customs_calc <price_usd> <country> <hs_code>')
    try:
        from ..global_commerce.trade.import_manager import CustomsDutyCalculator
        calc = CustomsDutyCalculator()
        result = calc.calculate(
            total_price_usd=float(price),
            hs_code=hs_code.strip(),
            source_country=country,
        )
        if result.get('duty_free'):
            return format_message('info',
                                   f"면세 해당: ${float(price):.2f} <= ${result['threshold_usd']:.2f} ({country})")
        return format_message('info',
                               f"관세 계산 결과:\n"
                               f"• 상품가: {result['total_price_krw']:,.0f}원\n"
                               f"• 관세({result['duty_rate']*100:.0f}%): {result['customs_duty_krw']:,.0f}원\n"
                               f"• 부가세: {result['vat_krw']:,.0f}원\n"
                               f"• 총 세금: {result['total_tax_krw']:,.0f}원")
    except Exception as exc:
        logger.error("cmd_customs_calc 오류: %s", exc)
        return format_message('error', f'관세 계산 실패: {exc}')


def cmd_trade_status(order_id: str = '') -> str:
    """/trade_status <order_id> — 무역 주문 상태."""
    order_id = order_id.strip()
    if not order_id:
        return format_message('error', '사용법: /trade_status <order_id>')
    try:
        from ..global_commerce.trade.import_manager import ImportManager
        from ..global_commerce.trade.export_manager import ExportManager
        imp_mgr = ImportManager()
        exp_mgr = ExportManager()
        order = imp_mgr.get(order_id) or exp_mgr.get(order_id)
        if order is None:
            return format_message('error', f'주문을 찾을 수 없습니다: {order_id}')
        order_type = '수입' if hasattr(order, 'product_url') else '수출'
        return format_message('info',
                               f"{order_type} 주문 상태:\n"
                               f"• ID: {order.order_id[:8]}\n"
                               f"• 상태: {order.status.value}\n"
                               f"• 업데이트: {order.updated_at}")
    except Exception as exc:
        logger.error("cmd_trade_status 오류: %s", exc)
        return format_message('error', f'무역 주문 상태 조회 실패: {exc}')


def cmd_shipping_intl(weight: str = '', from_country: str = '', to_country: str = '') -> str:
    """/shipping_intl <weight_kg> <from_country> <to_country> — 국제 배송비 계산."""
    weight = weight.strip()
    from_country = from_country.strip()
    to_country = to_country.strip()
    if not weight or not from_country or not to_country:
        return format_message('error', '사용법: /shipping_intl <weight_kg> <from> <to>')
    try:
        from ..global_commerce.shipping.international_shipping_manager import InternationalShippingManager
        mgr = InternationalShippingManager()
        quote = mgr.calculate(
            weight_kg=float(weight),
            origin_country=from_country,
            destination_country=to_country,
        )
        return format_message('info',
                               f"국제 배송비 ({from_country}→{to_country}):\n"
                               f"• 무게: {quote.chargeable_weight_kg}kg\n"
                               f"• 기본료: {quote.base_fee_krw:,.0f}원\n"
                               f"• 유류할증: {quote.fuel_surcharge_krw:,.0f}원\n"
                               f"• 합계: {quote.total_fee_krw:,.0f}원\n"
                               f"• 예상 배송: {quote.transit_days}일")
    except Exception as exc:
        logger.error("cmd_shipping_intl 오류: %s", exc)
        return format_message('error', f'국제 배송비 계산 실패: {exc}')


def cmd_ai_recommend(user_id: str = '') -> str:
    """/ai_recommend <user_id> — AI 맞춤 추천."""
    user_id = user_id.strip()
    if not user_id:
        return format_message('error', '사용법: /ai_recommend <user_id>')
    try:
        from ..ai_recommendation import AIRecommendationEngine
        engine = AIRecommendationEngine()
        results = engine.recommend(user_id, top_n=5, strategy='ensemble')
        if not results:
            return format_message('info', f'{user_id}님을 위한 추천 상품이 없습니다.')
        lines = '\n'.join(
            f"• {r.product_id} (점수: {r.score:.2f}, 전략: {r.strategy})"
            for r in results
        )
        return format_message('info', f"AI 맞춤 추천 ({user_id}):\n{lines}")
    except Exception as exc:
        logger.error("cmd_ai_recommend 오류: %s", exc)
        return format_message('error', f'AI 추천 실패: {exc}')


def cmd_trending(category: str = '') -> str:
    """/trending [category] — 트렌딩 상품."""
    category = category.strip()
    try:
        from ..ai_recommendation import AIRecommendationEngine
        engine = AIRecommendationEngine()
        results = engine.get_trending(top_n=5, category=category or None)
        if not results:
            label = f'카테고리 "{category}"' if category else '전체'
            return format_message('info', f'{label} 트렌딩 상품이 없습니다.')
        label = f'카테고리 "{category}"' if category else '전체'
        lines = '\n'.join(
            f"• {r.product_id} (점수: {r.score:.2f})"
            for r in results
        )
        return format_message('info', f"트렌딩 상품 ({label}):\n{lines}")
    except Exception as exc:
        logger.error("cmd_trending 오류: %s", exc)
        return format_message('error', f'트렌딩 조회 실패: {exc}')


def cmd_cross_sell(product_id: str = '') -> str:
    """/cross_sell <product_id> — 함께 구매 추천."""
    product_id = product_id.strip()
    if not product_id:
        return format_message('error', '사용법: /cross_sell <product_id>')
    try:
        from ..ai_recommendation import AIRecommendationEngine
        engine = AIRecommendationEngine()
        results = engine.get_cross_sell([product_id], top_n=5)
        if not results:
            return format_message('info', f'"{product_id}"에 대한 크로스셀 추천이 없습니다.')
        lines = '\n'.join(
            f"• {r.product_id} (점수: {r.score:.2f})"
            for r in results
        )
        return format_message('info', f"함께 구매 추천 ({product_id}):\n{lines}")
    except Exception as exc:
        logger.error("cmd_cross_sell 오류: %s", exc)
        return format_message('error', f'크로스셀 추천 실패: {exc}')


def cmd_recommend_metrics() -> str:
    """/recommend_metrics — 추천 성능 현황."""
    try:
        from ..ai_recommendation import AIRecommendationEngine
        engine = AIRecommendationEngine()
        metrics = engine.feedback.get_metrics()
        weights = engine.feedback.get_strategy_weights()
        if not metrics:
            return format_message('info', '추천 메트릭 데이터가 없습니다.')
        lines = []
        for strategy, m in metrics.items():
            lines.append(
                f"• {strategy}: 노출 {m['impressions']}, "
                f"CTR {m['ctr']:.1%}, CVR {m['cvr']:.1%}"
            )
        top_strategies = sorted(weights.items(), key=lambda x: -x[1])[:3]
        weight_lines = ', '.join(f"{s}: {w:.2f}" for s, w in top_strategies)
        metrics_text = '\n'.join(lines)
        return format_message('info',
                               f"추천 성능 현황:\n{metrics_text}\n"
                               f"상위 가중치: {weight_lines}")
    except Exception as exc:
        logger.error("cmd_recommend_metrics 오류: %s", exc)
        return format_message('error', f'추천 메트릭 조회 실패: {exc}')


def cmd_mobile_stats() -> str:
    """/mobile_stats — 모바일 API 사용 현황."""
    try:
        from ..mobile_api.mobile_admin import MobileAdminService
        svc = MobileAdminService()
        summary = svc.get_dashboard_summary()
        lines = [
            f"• 주문 수: {summary['order_count']}",
            f"• 매출: {summary['revenue']:,.2f}",
            f"• 활성 사용자: {summary['active_users']}",
            f"• 재고 알림: {summary['inventory_alerts']}",
            f"• CS 대기: {summary['pending_cs']}",
        ]
        return format_message('info', '모바일 API 현황:\n' + '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_mobile_stats 오류: %s", exc)
        return format_message('error', f'모바일 현황 조회 실패: {exc}')


def cmd_push_send(user_id: str = '', message: str = '') -> str:
    """/push_send <user_id> <message> — 수동 푸시 발송."""
    if not user_id or not message:
        return format_message('error', '사용법: /push_send <user_id> <message>')
    try:
        from ..mobile_api.mobile_notification import MobilePushService
        svc = MobilePushService()
        notif = svc.send_promotion_notification(user_id, '관리자 알림', message)
        return format_message('info', f'푸시 발송 완료: {notif.notification_id}')
    except Exception as exc:
        logger.error("cmd_push_send 오류: %s", exc)
        return format_message('error', f'푸시 발송 실패: {exc}')


# ── Phase 96: 자동 구매 엔진 커맨드 ────────────────────────────────────────

def cmd_auto_buy(product_url: str = '') -> str:
    """/auto_buy <product_url> — 자동 구매 실행."""
    if not product_url:
        return format_message('error', '사용법: /auto_buy <product_url>')
    try:
        from ..auto_purchase.import_automation import ProxyBuyAutomation
        from ..auto_purchase.purchase_engine import AutoPurchaseEngine
        engine = AutoPurchaseEngine()
        automation = ProxyBuyAutomation(purchase_engine=engine)
        # URL에서 마켓플레이스 추론
        if 'amazon' in product_url.lower():
            marketplace = 'amazon_us'
        elif 'taobao' in product_url.lower():
            marketplace = 'taobao'
        elif '1688' in product_url.lower():
            marketplace = 'alibaba_1688'
        else:
            marketplace = 'amazon_us'
        request = automation.create_proxy_request(
            customer_id='bot_user',
            product_url=product_url,
            product_name='Bot Purchase',
            marketplace=marketplace,
        )
        return format_message('info',
                               f'자동 구매 요청 생성:\n'
                               f'• 요청 ID: {request.request_id}\n'
                               f'• 마켓플레이스: {marketplace}\n'
                               f'• 상태: {request.status}')
    except Exception as exc:
        logger.error("cmd_auto_buy 오류: %s", exc)
        return format_message('error', f'자동 구매 실패: {exc}')


def cmd_buy_status(order_id: str = '') -> str:
    """/buy_status <order_id> — 구매 상태 확인."""
    if not order_id:
        return format_message('error', '사용법: /buy_status <order_id>')
    try:
        from ..auto_purchase.purchase_engine import AutoPurchaseEngine
        engine = AutoPurchaseEngine()
        status = engine.get_order_status(order_id)
        if not status:
            return format_message('error', f'주문을 찾을 수 없습니다: {order_id}')
        lines = [
            f'• 주문 ID: {status["order_id"]}',
            f'• 상태: {status["status"]}',
            f'• 마켓플레이스: {status["marketplace"]}',
            f'• 상품 ID: {status["product_id"]}',
            f'• 수량: {status["quantity"]}',
        ]
        if status.get('tracking_number'):
            lines.append(f'• 운송장: {status["tracking_number"]}')
        if status.get('error_message'):
            lines.append(f'• 오류: {status["error_message"]}')
        return format_message('info', '구매 상태:\n' + '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_buy_status 오류: %s", exc)
        return format_message('error', f'상태 조회 실패: {exc}')


def cmd_buy_queue() -> str:
    """/buy_queue — 현재 구매 큐."""
    try:
        from ..auto_purchase.purchase_engine import AutoPurchaseEngine
        engine = AutoPurchaseEngine()
        q = engine.get_queue_status()
        lines = [
            f'• 긴급: {q["urgent"]}건',
            f'• 일반: {q["normal"]}건',
            f'• 대기: {q["low"]}건',
            f'• 처리 중: {q["active"]}건',
            f'• 총 대기: {q["total_queued"]}건',
        ]
        return format_message('info', '구매 큐 현황:\n' + '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_buy_queue 오류: %s", exc)
        return format_message('error', f'큐 조회 실패: {exc}')


def cmd_buy_metrics() -> str:
    """/buy_metrics — 구매 성과 현황."""
    try:
        from ..auto_purchase.purchase_engine import AutoPurchaseEngine
        engine = AutoPurchaseEngine()
        m = engine.get_metrics()
        lines = [
            f'• 총 주문: {m["total_orders"]}건',
            f'• 성공: {m["successful_orders"]}건',
            f'• 실패: {m["failed_orders"]}건',
            f'• 성공률: {m["success_rate"]:.1%}',
            f'• 총 구매금액: ${m["total_spend"]:,.2f}',
        ]
        return format_message('info', '구매 성과:\n' + '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_buy_metrics 오류: %s", exc)
        return format_message('error', f'메트릭 조회 실패: {exc}')


def cmd_buy_rules() -> str:
    """/buy_rules — 구매 규칙 목록."""
    try:
        from ..auto_purchase.purchase_rules import PurchaseRuleEngine
        engine = PurchaseRuleEngine()
        rules = engine.list_rules()
        if not rules:
            return format_message('info', '등록된 구매 규칙이 없습니다.')
        lines = [f'• [{r["name"]}] {r["description"]}' for r in rules]
        return format_message('info', '구매 규칙 목록:\n' + '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_buy_rules 오류: %s", exc)
        return format_message('error', f'규칙 조회 실패: {exc}')


def cmd_buy_simulate(product_url: str = '') -> str:
    """/buy_simulate <product_url> — 구매 시뮬레이션."""
    if not product_url:
        return format_message('error', '사용법: /buy_simulate <product_url>')
    try:
        from ..auto_purchase.purchase_engine import AutoPurchaseEngine
        engine = AutoPurchaseEngine()
        # URL에서 마켓플레이스/상품 ID 추론
        if 'amazon' in product_url.lower():
            marketplace = 'amazon_us'
            parts = product_url.split('/dp/')
            product_id = parts[1].split('/')[0].split('?')[0] if len(parts) > 1 else 'B08N5WRWNW'
        elif 'taobao' in product_url.lower():
            marketplace = 'taobao'
            product_id = 'TB001234'
        else:
            marketplace = 'amazon_us'
            product_id = 'B08N5WRWNW'

        result = engine.simulate(
            source_product_id=product_id,
            marketplace=marketplace,
            quantity=1,
            unit_price=50.0,
            selling_price=70.0,
        )
        lines = [
            f'• 상품: {product_id}',
            f'• 마켓플레이스: {marketplace}',
            f'• 규칙 결정: {result["rule_decision"]}',
            f'• 마진율: {result["margin_rate"]:.1%}',
            f'• 예상 비용: ${result["estimated_total_cost"]:.2f}',
            f'• 진행 여부: {"✅ 진행" if result["would_proceed"] else "❌ 중단"}',
        ]
        return format_message('info', '구매 시뮬레이션:\n' + '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_buy_simulate 오류: %s", exc)
        return format_message('error', f'시뮬레이션 실패: {exc}')


# ── Phase 98: 멀티벤더 마켓플레이스 ─────────────────────────────────────────

def cmd_vendors(status: str = '') -> str:
    """/vendors [status] — 판매자 목록."""
    try:
        from ..vendor_marketplace.vendor_manager import VendorOnboardingManager
        mgr = VendorOnboardingManager()
        vendors = mgr.list_vendors(status=status or None)
        if not vendors:
            return format_message('info', f'판매자 없음 (상태: {status or "전체"})')
        lines = [f'• [{v.status.value}] {v.name} ({v.email}) — {v.tier.value}' for v in vendors]
        return format_message('info', f'판매자 목록 ({len(vendors)}명):\n' + '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_vendors 오류: %s", exc)
        return format_message('error', f'판매자 목록 조회 실패: {exc}')


def cmd_vendor_approve(vendor_id: str = '') -> str:
    """/vendor_approve <vendor_id> — 판매자 승인."""
    if not vendor_id:
        return format_message('error', '사용법: /vendor_approve <vendor_id>')
    try:
        from ..vendor_marketplace.vendor_manager import VendorOnboardingManager
        mgr = VendorOnboardingManager()
        vendor = mgr.approve(vendor_id)
        return format_message('info', f'판매자 승인 완료: {vendor.name} ({vendor.status.value})')
    except Exception as exc:
        logger.error("cmd_vendor_approve 오류: %s", exc)
        return format_message('error', f'판매자 승인 실패: {exc}')


def cmd_vendor_score(vendor_id: str = '') -> str:
    """/vendor_score <vendor_id> — 판매자 점수 조회."""
    if not vendor_id:
        return format_message('error', '사용법: /vendor_score <vendor_id>')
    try:
        from ..vendor_marketplace.vendor_analytics import VendorScoring
        scoring = VendorScoring()
        # Mock 지표로 점수 계산
        score = scoring.calculate(
            delivery_delay_rate=0.05,
            return_rate=0.03,
            avg_rating=4.5,
            cs_response_hours=2.0,
        )
        lines = [
            f'• 종합 점수: {score["total_score"]:.1f}점 (등급: {score["grade"]})',
            f'• 배송 점수: {score["delivery_score"]:.1f}',
            f'• 반품 점수: {score["return_score"]:.1f}',
            f'• 평점 점수: {score["rating_score"]:.1f}',
            f'• CS 점수: {score["cs_score"]:.1f}',
        ]
        return format_message('info', f'판매자 점수 [{vendor_id}]:\n' + '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_vendor_score 오류: %s", exc)
        return format_message('error', f'점수 조회 실패: {exc}')


def cmd_vendor_settlement(vendor_id: str = '') -> str:
    """/vendor_settlement <vendor_id> — 정산 조회."""
    if not vendor_id:
        return format_message('error', '사용법: /vendor_settlement <vendor_id>')
    try:
        from ..vendor_marketplace.settlement import SettlementManager
        mgr = SettlementManager()
        settlements = mgr.list_vendor_settlements(vendor_id)
        if not settlements:
            return format_message('info', f'정산 내역 없음: {vendor_id}')
        lines = [
            f'• [{s.status.value}] {s.settlement_id[:8]}... '
            f'순수익: {s.net_amount:,.0f}원 ({s.cycle})'
            for s in settlements
        ]
        return format_message('info', f'정산 내역 ({len(settlements)}건):\n' + '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_vendor_settlement 오류: %s", exc)
        return format_message('error', f'정산 조회 실패: {exc}')


def cmd_vendor_ranking() -> str:
    """/vendor_ranking — 판매자 랭킹."""
    try:
        from ..vendor_marketplace.vendor_analytics import VendorRanking
        ranking = VendorRanking()
        # Mock 데이터로 예시 랭킹 표시
        sample_stats = [
            {'vendor_id': 'V001', 'name': '베스트샵', 'total_sales': 5000000, 'total_score': 92.0, 'avg_rating': 4.8},
            {'vendor_id': 'V002', 'name': '스마트스토어', 'total_sales': 3000000, 'total_score': 85.0, 'avg_rating': 4.5},
            {'vendor_id': 'V003', 'name': '마켓킹', 'total_sales': 1500000, 'total_score': 70.0, 'avg_rating': 4.0},
        ]
        leaderboard = ranking.build_leaderboard(sample_stats)
        lines = [
            f'#{v["score_rank"]} {v["name"]} — 점수: {v["total_score"]:.0f}점 '
            f'({" ".join(v["badges"]) if v["badges"] else "-"})'
            for v in leaderboard
        ]
        return format_message('info', '판매자 랭킹:\n' + '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_vendor_ranking 오류: %s", exc)
        return format_message('error', f'랭킹 조회 실패: {exc}')


# ── Phase 99: 물류 최적화 봇 커맨드 ──────────────────────────────────────

def cmd_logistics_status() -> str:
    """/logistics_status — 물류 현황 조회."""
    try:
        from ..logistics.last_mile import LastMileTracker, DeliveryAssignment
        from ..logistics.logistics_automation import LogisticsAlertService
        from ..logistics.logistics_models import DeliveryStatus

        tracker = LastMileTracker()
        assignment = DeliveryAssignment()
        alert_svc = LogisticsAlertService()

        active = tracker.list_deliveries(DeliveryStatus.in_transit)
        available_agents = assignment.list_agents("available")
        alerts = alert_svc.get_alerts()

        lines = [
            f'• 진행 중 배송: {len(active)}건',
            f'• 사용 가능 기사: {len(available_agents)}명',
            f'• 최근 알림: {len(alerts)}건',
        ]
        return format_message('info', '물류 현황:\n' + '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_logistics_status 오류: %s", exc)
        return format_message('error', f'물류 현황 조회 실패: {exc}')


def cmd_route_optimize(delivery_ids_str: str = '') -> str:
    """/route_optimize <delivery_ids> — 경로 최적화."""
    if not delivery_ids_str.strip():
        return format_message('error', '사용법: /route_optimize <delivery_id1,delivery_id2,...>')
    try:
        from ..logistics.route_optimizer import RouteOptimizer, RouteConstraint
        from ..logistics.logistics_models import Coordinate, DeliveryStop
        import uuid as _uuid

        delivery_ids = [d.strip() for d in delivery_ids_str.split(',') if d.strip()]
        optimizer = RouteOptimizer()
        depot = Coordinate(lat=37.5665, lon=126.9780)

        stops = [
            DeliveryStop(
                stop_id=_uuid.uuid4().hex[:8],
                address=f'배송지 {i + 1}',
                coordinate=Coordinate(lat=37.5 + i * 0.01, lon=127.0 + i * 0.01),
                order_id=did,
                weight_kg=2.0,
            )
            for i, did in enumerate(delivery_ids)
        ]

        result = optimizer.optimize(stops, depot, strategy='nearest_neighbor', constraints=RouteConstraint())
        lines = [
            f'• 경로 ID: {result.route_id[:8]}...',
            f'• 정류장 수: {len(result.stops)}개',
            f'• 총 거리: {result.total_distance_km:.1f}km',
            f'• 예상 시간: {result.estimated_duration_min:.0f}분',
            f'• 전략: {result.strategy_used}',
        ]
        return format_message('info', '경로 최적화 완료:\n' + '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_route_optimize 오류: %s", exc)
        return format_message('error', f'경로 최적화 실패: {exc}')


def cmd_delivery_eta(delivery_id: str = '') -> str:
    """/delivery_eta <delivery_id> — 배송 ETA 조회."""
    if not delivery_id.strip():
        return format_message('error', '사용법: /delivery_eta <delivery_id>')
    try:
        from ..logistics.last_mile import LastMileTracker

        tracker = LastMileTracker()
        delivery = tracker.get_delivery(delivery_id.strip())
        if delivery is None:
            return format_message('error', f'배송 없음: {delivery_id}')
        eta = tracker.calculate_eta(delivery_id.strip())
        lines = [
            f'• 배송 ID: {delivery_id[:8]}...',
            f'• 상태: {delivery.status.value}',
            f'• 예상 도착: {eta:.0f}분 후',
            f'• 거리: {delivery.distance_km:.1f}km',
        ]
        return format_message('info', 'ETA 조회:\n' + '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_delivery_eta 오류: %s", exc)
        return format_message('error', f'ETA 조회 실패: {exc}')


def cmd_carrier_recommend(args: str = '') -> str:
    """/carrier_recommend <weight> <region> — 택배사 추천."""
    parts = args.strip().split()
    if len(parts) < 2:
        return format_message('error', '사용법: /carrier_recommend <weight_kg> <region>')
    try:
        from ..logistics.cost_optimizer import CarrierSelector

        weight = float(parts[0])
        region = parts[1]
        selector = CarrierSelector()
        carrier = selector.recommend_carrier(weight, region, priority='cost')
        lines = [
            f'• 택배사: {carrier.name}',
            f'• 기본 요금: {carrier.base_rate:,.0f}원',
            f'• kg당 요금: {carrier.per_kg_rate:,.0f}원',
            f'• 평균 배송일: {carrier.avg_delivery_days}일',
            f'• 신뢰도: {carrier.reliability_score:.0%}',
        ]
        return format_message('info', f'택배사 추천 ({weight}kg, {region}):\n' + '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_carrier_recommend 오류: %s", exc)
        return format_message('error', f'택배사 추천 실패: {exc}')


def cmd_logistics_report() -> str:
    """/logistics_report — 물류 보고서 생성."""
    try:
        from ..logistics.logistics_analytics import LogisticsReport

        report = LogisticsReport()
        daily = report.generate_daily_report()
        weekly = report.generate_weekly_report()
        lines = [
            f'• 오늘 배송: {daily["total_deliveries"]}건',
            f'• 성공률: {daily["success_rate"]:.0%}',
            f'• 이번 주 배송: {weekly["total_deliveries"]}건',
            f'• 주간 성공률: {weekly["success_rate"]:.0%}',
        ]
        return format_message('info', '물류 보고서:\n' + '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_logistics_report 오류: %s", exc)
        return format_message('error', f'보고서 생성 실패: {exc}')


# ── Phase 100: 데이터 파이프라인 봇 커맨드 ──────────────────────────────────────

def cmd_etl_status() -> str:
    """/etl_status — ETL 파이프라인 현황 조회."""
    try:
        from ..data_pipeline.etl_engine import ETLEngine
        engine = ETLEngine()
        pipelines = engine.list_pipelines()
        if not pipelines:
            return format_message('info', 'ETL 파이프라인이 없습니다.')
        lines = [f'• [{p.status.value}] {p.name} (ID: {p.pipeline_id[:8]}...)' for p in pipelines]
        return format_message('info', f'ETL 파이프라인 현황 ({len(pipelines)}개):\n' + '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_etl_status 오류: %s", exc)
        return format_message('error', f'ETL 현황 조회 실패: {exc}')


def cmd_etl_run(pipeline_id: str = '') -> str:
    """/etl_run <pipeline_id> — 파이프라인 실행."""
    if not pipeline_id.strip():
        return format_message('error', '사용법: /etl_run <pipeline_id>')
    try:
        from ..data_pipeline.etl_engine import ETLEngine
        engine = ETLEngine()
        record = engine.run_pipeline(pipeline_id.strip())
        lines = [
            f'• 실행 ID: {record.run_id[:8]}...',
            f'• 상태: {record.status}',
            f'• 처리 행수: {record.rows_processed:,}',
            f'• 시작: {record.started_at}',
            f'• 완료: {record.finished_at}',
        ]
        if record.error:
            lines.append(f'• 오류: {record.error}')
        return format_message('info', '파이프라인 실행 완료:\n' + '\n'.join(lines))
    except KeyError:
        return format_message('error', f'파이프라인 없음: {pipeline_id}')
    except Exception as exc:
        logger.error("cmd_etl_run 오류: %s", exc)
        return format_message('error', f'파이프라인 실행 실패: {exc}')


def cmd_warehouse_tables() -> str:
    """/warehouse_tables — 웨어하우스 테이블 목록."""
    try:
        from ..data_pipeline.data_warehouse import DataWarehouse
        warehouse = DataWarehouse()
        tables = warehouse.list_tables()
        if not tables:
            return format_message('info', '웨어하우스 테이블이 없습니다.')
        stats = warehouse.get_stats()
        lines = [
            f'• 총 테이블: {stats["total_tables"]}개',
            f'• 총 행수: {stats["total_rows"]:,}',
            f'• 용량 (추정): {stats["disk_size_mb"]:.2f}MB',
        ]
        for t in tables:
            lines.append(f'  - {t.table_name}: {t.row_count:,}행')
        return format_message('info', '웨어하우스 테이블 목록:\n' + '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_warehouse_tables 오류: %s", exc)
        return format_message('error', f'테이블 목록 조회 실패: {exc}')


def cmd_data_quality() -> str:
    """/data_quality — 데이터 품질 리포트."""
    try:
        from ..data_pipeline.data_quality import DataQualityChecker, NotNullRule, RangeRule
        checker = DataQualityChecker()
        checker.add_rule(NotNullRule(fields=["id"]))
        checker.add_rule(RangeRule(field="value", min_val=0))
        sample_data = [{"id": str(i), "value": i * 10} for i in range(20)]
        report = checker.check(sample_data, "sample_table")
        lines = [
            f'• 테이블: {report.table_name}',
            f'• 총 행수: {report.total_rows}',
            f'• 통과: {report.passed_rows}',
            f'• 실패: {report.failed_rows}',
            f'• 품질 점수: {report.score:.1f}%',
        ]
        return format_message('info', '데이터 품질 리포트:\n' + '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_data_quality 오류: %s", exc)
        return format_message('error', f'품질 검사 실패: {exc}')


def cmd_etl_dashboard() -> str:
    """/etl_dashboard — ETL 대시보드."""
    try:
        from ..data_pipeline.etl_engine import ETLEngine
        from ..data_pipeline.data_warehouse import DataWarehouse
        from ..data_pipeline.pipeline_monitor import PipelineMonitor, ETLDashboard
        engine = ETLEngine()
        warehouse = DataWarehouse()
        monitor = PipelineMonitor()
        dashboard = ETLDashboard(engine, warehouse, monitor)
        summary = dashboard.get_summary()
        stats = summary.get('warehouse_stats', {})
        lines = [
            f'• 파이프라인: {summary["pipeline_count"]}개',
            f'• 실행 중: {summary["active_pipelines"]}개',
            f'• 총 실행: {summary["total_runs"]}회',
            f'• 성공률: {summary["success_rate"]:.0%}',
            f'• 웨어하우스 테이블: {stats.get("total_tables", 0)}개',
            f'• 총 데이터: {stats.get("total_rows", 0):,}행',
        ]
        return format_message('info', 'ETL 대시보드:\n' + '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_etl_dashboard 오류: %s", exc)
        return format_message('error', f'ETL 대시보드 조회 실패: {exc}')


# ─────────────────────────────────────────────────────────────
# Phase 102: 배송대행지 커맨드
# ─────────────────────────────────────────────────────────────

def cmd_forwarding_status() -> str:
    """/forwarding_status — 전체 배송대행 현황."""
    try:
        from ..forwarding.dashboard import ForwardingDashboard
        from ..forwarding.incoming import IncomingVerifier
        from ..forwarding.consolidation import ConsolidationManager
        from ..forwarding.tracker import ShipmentTracker
        dashboard = ForwardingDashboard(
            verifier=IncomingVerifier(),
            manager=ConsolidationManager(),
            tracker=ShipmentTracker(),
        )
        summary = dashboard.get_summary()
        inc = summary.get('incoming_stats', {})
        ship = summary.get('shipment_stats', {})
        cons = summary.get('consolidation_stats', {})
        lines = [
            f"📦 입고 대기: {inc.get('waiting', 0)}",
            f"✅ 입고 완료: {inc.get('received', 0)}",
            f"🔍 검수 중: {inc.get('inspected', 0)}",
            f"🚢 배송 준비: {inc.get('ready_to_ship', 0)}",
            f"⚠️ 문제 발생: {inc.get('issue_found', 0)}",
            f"🚚 배송 중: {ship.get('in_transit', 0)}",
            f"🏠 배송 완료: {ship.get('delivered', 0)}",
            f"📋 합배송 그룹: {cons.get('total_groups', 0)}",
        ]
        return format_message('info', '배송대행 현황:\n' + '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_forwarding_status 오류: %s", exc)
        return format_message('error', f'배송대행 현황 조회 실패: {exc}')


def cmd_incoming_check(tracking_number: str = '') -> str:
    """/incoming_check <tracking_number> — 입고 확인."""
    if not tracking_number.strip():
        return format_message('error', '사용법: /incoming_check <tracking_number>')
    try:
        from ..forwarding.incoming import IncomingVerifier
        verifier = IncomingVerifier()
        record = verifier.verify(
            order_id=f'order_{tracking_number}',
            tracking_number=tracking_number.strip(),
            agent_id='moltail',
        )
        lines = [
            f"• 트래킹: {record.tracking_number}",
            f"• 상태: {record.status.value}",
            f"• 무게: {record.weight_kg:.2f}kg",
            f"• 입고일: {record.received_at.strftime('%Y-%m-%d %H:%M') if record.received_at else '-'}",
        ]
        if record.issue_type:
            lines.append(f"• 문제: {record.issue_type}")
        return format_message('info', '입고 확인 결과:\n' + '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_incoming_check 오류: %s", exc)
        return format_message('error', f'입고 확인 실패: {exc}')


def cmd_shipping_estimate(weight: str = '', country: str = '') -> str:
    """/shipping_estimate <weight> <country> — 배송비 견적."""
    if not weight.strip() or not country.strip():
        return format_message('error', '사용법: /shipping_estimate <weight_kg> <country>')
    try:
        from ..forwarding.cost_estimator import CostEstimator
        estimator = CostEstimator()
        try:
            w = float(weight.strip())
        except ValueError:
            return format_message('error', f'무게는 숫자여야 합니다: {weight}')
        breakdown = estimator.estimate(w, country.strip().upper(), agent_id='moltail')
        lines = [
            f"• 기본 배송비: ${breakdown.base_shipping_usd:.2f}",
            f"• 유류 할증: ${breakdown.fuel_surcharge_usd:.2f}",
            f"• 보험료: ${breakdown.insurance_usd:.2f}",
            f"• 대행 수수료: ${breakdown.agent_fee_usd:.2f}",
            f"• 관세: ${breakdown.customs_duty_usd:.2f}",
            f"• 부가세: ${breakdown.vat_usd:.2f}",
            f"━━━━━━━━━━━━━━",
            f"• 합계: ${breakdown.total_usd:.2f}",
        ]
        return format_message('info', f'배송비 견적 ({w}kg → {country.upper()}):\n' + '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_shipping_estimate 오류: %s", exc)
        return format_message('error', f'배송비 견적 실패: {exc}')


def cmd_consolidation_list() -> str:
    """/consolidation_list — 합배송 그룹 목록."""
    try:
        from ..forwarding.consolidation import ConsolidationManager
        manager = ConsolidationManager()
        groups = manager.list_groups()
        if not groups:
            return format_message('info', '합배송 그룹이 없습니다.')
        lines = [f'총 {len(groups)}개:']
        for g in groups[:10]:
            lines.append(
                f"• [{g.status.value}] {g.group_id[:8]}... "
                f"({len(g.order_ids)}건, {g.estimated_weight_kg:.1f}kg, "
                f"절감: ${g.savings_usd:.2f})"
            )
        if len(groups) > 10:
            lines.append(f'... 외 {len(groups) - 10}개')
        return format_message('info', '합배송 그룹 목록:\n' + '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_consolidation_list 오류: %s", exc)
        return format_message('error', f'합배송 목록 조회 실패: {exc}')


def cmd_forwarding_dashboard() -> str:
    """/forwarding_dashboard — 배송대행 대시보드 요약."""
    try:
        from ..forwarding.dashboard import ForwardingDashboard
        from ..forwarding.incoming import IncomingVerifier
        from ..forwarding.consolidation import ConsolidationManager
        from ..forwarding.tracker import ShipmentTracker
        from ..forwarding.cost_estimator import CostEstimator
        from ..forwarding.agent import ForwardingAgentManager
        dashboard = ForwardingDashboard(
            verifier=IncomingVerifier(),
            manager=ConsolidationManager(),
            tracker=ShipmentTracker(),
            estimator=CostEstimator(),
            agent_manager=ForwardingAgentManager(),
        )
        summary = dashboard.get_summary()
        agent_stats = dashboard.get_agent_stats()
        lines = [
            f"📊 전체 배송: {summary.get('total_shipments', 0)}건",
        ]
        for ag in agent_stats:
            lines.append(
                f"  • {ag.get('name', ag.get('agent_id', '-'))}: "
                f"신뢰도 {ag.get('reliability', 0):.0%}"
            )
        return format_message('info', '배송대행 대시보드:\n' + '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_forwarding_dashboard 오류: %s", exc)
        return format_message('error', f'대시보드 조회 실패: {exc}')


# ─────────────────────────────────────────────────────────────
# Phase 103: 풀필먼트 커맨드
# ─────────────────────────────────────────────────────────────

def cmd_fulfillment_status() -> str:
    """/fulfillment_status — 전체 풀필먼트 현황."""
    try:
        from ..fulfillment.engine import FulfillmentEngine
        engine = FulfillmentEngine()
        stats = engine.get_stats()
        by_status = stats.get('by_status', {})
        lines = [
            f"📦 입고: {by_status.get('received', 0)}",
            f"🔍 검수 중: {by_status.get('inspecting', 0)}",
            f"📦 포장 중: {by_status.get('packing', 0)}",
            f"✅ 발송 대기: {by_status.get('ready_to_ship', 0)}",
            f"🚀 발송됨: {by_status.get('shipped', 0)}",
            f"🚚 배송 중: {by_status.get('in_transit', 0)}",
            f"🏠 배송 완료: {by_status.get('delivered', 0)}",
        ]
        return format_message('info', '풀필먼트 현황:\n' + '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_fulfillment_status 오류: %s", exc)
        return format_message('error', f'풀필먼트 현황 조회 실패: {exc}')


def cmd_inspect(order_id: str = '') -> str:
    """/inspect <order_id> — 검수 결과 조회."""
    if not order_id.strip():
        return format_message('error', '사용법: /inspect <order_id>')
    try:
        from ..fulfillment.inspection import InspectionService
        svc = InspectionService()
        history = svc.get_history(order_id.strip())
        if not history:
            return format_message('info', f'검수 이력 없음: {order_id}')
        latest = history[-1]
        lines = [
            f"• 주문: {latest.order_id}",
            f"• 등급: {latest.grade.value}",
            f"• 코멘트: {latest.comment}",
            f"• 반품 필요: {'예' if latest.requires_return else '아니오'}",
        ]
        if latest.defect_types:
            lines.append(f"• 불량 유형: {', '.join(latest.defect_types)}")
        return format_message('info', '검수 결과:\n' + '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_inspect 오류: %s", exc)
        return format_message('error', f'검수 결과 조회 실패: {exc}')


def cmd_ship(order_id: str = '') -> str:
    """/ship <order_id> — 발송 요청."""
    if not order_id.strip():
        return format_message('error', '사용법: /ship <order_id>')
    try:
        from ..fulfillment.engine import FulfillmentEngine
        from ..fulfillment.shipping import DomesticShippingManager
        from ..fulfillment.tracking import TrackingNumberManager, DeliveryTracker
        engine = FulfillmentEngine()
        order = engine.get_order(order_id.strip())
        if not order:
            return format_message('error', f'주문을 찾을 수 없습니다: {order_id}')
        shipping_mgr = DomesticShippingManager()
        packing_info = order.packing_result or {}
        package_info = {'weight_kg': packing_info.get('weight_kg', 1.0), 'dimensions_cm': {}}
        shipment = shipping_mgr.ship(order_id=order_id.strip(), recipient=order.recipient, package_info=package_info)
        trk_mgr = TrackingNumberManager()
        trk_mgr.register(order_id=order_id.strip(), tracking_number=shipment['tracking_number'], carrier_id=shipment['carrier_id'])
        lines = [
            f"• 운송장: {shipment['tracking_number']}",
            f"• 택배사: {shipment['carrier_name']}",
        ]
        return format_message('info', f'발송 완료:\n' + '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_ship 오류: %s", exc)
        return format_message('error', f'발송 요청 실패: {exc}')


def cmd_tracking(tracking_number: str = '') -> str:
    """/tracking <tracking_number> — 배송 추적."""
    if not tracking_number.strip():
        return format_message('error', '사용법: /tracking <tracking_number>')
    try:
        from ..fulfillment.shipping import DomesticShippingManager
        mgr = DomesticShippingManager()
        result = mgr.get_tracking(tracking_number.strip())
        lines = [
            f"• 운송장: {result.get('tracking_number', '-')}",
            f"• 상태: {result.get('status', '-')}",
        ]
        events = result.get('events', [])
        if events:
            latest = events[-1]
            lines.append(f"• 최근: {latest.get('location', '-')} — {latest.get('description', '-')}")
        return format_message('info', '배송 추적:\n' + '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_tracking 오류: %s", exc)
        return format_message('error', f'배송 추적 실패: {exc}')


def cmd_fulfillment_dashboard() -> str:
    """/fulfillment_dashboard — 풀필먼트 대시보드 요약."""
    try:
        from ..fulfillment.engine import FulfillmentEngine
        from ..fulfillment.inspection import InspectionService
        from ..fulfillment.packing import PackingService
        from ..fulfillment.shipping import DomesticShippingManager
        from ..fulfillment.tracking import TrackingNumberManager, DeliveryTracker
        from ..fulfillment.dashboard import FulfillmentDashboard
        dashboard = FulfillmentDashboard(
            engine=FulfillmentEngine(),
            inspection_service=InspectionService(),
            packing_service=PackingService(),
            shipping_manager=DomesticShippingManager(),
            tracking_manager=TrackingNumberManager(),
            delivery_tracker=DeliveryTracker(),
        )
        summary = dashboard.get_summary()
        fulf = summary.get('fulfillment_orders', {})
        lines = [
            f"📊 총 주문: {fulf.get('total', 0)}건",
        ]
        proc = dashboard.get_processing_stats()
        lines.append(f"🚚 배송 중: {proc.get('in_transit', 0)}")
        lines.append(f"✅ 완료: {proc.get('delivered', 0)}")
        return format_message('info', '풀필먼트 대시보드:\n' + '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_fulfillment_dashboard 오류: %s", exc)
        return format_message('error', f'대시보드 조회 실패: {exc}')


# ─────────────────────────────────────────────────────────────
# Phase 104: 중국 마켓플레이스 커맨드
# ─────────────────────────────────────────────────────────────

def cmd_china_search(keyword: str = '') -> str:
    """/china_search <keyword> — 중국 상품 검색."""
    if not keyword.strip():
        return format_message('error', '사용법: /china_search <keyword>')
    try:
        from ..china_marketplace.taobao_agent import TaobaoAgent
        from ..china_marketplace.alibaba_agent import Alibaba1688Agent
        tb_results = TaobaoAgent().search(keyword.strip(), max_results=3)
        ali_results = Alibaba1688Agent().search(keyword.strip(), max_results=2)
        lines = [f'🔍 "{keyword}" 검색 결과:']
        lines.append('\n[타오바오]')
        for p in tb_results:
            lines.append(f"• {p.title} — ¥{p.price_cny:.2f}")
        lines.append('\n[1688]')
        for p in ali_results:
            tiers = p.price_tiers
            min_price = tiers[0]['price_cny'] if tiers else 0
            lines.append(f"• {p.title} — ¥{min_price:.2f}~ (MOQ: {p.moq})")
        return format_message('info', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_china_search 오류: %s", exc)
        return format_message('error', f'검색 실패: {exc}')


def cmd_china_buy(url: str = '', quantity: int = 1) -> str:
    """/china_buy <url> [quantity] — 중국 구매 주문."""
    if not url.strip():
        return format_message('error', '사용법: /china_buy <url> [quantity]')
    try:
        qty = int(quantity)
    except (ValueError, TypeError):
        return format_message('error', 'quantity는 정수여야 합니다.')
    try:
        from ..china_marketplace.engine import ChinaMarketplaceEngine
        engine = ChinaMarketplaceEngine()
        parsed_url = url.strip()
        marketplace = '1688' if parsed_url.startswith('https://detail.1688.com') or parsed_url.startswith('https://www.1688.com') else 'taobao'
        order = engine.create_order(
            marketplace=marketplace,
            product_url=parsed_url,
            quantity=qty,
        )
        lines = [
            f"✅ 주문 생성 완료",
            f"• 주문 ID: {order.order_id}",
            f"• 마켓: {order.marketplace}",
            f"• 수량: {order.quantity}",
            f"• 상태: {order.status.value}",
        ]
        return format_message('info', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_china_buy 오류: %s", exc)
        return format_message('error', f'주문 생성 실패: {exc}')


def cmd_china_status(order_id: str = '') -> str:
    """/china_status <order_id> — 주문 상태 확인."""
    if not order_id.strip():
        return format_message('error', '사용법: /china_status <order_id>')
    try:
        from ..china_marketplace.engine import ChinaMarketplaceEngine
        engine = ChinaMarketplaceEngine()
        order = engine.get_order(order_id.strip())
        if not order:
            return format_message('error', f'주문을 찾을 수 없습니다: {order_id}')
        lines = [
            f"📦 주문 상태",
            f"• 주문 ID: {order.order_id}",
            f"• 마켓: {order.marketplace}",
            f"• 상태: {order.status.value}",
            f"• 에이전트: {order.agent or '미배정'}",
        ]
        return format_message('info', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_china_status 오류: %s", exc)
        return format_message('error', f'상태 조회 실패: {exc}')


def cmd_seller_check(seller_id: str = '') -> str:
    """/seller_check <seller_id> — 셀러 검증."""
    if not seller_id.strip():
        return format_message('error', '사용법: /seller_check <seller_id>')
    try:
        from ..china_marketplace.seller_verification import SellerVerificationService
        svc = SellerVerificationService()
        score = svc.verify_seller(seller_id.strip())
        emoji = '✅' if score.recommendation == 'approved' else ('⚠️' if score.recommendation == 'caution' else '❌')
        lines = [
            f"{emoji} 셀러 검증 결과: {seller_id}",
            f"• 신뢰도: {score.reliability:.1f}",
            f"• 품질: {score.quality:.1f}",
            f"• 배송속도: {score.shipping_speed:.1f}",
            f"• 소통: {score.communication:.1f}",
            f"• 종합: {score.overall:.1f}",
            f"• 판정: {score.recommendation}",
        ]
        return format_message('info', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_seller_check 오류: %s", exc)
        return format_message('error', f'셀러 검증 실패: {exc}')


def cmd_china_dashboard() -> str:
    """/china_dashboard — 중국 구매 대시보드."""
    try:
        from ..china_marketplace.engine import ChinaMarketplaceEngine
        from ..china_marketplace.agent_manager import AgentManager
        from ..china_marketplace.seller_verification import SellerVerificationService
        from ..china_marketplace.payment import ChinaPaymentService
        from ..china_marketplace.rpa_controller import RPAController
        from ..china_marketplace.dashboard import ChinaPurchaseDashboard
        dashboard = ChinaPurchaseDashboard(
            engine=ChinaMarketplaceEngine(),
            agent_manager=AgentManager(),
            seller_service=SellerVerificationService(),
            payment_service=ChinaPaymentService(),
            rpa_controller=RPAController(),
        )
        summary = dashboard.get_summary()
        orders = summary.get('orders', {})
        payments = summary.get('payments', {})
        rpa = summary.get('rpa', {})
        lines = [
            '🇨🇳 중국 구매 대시보드',
            f"📦 전체 주문: {orders.get('total', 0)}건",
            f"💳 결제 총액: ¥{payments.get('total_amount_cny', 0):.2f}",
            f"🤖 RPA 작업: {rpa.get('total_tasks', 0)}건 (성공률: {rpa.get('success_rate', 0) * 100:.1f}%)",
        ]
        return format_message('info', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_china_dashboard 오류: %s", exc)
        return format_message('error', f'대시보드 조회 실패: {exc}')



# ── Phase 105: 예외 처리 + 자동 복구 ────────────────────────────────────────

def cmd_exceptions(args_str: str = '') -> str:
    """/exceptions — 현재 예외 현황."""
    try:
        from ..exception_handler.engine import ExceptionEngine
        engine = ExceptionEngine()
        stats = engine.get_stats()
        lines = [
            '🚨 예외 현황',
            f"• 전체: {stats['total']}건",
            f"• 해결: {stats['resolved']}건",
            f"• 해결률: {stats['resolution_rate'] * 100:.1f}%",
        ]
        if stats['by_severity']:
            lines.append('심각도별:')
            for sev, cnt in stats['by_severity'].items():
                lines.append(f'  - {sev}: {cnt}건')
        return format_message('info', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_exceptions 오류: %s", exc)
        return format_message('error', f'예외 현황 조회 실패: {exc}')


def cmd_exception_detail(case_id: str = '') -> str:
    """/exception_detail <case_id> — 예외 상세."""
    if not case_id.strip():
        return format_message('error', '사용법: /exception_detail <case_id>')
    try:
        from ..exception_handler.engine import ExceptionEngine
        engine = ExceptionEngine()
        case = engine.get_case(case_id.strip())
        if not case:
            return format_message('error', f'예외 케이스를 찾을 수 없습니다: {case_id}')
        d = case.to_dict()
        lines = [
            f'🔍 예외 상세: {d["case_id"]}',
            f'• 유형: {d["type"]}',
            f'• 심각도: {d["severity"]}',
            f'• 상태: {d["status"]}',
            f'• 주문: {d["order_id"] or "-"}',
            f'• 감지: {d["detected_at"]}',
            f'• 재시도: {d["retry_count"]}회',
        ]
        if d.get('resolution'):
            lines.append(f'• 해결: {d["resolution"]}')
        return format_message('info', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_exception_detail 오류: %s", exc)
        return format_message('error', f'예외 상세 조회 실패: {exc}')


def cmd_price_alerts(args_str: str = '') -> str:
    """/price_alerts — 가격 알림 목록."""
    try:
        from ..exception_handler.price_detector import PriceChangeDetector
        detector = PriceChangeDetector()
        alerts = detector.list_alerts(acknowledged=False)
        if not alerts:
            return format_message('info', '미확인 가격 알림이 없습니다.')
        lines = ['💰 가격 알림 목록 (미확인)']
        for a in alerts[:10]:
            d = a.to_dict()
            lines.append(
                f'• [{d["alert_type"]}] {d["product_id"]} '
                f'{d["old_price"]:,.0f} → {d["new_price"]:,.0f} ({d["change_percent"]:+.1f}%)'
            )
        return format_message('info', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_price_alerts 오류: %s", exc)
        return format_message('error', f'가격 알림 조회 실패: {exc}')


def cmd_retry(case_id: str = '') -> str:
    """/retry <case_id> — 수동 재시도."""
    if not case_id.strip():
        return format_message('error', '사용법: /retry <case_id>')
    try:
        from ..exception_handler.engine import ExceptionEngine
        engine = ExceptionEngine()
        case = engine.get_case(case_id.strip())
        if not case:
            return format_message('error', f'예외 케이스를 찾을 수 없습니다: {case_id}')
        engine.increment_retry(case.case_id)
        return format_message('info', f'재시도 완료: {case_id} (총 {case.retry_count}회)')
    except Exception as exc:
        logger.error("cmd_retry 오류: %s", exc)
        return format_message('error', f'재시도 실패: {exc}')


def cmd_exception_dashboard() -> str:
    """/exception_dashboard — 예외 대시보드 요약."""
    try:
        from ..exception_handler.engine import ExceptionEngine
        from ..exception_handler.damage_handler import DamageHandler
        from ..exception_handler.price_detector import PriceChangeDetector
        from ..exception_handler.retry_manager import RetryManager
        from ..exception_handler.auto_recovery import AutoRecoveryService
        from ..exception_handler.delay_handler import DeliveryDelayHandler
        from ..exception_handler.payment_failure import PaymentFailureHandler
        from ..exception_handler.dashboard import ExceptionDashboard

        dashboard = ExceptionDashboard(
            engine=ExceptionEngine(),
            damage_handler=DamageHandler(),
            price_detector=PriceChangeDetector(),
            retry_manager=RetryManager(),
            recovery_service=AutoRecoveryService(),
            delay_handler=DeliveryDelayHandler(),
            payment_handler=PaymentFailureHandler(),
        )
        metrics = dashboard.get_resolution_metrics()
        cost = dashboard.get_cost_impact()
        lines = [
            '🛡️ 예외 대시보드',
            f"• 자동 복구율: {metrics['auto_recovery_rate'] * 100:.1f}%",
            f"• 평균 해결시간: {metrics['avg_resolution_hours']:.1f}시간",
            f"• 에스컬레이션율: {metrics['escalation_rate'] * 100:.1f}%",
            f"• 훼손 보상 총액: {cost['damage_compensation']:,.0f}원",
            f"• 복구 비용 총액: {cost['recovery_cost']:,.0f}원",
        ]
        return format_message('info', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_exception_dashboard 오류: %s", exc)
        return format_message('error', f'대시보드 조회 실패: {exc}')


# ─────────────────────────────────────────────────────────────
# Phase 106: 자율 운영 대시보드 커맨드
# ─────────────────────────────────────────────────────────────

def cmd_ops_status() -> str:
    """/ops_status — 운영 상태 요약."""
    try:
        from ..autonomous_ops.engine import AutonomousOperationEngine
        engine = AutonomousOperationEngine()
        status = engine.get_status().to_dict()
        lines = [
            '🤖 자율 운영 상태',
            f"• 모드: {status['mode']}",
            f"• 건강 점수: {status['health_score']:.1f}/100",
            f"• 활성 알림: {status['active_alerts']}건",
            f"• 자동 액션: {status['auto_actions_count']}건",
            f"• 업타임: {status['uptime_seconds']:.0f}초",
        ]
        return format_message('info', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_ops_status 오류: %s", exc)
        return format_message('error', f'운영 상태 조회 실패: {exc}')


def cmd_revenue_today() -> str:
    """/revenue — 오늘 수익 현황."""
    try:
        from ..autonomous_ops.revenue_model import RevenueTracker
        tracker = RevenueTracker()
        daily = tracker.get_daily_revenue()
        total = sum(daily.values())
        lines = ['💰 오늘 수익 현황', f'총 수익: {total:,.0f}원']
        for stream, amount in daily.items():
            if amount > 0:
                lines.append(f'• {stream}: {amount:,.0f}원')
        return format_message('info', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_revenue_today 오류: %s", exc)
        return format_message('error', f'수익 조회 실패: {exc}')


def cmd_anomalies() -> str:
    """/anomalies — 현재 이상 알림."""
    try:
        from ..autonomous_ops.anomaly_detector import AnomalyDetector
        detector = AnomalyDetector()
        active = detector.get_active_alerts()
        if not active:
            return format_message('info', '현재 활성 이상 알림이 없습니다.')
        lines = [f'⚠️ 활성 이상 알림 ({len(active)}건)']
        for a in active[:10]:
            lines.append(
                f"• [{a['severity']}] {a['type']} — {a['metric_name']} "
                f"(편차: {a['deviation_percent']:.1f}%)"
            )
        return format_message('info', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_anomalies 오류: %s", exc)
        return format_message('error', f'이상 알림 조회 실패: {exc}')


def cmd_automation_rate() -> str:
    """/automation_rate — 자동화율."""
    try:
        from ..autonomous_ops.intervention import InterventionTracker
        tracker = InterventionTracker()
        stats = tracker.get_stats()
        coverage = stats['automation_coverage']
        lines = [
            '🤖 자동화율',
            f"• 자동화 커버리지: {coverage * 100:.1f}%",
            f"• 자동 처리: {stats['auto_handled']}건",
            f"• 수동 개입: {stats['manual_interventions']}건",
            f"• 목표 달성: {'✅' if coverage >= 0.95 else '❌'} (목표 95%)",
        ]
        return format_message('info', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_automation_rate 오류: %s", exc)
        return format_message('error', f'자동화율 조회 실패: {exc}')


def cmd_ops_dashboard() -> str:
    """/ops_dashboard — 통합 대시보드 요약."""
    try:
        from ..autonomous_ops.engine import AutonomousOperationEngine
        from ..autonomous_ops.revenue_model import RevenueTracker
        from ..autonomous_ops.anomaly_detector import AnomalyDetector
        from ..autonomous_ops.autopilot import AutoPilotController
        from ..autonomous_ops.intervention import InterventionTracker, ManualTaskQueue
        from ..autonomous_ops.dashboard import UnifiedDashboard

        dashboard = UnifiedDashboard(
            engine=AutonomousOperationEngine(),
            revenue_tracker=RevenueTracker(),
            anomaly_detector=AnomalyDetector(),
            autopilot=AutoPilotController(),
            intervention_tracker=InterventionTracker(),
            task_queue=ManualTaskQueue(),
        )
        metrics = dashboard.get_realtime_metrics()
        lines = [
            '📊 통합 운영 대시보드',
            f"• 오늘 수익: {metrics['revenue_today']:,.0f}원",
            f"• 오늘 이익: {metrics['profit_today']:,.0f}원",
            f"• 마진율: {metrics['margin_rate'] * 100:.1f}%",
            f"• 자동화율: {metrics['automation_rate'] * 100:.1f}%",
            f"• 활성 알림: {metrics['active_alerts']}건",
            f"• 건강 점수: {metrics['health_score']:.1f}/100",
        ]
        return format_message('info', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_ops_dashboard 오류: %s", exc)
        return format_message('error', f'대시보드 조회 실패: {exc}')


def cmd_simulate(scenario: str = '') -> str:
    """/simulate <scenario> — 시나리오 시뮬레이션."""
    if not scenario.strip():
        return format_message('error', '사용법: /simulate <price_crash|demand_surge|supply_disruption|currency_shock|system_failure|competitor_action>')
    try:
        from ..autonomous_ops.simulation import SimulationEngine, ScenarioType
        sim = SimulationEngine()
        scenario_type = ScenarioType(scenario.strip().lower())
        sc = sim.create_scenario(
            name=f'{scenario} 시뮬레이션',
            type=scenario_type,
            parameters={},
        )
        result = sim.run_simulation(sc.scenario_id, {})
        lines = [
            f'🔬 시뮬레이션 결과: {scenario}',
            f"• 수익 영향: {result.revenue_impact:+,.0f}원",
            f"• 비용 영향: {result.cost_impact:+,.0f}원",
            f"• 주문 영향: {result.order_impact:+d}건",
            f"• 위험 점수: {result.risk_score:.1f}/100",
        ]
        for rec in result.recommendations[:2]:
            lines.append(f'💡 {rec}')
        return format_message('info', '\n'.join(lines))
    except ValueError:
        return format_message('error', f'유효하지 않은 시나리오: {scenario}')
    except Exception as exc:
        logger.error("cmd_simulate 오류: %s", exc)
        return format_message('error', f'시뮬레이션 실패: {exc}')


# ─────────────────────────────────────────────────────────────
# Phase 107: 실시간 채팅 고객 지원 커맨드
# ─────────────────────────────────────────────────────────────

def cmd_chat_status() -> str:
    """/chat_status — 채팅 서비스 현황."""
    try:
        from ..live_chat.engine import ChatEngine
        from ..live_chat.websocket_manager import WebSocketManager
        engine = ChatEngine()
        ws = WebSocketManager()
        stats = engine.get_stats()
        ws_status = ws.get_status()
        lines = [
            '💬 채팅 서비스 현황',
            f"• 전체 세션: {stats['total_sessions']}건",
            f"• 온라인 연결: {ws_status['total_connections']}명",
            f"• 온라인 고객: {ws_status['online_customers']}명",
            f"• 온라인 상담원: {ws_status['online_agents']}명",
            f"• 평균 만족도: {stats['average_rating']:.1f}/5.0",
        ]
        by_status = stats.get('by_status', {})
        if by_status:
            lines.append('\n상태별:')
            for status, count in by_status.items():
                lines.append(f"  • {status}: {count}건")
        return format_message('info', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_chat_status 오류: %s", exc)
        return format_message('error', f'채팅 현황 조회 실패: {exc}')


def cmd_chat_queue() -> str:
    """/chat_queue — 대기열 현황."""
    try:
        from ..live_chat.agent_assignment import AgentAssignmentService
        service = AgentAssignmentService()
        queue = service.get_queue()
        stats = service.get_stats()
        lines = [
            '🔢 채팅 대기열 현황',
            f"• 대기 고객 수: {len(queue)}명",
            f"• 가용 상담원: {stats['available']}명",
            f"• 총 상담원: {stats['total_agents']}명",
        ]
        if queue:
            lines.append('\n대기 목록 (최대 5개):')
            for i, entry in enumerate(queue[:5], 1):
                vip = ' [VIP]' if entry.is_vip else ''
                lines.append(f"  {i}. 고객 {entry.customer_id}{vip}")
        return format_message('info', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_chat_queue 오류: %s", exc)
        return format_message('error', f'대기열 조회 실패: {exc}')


def cmd_agent_status() -> str:
    """/agent_status — 상담원 현황."""
    try:
        from ..live_chat.agent_assignment import AgentAssignmentService
        service = AgentAssignmentService()
        stats = service.get_stats()
        agents = service.list_agents()
        lines = [
            '🎧 상담원 현황',
            f"• 전체: {stats['total_agents']}명",
            f"• 온라인: {stats['available']}명",
            f"• 바쁨: {stats['busy']}명",
            f"• 자리비움: {stats['away']}명",
            f"• 오프라인: {stats['offline']}명",
            f"• 진행 중 세션: {stats['total_current_sessions']}건",
        ]
        if agents:
            lines.append('\n상담원 목록 (최대 5명):')
            for a in agents[:5]:
                available_icon = '✅' if a.is_available else '❌'
                lines.append(
                    f"  {available_icon} {a.name} "
                    f"({a.current_sessions}/{a.max_sessions})"
                )
        return format_message('info', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_agent_status 오류: %s", exc)
        return format_message('error', f'상담원 현황 조회 실패: {exc}')


def cmd_chat_stats() -> str:
    """/chat_stats — 채팅 통계."""
    try:
        from ..live_chat.engine import ChatEngine
        from ..live_chat.auto_reply import AutoReplyService
        from ..live_chat.history import ChatHistoryManager
        engine = ChatEngine()
        auto_reply = AutoReplyService()
        history = ChatHistoryManager()
        stats = engine.get_stats()
        faq_stats = auto_reply.get_stats()
        hist_stats = history.get_stats()
        lines = [
            '📊 채팅 통계',
            f"• 전체 세션: {stats['total_sessions']}건",
            f"• 평균 만족도: {stats['average_rating']:.1f}/5.0",
            f"• 평가된 세션: {stats['rated_sessions']}건",
            f"• FAQ 항목: {faq_stats['total_faqs']}개",
            f"• FAQ 조회 수: {faq_stats['total_hits']}회",
            f"• 이력 저장: {hist_stats['total_sessions']}건",
            f"• 평균 메시지 수: {hist_stats['average_messages_per_session']:.1f}개",
        ]
        return format_message('info', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_chat_stats 오류: %s", exc)
        return format_message('error', f'채팅 통계 조회 실패: {exc}')


def cmd_chat_dashboard() -> str:
    """/chat_dashboard — 채팅 대시보드 요약."""
    try:
        from ..live_chat.engine import ChatEngine
        from ..live_chat.agent_assignment import AgentAssignmentService
        from ..live_chat.analytics import ChatAnalytics
        engine = ChatEngine()
        assignment = AgentAssignmentService()
        analytics = ChatAnalytics()
        queue = assignment.get_queue()
        agent_stats = assignment.get_stats()
        session_stats = engine.get_stats()
        perf = analytics.get_performance_metrics()
        lines = [
            '📱 채팅 대시보드',
            f"• 전체 세션: {session_stats['total_sessions']}건",
            f"• 대기 고객: {len(queue)}명",
            f"• 가용 상담원: {agent_stats['available']}명",
            f"• 평균 만족도: {session_stats['average_rating']:.1f}/5.0",
            f"• 평균 첫 응답: {perf['avg_first_response_seconds']:.0f}초",
            f"• 평균 해결 시간: {perf['avg_resolution_seconds']:.0f}초",
        ]
        return format_message('info', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_chat_dashboard 오류: %s", exc)
        return format_message('error', f'대시보드 조회 실패: {exc}')


# ─────────────────────────────────────────────────────────────────────────────
# Phase 108: 소싱처 실시간 모니터링 커맨드
# ─────────────────────────────────────────────────────────────────────────────

def cmd_source_status() -> str:
    """/source_status — 소싱처 모니터링 현황."""
    try:
        from ..source_monitor.engine import SourceMonitorEngine
        from ..source_monitor.change_detector import ChangeDetector
        engine = SourceMonitorEngine()
        detector = ChangeDetector()
        summary = engine.get_summary()
        event_stats = detector.get_stats()
        lines = [
            '🔍 소싱처 모니터링 현황',
            f"• 전체 소싱 상품: {summary['total']}개",
            f"• 활성: {summary['active']}개",
            f"• 문제: {summary['problem']}개",
            f"• 비활성: {summary['inactive']}개",
            f"• 변동 이벤트: {event_stats['total']}건",
        ]
        by_type = summary.get('by_source_type', {})
        if by_type:
            lines.append('\n마켓플레이스별:')
            for k, v in by_type.items():
                lines.append(f"  • {k}: {v}개")
        return format_message('info', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_source_status 오류: %s", exc)
        return format_message('error', f'소싱처 현황 조회 실패: {exc}')


def cmd_source_check(product_id: str) -> str:
    """/source_check <product_id> — 특정 상품 즉시 체크."""
    try:
        from ..source_monitor.engine import SourceMonitorEngine
        engine = SourceMonitorEngine()
        result = engine.run_check(product_id)
        if 'error' in result:
            return format_message('error', f"상품 없음: {product_id}")
        cr = result.get('check_result', {})
        events = result.get('events', [])
        lines = [
            f'🔎 상품 체크: {product_id}',
            f"• 생존 여부: {'✅ 활성' if cr.get('is_alive') else '❌ 삭제/오류'}",
            f"• 현재 가격: {cr.get('price', '-')}",
            f"• 재고 상태: {cr.get('stock_status', '-')}",
            f"• 판매자 활성: {'✅' if cr.get('seller_active') else '❌'}",
            f"• 변동 감지: {len(events)}건",
        ]
        return format_message('info', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_source_check 오류: %s", exc)
        return format_message('error', f'상품 체크 실패: {exc}')


def cmd_source_alerts() -> str:
    """/source_alerts — 현재 변동 알림."""
    try:
        from ..source_monitor.change_detector import ChangeDetector
        detector = ChangeDetector()
        events = detector.get_events()
        critical = detector.get_critical_events()
        lines = [
            '🚨 소싱처 변동 알림',
            f"• 전체 변동: {len(events)}건",
            f"• 긴급 변동: {len(critical)}건",
        ]
        if critical:
            lines.append('\n긴급 변동 (최대 5건):')
            for e in critical[:5]:
                ct = e.change_type.value if hasattr(e.change_type, 'value') else str(e.change_type)
                lines.append(f"  ⚠️ {e.source_product_id}: {ct}")
        return format_message('info', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_source_alerts 오류: %s", exc)
        return format_message('error', f'변동 알림 조회 실패: {exc}')


def cmd_source_dead() -> str:
    """/source_dead — 비활성화된 상품 목록."""
    try:
        from ..source_monitor.auto_deactivation import AutoDeactivationService
        svc = AutoDeactivationService()
        records = svc.list_deactivated()
        lines = [
            '❌ 비활성화된 상품',
            f"• 비활성화 수: {len(records)}건",
        ]
        if records:
            lines.append('\n목록 (최대 5개):')
            for r in records[:5]:
                action = r.action_taken.value if hasattr(r.action_taken, 'value') else str(r.action_taken)
                lines.append(f"  • {r.source_product_id} — {r.reason[:40]} [{action}]")
        return format_message('info', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_source_dead 오류: %s", exc)
        return format_message('error', f'비활성화 목록 조회 실패: {exc}')


def cmd_source_alternatives(product_id: str) -> str:
    """/source_alternatives <product_id> — 대체 소싱처 조회."""
    try:
        from ..source_monitor.engine import SourceMonitorEngine
        from ..source_monitor.alternative_finder import AlternativeSourceFinder
        engine = SourceMonitorEngine()
        finder = AlternativeSourceFinder()
        product = engine.get_product(product_id)
        if not product:
            return format_message('error', f"상품 없음: {product_id}")
        alternatives = finder.find_alternatives(product)
        lines = [
            f'🔄 대체 소싱처: {product_id}',
            f"• 발견: {len(alternatives)}개",
        ]
        for a in alternatives[:5]:
            st = a.source_type.value if hasattr(a.source_type, 'value') else str(a.source_type)
            lines.append(
                f"  • [{st}] 가격: {a.price} | 점수: {a.match_score:.1f} | 배송: {a.estimated_delivery_days}일"
            )
        return format_message('info', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_source_alternatives 오류: %s", exc)
        return format_message('error', f'대체 소싱처 조회 실패: {exc}')


def cmd_source_dashboard() -> str:
    """/source_dashboard — 모니터링 대시보드."""
    try:
        from ..source_monitor.engine import SourceMonitorEngine
        from ..source_monitor.change_detector import ChangeDetector
        from ..source_monitor.auto_deactivation import AutoDeactivationService
        from ..source_monitor.scheduler import SourceMonitorScheduler
        from ..source_monitor.dashboard import SourceMonitorDashboard
        engine = SourceMonitorEngine()
        detector = ChangeDetector()
        deactivation_svc = AutoDeactivationService()
        scheduler = SourceMonitorScheduler()
        dashboard = SourceMonitorDashboard(engine, detector, deactivation_svc, scheduler)
        data = dashboard.get_dashboard()
        summary = data.get('summary', {})
        lines = [
            '📊 소싱처 모니터링 대시보드',
            f"• 전체 소싱 상품: {summary.get('total', 0)}개",
            f"• 활성: {summary.get('active', 0)}개",
            f"• 문제: {summary.get('problem', 0)}개",
            f"• 긴급 변동: {data.get('critical_events_count', 0)}건",
            f"• 비활성화: {data.get('deactivated_count', 0)}건",
            f"• 체크 성공률: {data.get('check_success_rate', 100.0):.1f}%",
            f"• 자동 처리: {data.get('auto_processed', 0)}건",
            f"• 수동 필요: {data.get('manual_required', 0)}건",
        ]
        return format_message('info', '\n'.join(lines))
    except Exception as exc:
        logger.error("cmd_source_dashboard 오류: %s", exc)
        return format_message('error', f'대시보드 조회 실패: {exc}')


# ── Phase 111: 경쟁사 가격 모니터링 ──────────────────────────────────────────

def cmd_competitors(sku: str) -> str:
    """/competitors <sku> — 특정 상품의 경쟁사 목록 + 가격 비교."""
    try:
        from .competitor_pricing_commands import cmd_competitors as _cmd
        return _cmd(sku)
    except Exception as exc:
        logger.error("cmd_competitors 오류: %s", exc)
        return format_message('error', f'경쟁사 조회 실패: {exc}')


def cmd_price_position(sku: str = '') -> str:
    """/price_position [sku] — 가격 포지션 분석."""
    try:
        from .competitor_pricing_commands import cmd_price_position as _cmd
        return _cmd(sku)
    except Exception as exc:
        logger.error("cmd_price_position 오류: %s", exc)
        return format_message('error', f'포지션 분석 실패: {exc}')


def cmd_price_suggest(sku: str = '') -> str:
    """/price_suggest [sku] — 가격 조정 제안."""
    try:
        from .competitor_pricing_commands import cmd_price_suggest as _cmd
        return _cmd(sku)
    except Exception as exc:
        logger.error("cmd_price_suggest 오류: %s", exc)
        return format_message('error', f'가격 제안 실패: {exc}')


def cmd_competitor_alerts() -> str:
    """/competitor_alerts — 경쟁사 알림 현황."""
    try:
        from .competitor_pricing_commands import cmd_competitor_alerts as _cmd
        return _cmd()
    except Exception as exc:
        logger.error("cmd_competitor_alerts 오류: %s", exc)
        return format_message('error', f'경쟁사 알림 조회 실패: {exc}')


def cmd_competitor_dashboard() -> str:
    """/competitor_dashboard — 경쟁사 대시보드 요약."""
    try:
        from .competitor_pricing_commands import cmd_competitor_dashboard as _cmd
        return _cmd()
    except Exception as exc:
        logger.error("cmd_competitor_dashboard 오류: %s", exc)
        return format_message('error', f'대시보드 조회 실패: {exc}')


def cmd_price_war() -> str:
    """/price_war — 가격 전쟁 감지."""
    try:
        from .competitor_pricing_commands import cmd_price_war as _cmd
        return _cmd()
    except Exception as exc:
        logger.error("cmd_price_war 오류: %s", exc)
        return format_message('error', f'가격 전쟁 감지 실패: {exc}')


def cmd_competitor_find(sku: str) -> str:
    """/competitor_find <sku> — 경쟁사 자동 검색."""
    try:
        from .competitor_pricing_commands import cmd_competitor_find as _cmd
        return _cmd(sku)
    except Exception as exc:
        logger.error("cmd_competitor_find 오류: %s", exc)
        return format_message('error', f'경쟁사 검색 실패: {exc}')


def cmd_price_rules() -> str:
    """/price_rules — 가격 규칙 목록."""
    try:
        from .competitor_pricing_commands import cmd_price_rules as _cmd
        return _cmd()
    except Exception as exc:
        logger.error("cmd_price_rules 오류: %s", exc)
        return format_message('error', f'규칙 조회 실패: {exc}')


# ── Phase 112: 주문 매칭 + 이행 가능성 확인 ───────────────────────────────────

def cmd_match_order(order_id: str) -> str:
    """/match_order <order_id> — 주문 소싱처 매칭 실행."""
    try:
        from .order_matching_commands import cmd_match_order as _cmd
        return _cmd(order_id)
    except Exception as exc:
        logger.error("cmd_match_order 오류: %s", exc)
        return format_message('error', f'매칭 실패: {exc}')


def cmd_match_status(order_id: str) -> str:
    """/match_status <order_id> — 주문 매칭 결과 조회."""
    try:
        from .order_matching_commands import cmd_match_status as _cmd
        return _cmd(order_id)
    except Exception as exc:
        logger.error("cmd_match_status 오류: %s", exc)
        return format_message('error', f'조회 실패: {exc}')


def cmd_fulfillment_check(order_id: str) -> str:
    """/fulfillment_check <order_id> — 이행 가능성 확인."""
    try:
        from .order_matching_commands import cmd_fulfillment_check as _cmd
        return _cmd(order_id)
    except Exception as exc:
        logger.error("cmd_fulfillment_check 오류: %s", exc)
        return format_message('error', f'이행 확인 실패: {exc}')


def cmd_fulfillment_risk(order_id: str = '') -> str:
    """/fulfillment_risk [order_id] — 주문 리스크 평가."""
    try:
        from .order_matching_commands import cmd_fulfillment_risk as _cmd
        return _cmd(order_id)
    except Exception as exc:
        logger.error("cmd_fulfillment_risk 오류: %s", exc)
        return format_message('error', f'리스크 평가 실패: {exc}')


def cmd_sla_status(order_id: str = '') -> str:
    """/sla_status [order_id] — SLA 현황."""
    try:
        from .order_matching_commands import cmd_sla_status as _cmd
        return _cmd(order_id)
    except Exception as exc:
        logger.error("cmd_sla_status 오류: %s", exc)
        return format_message('error', f'SLA 조회 실패: {exc}')


def cmd_sla_overdue() -> str:
    """/sla_overdue — SLA 초과 주문 목록."""
    try:
        from .order_matching_commands import cmd_sla_overdue as _cmd
        return _cmd()
    except Exception as exc:
        logger.error("cmd_sla_overdue 오류: %s", exc)
        return format_message('error', f'SLA 초과 조회 실패: {exc}')


def cmd_source_priority(product_id: str) -> str:
    """/source_priority <product_id> — 소싱처 우선순위 조회."""
    try:
        from .order_matching_commands import cmd_source_priority as _cmd
        return _cmd(product_id)
    except Exception as exc:
        logger.error("cmd_source_priority 오류: %s", exc)
        return format_message('error', f'우선순위 조회 실패: {exc}')


def cmd_matching_dashboard() -> str:
    """/matching_dashboard — 매칭 대시보드 요약."""
    try:
        from .order_matching_commands import cmd_matching_dashboard as _cmd
        return _cmd()
    except Exception as exc:
        logger.error("cmd_matching_dashboard 오류: %s", exc)
        return format_message('error', f'대시보드 조회 실패: {exc}')


def cmd_unfulfillable() -> str:
    """/unfulfillable — 이행 불가 상품 목록."""
    try:
        from .order_matching_commands import cmd_unfulfillable as _cmd
        return _cmd()
    except Exception as exc:
        logger.error("cmd_unfulfillable 오류: %s", exc)
        return format_message('error', f'이행 불가 조회 실패: {exc}')


def cmd_high_risk_orders() -> str:
    """/high_risk_orders — 고위험 주문 목록."""
    try:
        from .order_matching_commands import cmd_high_risk_orders as _cmd
        return _cmd()
    except Exception as exc:
        logger.error("cmd_high_risk_orders 오류: %s", exc)
        return format_message('error', f'고위험 주문 조회 실패: {exc}')


# ── Phase 113: 가상 재고 ───────────────────────────────────────────────────────

def cmd_vstock(sku: str) -> str:
    """/vstock <sku> — 상품 가상 재고 조회."""
    try:
        from .virtual_inventory_commands import cmd_vstock as _cmd
        return _cmd(sku)
    except Exception as exc:
        logger.error("cmd_vstock 오류: %s", exc)
        return format_message('error', f'조회 실패: {exc}')


def cmd_vstock_all() -> str:
    """/vstock_all — 전체 가상 재고 요약."""
    try:
        from .virtual_inventory_commands import cmd_vstock_all as _cmd
        return _cmd()
    except Exception as exc:
        logger.error("cmd_vstock_all 오류: %s", exc)
        return format_message('error', f'조회 실패: {exc}')


def cmd_vstock_low() -> str:
    """/vstock_low — 재고 부족 상품 목록."""
    try:
        from .virtual_inventory_commands import cmd_vstock_low as _cmd
        return _cmd()
    except Exception as exc:
        logger.error("cmd_vstock_low 오류: %s", exc)
        return format_message('error', f'조회 실패: {exc}')


def cmd_vstock_out() -> str:
    """/vstock_out — 재고 소진 상품 목록."""
    try:
        from .virtual_inventory_commands import cmd_vstock_out as _cmd
        return _cmd()
    except Exception as exc:
        logger.error("cmd_vstock_out 오류: %s", exc)
        return format_message('error', f'조회 실패: {exc}')


def cmd_vstock_alerts() -> str:
    """/vstock_alerts — 재고 알림 목록."""
    try:
        from .virtual_inventory_commands import cmd_vstock_alerts as _cmd
        return _cmd()
    except Exception as exc:
        logger.error("cmd_vstock_alerts 오류: %s", exc)
        return format_message('error', f'알림 조회 실패: {exc}')


def cmd_vstock_reserve(sku: str, qty: str) -> str:
    """/vstock_reserve <sku> <qty> — 재고 예약."""
    try:
        from .virtual_inventory_commands import cmd_vstock_reserve as _cmd
        return _cmd(sku, qty)
    except Exception as exc:
        logger.error("cmd_vstock_reserve 오류: %s", exc)
        return format_message('error', f'예약 실패: {exc}')


def cmd_vstock_allocate(sku: str, qty: str) -> str:
    """/vstock_allocate <sku> <qty> — 소싱처 할당."""
    try:
        from .virtual_inventory_commands import cmd_vstock_allocate as _cmd
        return _cmd(sku, qty)
    except Exception as exc:
        logger.error("cmd_vstock_allocate 오류: %s", exc)
        return format_message('error', f'할당 실패: {exc}')


def cmd_vstock_sync() -> str:
    """/vstock_sync — 채널 재고 동기화."""
    try:
        from .virtual_inventory_commands import cmd_vstock_sync as _cmd
        return _cmd()
    except Exception as exc:
        logger.error("cmd_vstock_sync 오류: %s", exc)
        return format_message('error', f'동기화 실패: {exc}')


def cmd_vstock_health() -> str:
    """/vstock_health — 재고 건강도."""
    try:
        from .virtual_inventory_commands import cmd_vstock_health as _cmd
        return _cmd()
    except Exception as exc:
        logger.error("cmd_vstock_health 오류: %s", exc)
        return format_message('error', f'건강도 조회 실패: {exc}')


def cmd_vstock_risk() -> str:
    """/vstock_risk — 단일 소싱처 위험 상품."""
    try:
        from .virtual_inventory_commands import cmd_vstock_risk as _cmd
        return _cmd()
    except Exception as exc:
        logger.error("cmd_vstock_risk 오류: %s", exc)
        return format_message('error', f'위험 조회 실패: {exc}')


def cmd_vstock_dashboard() -> str:
    """/vstock_dashboard — 가상 재고 대시보드."""
    try:
        from .virtual_inventory_commands import cmd_vstock_dashboard as _cmd
        return _cmd()
    except Exception as exc:
        logger.error("cmd_vstock_dashboard 오류: %s", exc)
        return format_message('error', f'대시보드 조회 실패: {exc}')


# ── Phase 114: 셀러 성과 리포트 ───────────────────────────────────────────────

def cmd_my_report(report_type: str = 'daily') -> str:
    """/my_report [daily|weekly|monthly] — 리포트 생성 + 텔레그램 발송."""
    try:
        from .seller_report_commands import cmd_my_report as _cmd
        return _cmd(report_type)
    except Exception as exc:
        logger.error("cmd_my_report 오류: %s", exc)
        return format_message('error', f'리포트 생성 실패: {exc}')


def cmd_daily_summary() -> str:
    """/daily_summary — 오늘 매출/주문/마진 요약."""
    try:
        from .seller_report_commands import cmd_daily_summary as _cmd
        return _cmd()
    except Exception as exc:
        logger.error("cmd_daily_summary 오류: %s", exc)
        return format_message('error', f'일간 요약 실패: {exc}')


def cmd_product_rank(direction: str = 'top', n: int = 5) -> str:
    """/product_rank [top|bottom] [N] — 상품 수익성 순위."""
    try:
        from .seller_report_commands import cmd_product_rank as _cmd
        return _cmd(direction, int(n))
    except Exception as exc:
        logger.error("cmd_product_rank 오류: %s", exc)
        return format_message('error', f'상품 순위 조회 실패: {exc}')


def cmd_channel_compare() -> str:
    """/channel_compare — 채널별 성과 비교."""
    try:
        from .seller_report_commands import cmd_channel_compare as _cmd
        return _cmd()
    except Exception as exc:
        logger.error("cmd_channel_compare 오류: %s", exc)
        return format_message('error', f'채널 비교 실패: {exc}')


def cmd_source_rank() -> str:
    """/source_rank — 소싱처 성과 순위."""
    try:
        from .seller_report_commands import cmd_source_rank as _cmd
        return _cmd()
    except Exception as exc:
        logger.error("cmd_source_rank 오류: %s", exc)
        return format_message('error', f'소싱처 순위 조회 실패: {exc}')


def cmd_hybrid_suggest() -> str:
    """/hybrid_suggest — 사입 전환 추천 상품."""
    try:
        from .seller_report_commands import cmd_hybrid_suggest as _cmd
        return _cmd()
    except Exception as exc:
        logger.error("cmd_hybrid_suggest 오류: %s", exc)
        return format_message('error', f'사입 추천 조회 실패: {exc}')


def cmd_hybrid_invest() -> str:
    """/hybrid_invest — 사입 전환 투자금 추정."""
    try:
        from .seller_report_commands import cmd_hybrid_invest as _cmd
        return _cmd()
    except Exception as exc:
        logger.error("cmd_hybrid_invest 오류: %s", exc)
        return format_message('error', f'투자금 추정 실패: {exc}')


def cmd_performance_alerts() -> str:
    """/performance_alerts — 성과 알림 현황."""
    try:
        from .seller_report_commands import cmd_performance_alerts as _cmd
        return _cmd()
    except Exception as exc:
        logger.error("cmd_performance_alerts 오류: %s", exc)
        return format_message('error', f'알림 조회 실패: {exc}')


def cmd_dead_stock() -> str:
    """/dead_stock — 장기 미판매 상품."""
    try:
        from .seller_report_commands import cmd_dead_stock as _cmd
        return _cmd()
    except Exception as exc:
        logger.error("cmd_dead_stock 오류: %s", exc)
        return format_message('error', f'장기 미판매 조회 실패: {exc}')


def cmd_trending_products() -> str:
    """/trending_products — 판매 급상승 상품."""
    try:
        from .seller_report_commands import cmd_trending_products as _cmd
        return _cmd()
    except Exception as exc:
        logger.error("cmd_trending_products 오류: %s", exc)
        return format_message('error', f'급상승 상품 조회 실패: {exc}')


def cmd_my_goals() -> str:
    """/my_goals — 목표 진행률."""
    try:
        from .seller_report_commands import cmd_my_goals as _cmd
        return _cmd()
    except Exception as exc:
        logger.error("cmd_my_goals 오류: %s", exc)
        return format_message('error', f'목표 조회 실패: {exc}')


def cmd_seller_dashboard() -> str:
    """/seller_dashboard — 종합 대시보드 요약."""
    try:
        from .seller_report_commands import cmd_seller_dashboard as _cmd
        return _cmd()
    except Exception as exc:
        logger.error("cmd_seller_dashboard 오류: %s", exc)
        return format_message('error', f'대시보드 조회 실패: {exc}')


def cmd_delivery_watch(args: str = '') -> str:
    """/delivery_watch <order_id> <tracking_no> <carrier> — 배송 추적 등록."""
    parts = args.strip().split()
    if len(parts) < 3:
        return format_message('error', '사용법: /delivery_watch <order_id> <tracking_no> <carrier>')
    order_id, tracking_no, carrier = parts[0], parts[1], parts[2]
    try:
        from ..delivery_notifications.status_watcher import DeliveryStatusWatcher
        watcher = DeliveryStatusWatcher()
        entry = watcher.register(tracking_no, carrier, order_id, user_id='bot_user')
        return format_message('tracking', {'tracking_no': entry.tracking_no, 'carrier': entry.carrier, 'order_id': entry.order_id, 'status': '등록됨'})
    except Exception as exc:
        logger.error("cmd_delivery_watch 오류: %s", exc)
        return format_message('error', f'배송 추적 등록 실패: {exc}')


def cmd_delivery_status(tracking_no: str = '') -> str:
    """/delivery_status <tracking_no> — 배송 상태 조회."""
    tn = tracking_no.strip()
    if not tn:
        return format_message('error', '사용법: /delivery_status <tracking_no>')
    try:
        from ..shipping.tracker import ShipmentTracker
        tracker = ShipmentTracker()
        record = tracker.get_status(tn)
        if record is None:
            return format_message('error', f'등록되지 않은 운송장: {tn}')
        return format_message('tracking', record)
    except Exception as exc:
        logger.error("cmd_delivery_status 오류: %s", exc)
        return format_message('error', f'배송 상태 조회 실패: {exc}')


def cmd_delivery_prefs(user_id: str = '') -> str:
    """/delivery_prefs — 본인 알림 설정 조회/변경."""
    uid = user_id.strip() or 'bot_user'
    try:
        from ..delivery_notifications.customer_preferences import CustomerPreferenceManager
        mgr = CustomerPreferenceManager()
        pref = mgr.get(uid)
        data = {
            'user_id': pref.user_id,
            'channels': pref.channels,
            'language': pref.language,
            'quiet_hours': f'{pref.quiet_hours_start}~{pref.quiet_hours_end}',
            'frequency': pref.frequency,
        }
        return format_message('order_alerts', data, label='알림 설정')
    except Exception as exc:
        logger.error("cmd_delivery_prefs 오류: %s", exc)
        return format_message('error', f'알림 설정 조회 실패: {exc}')


def cmd_delivery_anomalies() -> str:
    """/delivery_anomalies — 운영자용 감지된 지연/예외 목록."""
    try:
        from ..delivery_notifications.delay_detector import DeliveryDelayDetector
        detector = DeliveryDelayDetector()
        anomalies = detector.get_all_anomalies()
        data = [
            {
                'tracking_no': a.tracking_no,
                'type': a.anomaly_type,
                'severity': a.severity,
                'detected_at': a.detected_at,
                'order_id': a.order_id,
            }
            for a in anomalies
        ]
        return format_message('order_alerts', data, label='배송 이상')
    except Exception as exc:
        logger.error("cmd_delivery_anomalies 오류: %s", exc)
        return format_message('error', f'배송 이상 조회 실패: {exc}')


# ── Phase 118: 반품/교환 자동 처리 봇 커맨드 ────────────────────────────────


def cmd_return_request(args: str = '') -> str:
    """/return_request <order_id> <reason_code> — 반품 요청 접수 (Phase 118)."""
    parts = args.strip().split()
    if len(parts) < 2:
        return format_message('error', '사용법: /return_request <order_id> <reason_code>')
    order_id, reason_code = parts[0], parts[1]
    try:
        from ..returns_automation.automation_manager import ReturnsAutomationManager
        mgr = ReturnsAutomationManager()
        req = mgr.submit_request(
            order_id=order_id,
            user_id='bot_user',
            items=[{'sku': 'UNKNOWN', 'product_name': '봇 요청 상품', 'quantity': 1, 'unit_price': 0}],
            reason_code=reason_code,
            reason_text=f'봇 커맨드 반품 요청: {reason_code}',
        )
        data = req.to_dict()
        return format_message('returns', [data], label=f'반품 접수: {req.request_id}')
    except Exception as exc:
        logger.error("cmd_return_request 오류: %s", exc)
        return format_message('error', f'반품 요청 실패: {exc}')


def cmd_return_status(request_id: str = '') -> str:
    """/return_status <request_id> — 반품/교환 요청 상태 조회 (Phase 118)."""
    rid = request_id.strip()
    if not rid:
        return format_message('error', '사용법: /return_status <request_id>')
    try:
        from ..returns_automation.automation_manager import ReturnsAutomationManager
        mgr = ReturnsAutomationManager()
        data = mgr.get_status(rid)
        if data is None:
            return format_message('error', f'요청을 찾을 수 없습니다: {rid}')
        return format_message('returns', [data], label=f'반품 상태: {rid}')
    except Exception as exc:
        logger.error("cmd_return_status 오류: %s", exc)
        return format_message('error', f'반품 상태 조회 실패: {exc}')


def cmd_return_approve_auto(request_id: str = '') -> str:
    """/return_approve_auto <request_id> — 반품 요청 수동 승인 (관리자, Phase 118)."""
    rid = request_id.strip()
    if not rid:
        return format_message('error', '사용법: /return_approve_auto <request_id>')
    try:
        from ..returns_automation.automation_manager import ReturnsAutomationManager
        mgr = ReturnsAutomationManager()
        req = mgr.approve(rid, notes='관리자 봇 승인')
        data = req.to_dict()
        return format_message('returns', [data], label=f'승인 완료: {rid}')
    except KeyError:
        return format_message('error', f'요청을 찾을 수 없습니다: {rid}')
    except Exception as exc:
        logger.error("cmd_return_approve_auto 오류: %s", exc)
        return format_message('error', f'반품 승인 실패: {exc}')


def cmd_return_metrics() -> str:
    """/return_metrics — 반품/교환 자동화 메트릭 조회 (Phase 118)."""
    try:
        from ..returns_automation.automation_manager import ReturnsAutomationManager
        mgr = ReturnsAutomationManager()
        data = mgr.metrics()
        return format_message('analytics', data, label='반품/교환 자동화 메트릭')
    except Exception as exc:
        logger.error("cmd_return_metrics 오류: %s", exc)
        return format_message('error', f'반품 메트릭 조회 실패: {exc}')


# ── Phase 119: 정산/회계 자동화 봇 커맨드 ─────────────────────────────────────


def cmd_finance_close(period_type: str = 'daily') -> str:
    """/finance_close <daily|weekly|monthly> — 회계 기간 마감 (Phase 119)."""
    pt = period_type.strip().lower() or 'daily'
    try:
        from ..finance_automation.automation_manager import FinanceAutomationManager
        mgr = FinanceAutomationManager()
        if pt == 'daily':
            close = mgr.run_daily_close()
        elif pt == 'weekly':
            close = mgr.run_weekly_close()
        elif pt == 'monthly':
            close = mgr.run_monthly_close()
        else:
            return format_message('error', f'지원하지 않는 기간 유형: {pt}')
        data = {
            'period': close.period,
            'type': close.type,
            'status': close.status,
            'closed_at': close.closed_at,
        }
        return format_message('analytics', data, label=f'기간 마감 완료: {close.type} {close.period}')
    except Exception as exc:
        logger.error("cmd_finance_close 오류: %s", exc)
        return format_message('error', f'기간 마감 실패: {exc}')


def cmd_finance_pnl(period: str = '') -> str:
    """/finance_pnl <period> — 손익계산서 조회 (Phase 119)."""
    p = period.strip()
    if not p:
        from datetime import datetime, timezone
        p = datetime.now(timezone.utc).strftime('%Y-%m')
    try:
        from ..finance_automation.automation_manager import FinanceAutomationManager
        mgr = FinanceAutomationManager()
        stmt = mgr.generate_statement('pnl', p)
        data = {'period': stmt.period, 'totals': stmt.totals, 'line_items': stmt.line_items}
        return format_message('analytics', data, label=f'손익계산서 {p}')
    except Exception as exc:
        logger.error("cmd_finance_pnl 오류: %s", exc)
        return format_message('error', f'손익계산서 조회 실패: {exc}')


def cmd_finance_settlement(channel: str = '') -> str:
    """/finance_settlement <channel> — 채널별 정산 조회 (Phase 119)."""
    ch = channel.strip()
    try:
        from ..finance_automation.automation_manager import FinanceAutomationManager
        mgr = FinanceAutomationManager()
        batches = mgr.get_settlements(ch)
        items = [
            {
                'batch_id': b.batch_id,
                'channel': b.channel,
                'gross': str(b.gross),
                'net': str(b.net),
                'status': b.status,
            }
            for b in batches
        ]
        return format_message('analytics', items, label=f'정산 목록 (채널={ch or "전체"}): {len(items)}건')
    except Exception as exc:
        logger.error("cmd_finance_settlement 오류: %s", exc)
        return format_message('error', f'정산 조회 실패: {exc}')


def cmd_finance_tax(period: str = '') -> str:
    """/finance_tax <period> — 세무 리포트 조회 (Phase 119)."""
    p = period.strip()
    if not p:
        from datetime import datetime, timezone
        p = datetime.now(timezone.utc).strftime('%Y-%m')
    try:
        from ..finance_automation.automation_manager import FinanceAutomationManager
        mgr = FinanceAutomationManager()
        report = mgr.generate_tax_report(p)
        data = {
            'period': report.period,
            'vat_payable': str(report.vat_payable),
            'vat_receivable': str(report.vat_receivable),
            'customs_paid': str(report.customs_paid),
            'total_taxable': str(report.total_taxable),
        }
        return format_message('analytics', data, label=f'세무 리포트 {p}')
    except Exception as exc:
        logger.error("cmd_finance_tax 오류: %s", exc)
        return format_message('error', f'세무 리포트 조회 실패: {exc}')


def cmd_finance_anomalies() -> str:
    """/finance_anomalies — 이상 거래 감지 결과 조회 (Phase 119)."""
    try:
        from ..finance_automation.automation_manager import FinanceAutomationManager
        mgr = FinanceAutomationManager()
        anomalies = mgr.get_anomalies()
        items = [
            {
                'type': a.type,
                'severity': a.severity,
                'reference': a.reference,
                'detail': a.detail,
            }
            for a in anomalies
        ]
        return format_message('analytics', items, label=f'재무 이상 감지: {len(items)}건')
    except Exception as exc:
        logger.error("cmd_finance_anomalies 오류: %s", exc)
        return format_message('error', f'이상 감지 조회 실패: {exc}')
