"""대시보드 CLI — 매출 리포트 / 일일 요약 / 주문 상태 조회.

사용법:
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


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Proxy Commerce 대시보드 CLI',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        '--action',
        required=True,
        choices=['daily-summary', 'revenue', 'status', 'margin-analysis'],
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
    print(json.dumps(data, ensure_ascii=False, indent=2))


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
