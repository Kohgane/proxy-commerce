"""대시보드 CLI — 매출 / 일일 요약 / 모닝 브리핑 / 주문 상태 조회.

사용법:
  python -m src.dashboard.cli --action morning-briefing [--date 2026-04-26]
  python -m src.dashboard.cli --action daily-summary [--date 2026-03-09]
  python -m src.dashboard.cli --action revenue --period daily [--date 2026-03-09]
  python -m src.dashboard.cli --action revenue --period weekly [--week-start 2026-03-03]
  python -m src.dashboard.cli --action revenue --period monthly [--month 2026-03]
  python -m src.dashboard.cli --action status --filter pending
  python -m src.dashboard.cli --action status --order-id 12345
  python -m src.dashboard.cli --action margin-analysis
"""

import argparse
import json
import logging

logger = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Proxy Commerce 대시보드 CLI',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        '--action',
        required=True,
        choices=[
            'daily-summary',
            'morning-briefing',
            'revenue',
            'status',
            'margin-analysis',
        ],
        help='실행할 액션',
    )
    parser.add_argument('--date', default=None, help='날짜 (YYYY-MM-DD)')
    parser.add_argument('--period', choices=['daily', 'weekly', 'monthly'], default='daily',
                        help='revenue 리포트 기간 (기본: daily)')
    parser.add_argument('--week-start', default=None, help='주간 리포트 시작 날짜 (YYYY-MM-DD)')
    parser.add_argument('--month', default=None, help='월간 리포트 (YYYY-MM)')
    parser.add_argument('--filter', choices=['pending', 'all'], default=None,
                        help='status 조회 필터 (pending: 미완료 주문, all: 전체)')
    parser.add_argument('--order-id', default=None, help='특정 주문 ID 조회')
    parser.add_argument('--status', default=None,
                        help='특정 상태 주문 조회 (예: routed, ordered, delivered 등)')
    return parser


def _print_json(data):
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def _action_morning_briefing(ns):
    """통합 모닝 브리핑 - 일일 요약 + 환율 + 가격 조정 → 텔레그램."""
    from .daily_summary import DailySummaryGenerator, format_morning_briefing

    # 1. 일일 요약 (기존 generate_summary 활용)
    daily_gen = DailySummaryGenerator()
    daily_summary = daily_gen.generate_summary(ns.date)

    # 2. 환율 데이터 + 이력 (모듈 없으면 빈 dict로 폴백)
    fx_data = {}
    fx_history = {}
    try:
        from ..fx.provider import FXProvider
        fx_provider = FXProvider()
        for pair in ['USDKRW', 'JPYKRW', 'EURKRW']:
            try:
                # FXProvider 메서드 시그니처는 코드베이스에 따라 다를 수 있음
                if hasattr(fx_provider, 'get_rate'):
                    rate = fx_provider.get_rate(pair)
                elif hasattr(fx_provider, 'get_all_rates'):
                    all_rates = fx_provider.get_all_rates()
                    rate = all_rates.get(pair)
                else:
                    rate = None
                if rate:
                    fx_data[pair] = float(rate)
            except Exception as exc:
                logger.debug("FX rate %s fetch failed: %s", pair, exc)
    except ImportError:
        logger.info("FXProvider not available, skipping FX data")

    try:
        from ..fx.history import FXHistory
        fx_hist = FXHistory()
        for pair in fx_data:
            try:
                if hasattr(fx_hist, 'get_previous_rate'):
                    prev = fx_hist.get_previous_rate(pair, days_ago=1)
                elif hasattr(fx_hist, 'get_rate_at'):
                    from datetime import date as _date, timedelta
                    prev = fx_hist.get_rate_at(pair, _date.today() - timedelta(days=1))
                else:
                    prev = None
                if prev:
                    fx_history[pair] = {'current': fx_data[pair], 'previous': float(prev)}
            except Exception as exc:
                logger.debug("FX history %s fetch failed: %s", pair, exc)
    except ImportError:
        logger.info("FXHistory not available, skipping FX history")

    # 3. 자동 가격 조정 요약 (모듈 없으면 빈 dict)
    pricing_summary = {'checked': 0, 'to_adjust': 0}
    try:
        from ..analytics.pricing import AutoPricing
        pricing = AutoPricing(mode='DRY_RUN')
        if hasattr(pricing, 'get_summary'):
            pricing_summary = pricing.get_summary()
        elif hasattr(pricing, 'check_all'):
            result = pricing.check_all()
            pricing_summary = {
                'checked': result.get('total_checked', 0),
                'to_adjust': result.get('to_adjust', 0),
            }
    except (ImportError, Exception) as exc:
        logger.debug("AutoPricing not available: %s", exc)

    # 4. 통합 메시지 생성
    message = format_morning_briefing(
        daily_summary=daily_summary,
        fx_data=fx_data,
        pricing_summary=pricing_summary,
        fx_history=fx_history,
    )

    # 5. 텔레그램 발송
    import os
    if os.getenv('TELEGRAM_ENABLED', '1') == '1':
        try:
            from ..utils.telegram import send_tele
            send_tele(message)
            logger.info("Morning briefing sent via Telegram")
        except Exception as exc:
            logger.warning("Telegram send failed: %s", exc)

    print(message)


def main(args=None):
    parser = _build_parser()
    ns = parser.parse_args(args)

    if ns.action == 'daily-summary':
        from .daily_summary import DailySummaryGenerator
        gen = DailySummaryGenerator()
        summary = gen.send_daily_summary(ns.date)
        if summary:
            print(gen.format_telegram(summary))
        return

    if ns.action == 'morning-briefing':
        _action_morning_briefing(ns)
        return

    if ns.action == 'revenue':
        from .revenue_report import RevenueReporter
        reporter = RevenueReporter()
        if ns.period == 'weekly':
            result = reporter.weekly_revenue(ns.week_start)
        elif ns.period == 'monthly':
            result = reporter.monthly_revenue(ns.month)
        else:
            result = reporter.daily_revenue(ns.date)
        _print_json(result)
        return

    if ns.action == 'status':
        from .order_status import OrderStatusTracker
        tracker = OrderStatusTracker()
        if ns.order_id:
            result = tracker.get_order_history(ns.order_id)
        elif ns.filter == 'pending':
            result = tracker.get_pending_orders()
        elif ns.filter == 'all':
            result = tracker._get_all_rows()
        elif ns.status:
            result = tracker.get_orders_by_status(ns.status)
        else:
            result = tracker.get_stats()
        _print_json(result)
        return

    if ns.action == 'margin-analysis':
        from .revenue_report import RevenueReporter
        reporter = RevenueReporter()
        result = reporter.margin_analysis()
        _print_json(result)
        return


if __name__ == '__main__':
    main()
