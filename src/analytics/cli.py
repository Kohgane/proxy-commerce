"""Analytics CLI — Phase 7 비즈니스 인텔리전스 + 자동화 실행 인터페이스.

사용법:
  python -m src.analytics.cli --action weekly-report [--week-start 2026-03-17]
  python -m src.analytics.cli --action monthly-report [--month 2026-03]
  python -m src.analytics.cli --action auto-pricing
  python -m src.analytics.cli --action reorder-check
  python -m src.analytics.cli --action new-product-check
  python -m src.analytics.cli --action business-report --report-type country
"""

import argparse
import json


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Proxy Commerce Analytics CLI',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        '--action',
        required=True,
        choices=[
            'weekly-report', 'monthly-report',
            'auto-pricing', 'reorder-check', 'new-product-check',
            'business-report',
        ],
        help='실행할 액션',
    )
    parser.add_argument('--week-start', default=None, help='주간 리포트 시작 날짜 (YYYY-MM-DD)')
    parser.add_argument('--month', default=None, help='월간 리포트 대상 월 (YYYY-MM)')
    parser.add_argument(
        '--report-type',
        choices=['country', 'brand', 'trend', 'channel'],
        default='country',
        help='business-report 세부 타입 (기본: country)',
    )
    parser.add_argument('--days', type=int, default=30, help='트렌드 분석 기간 일수 (기본: 30)')
    return parser


def _print_json(data):
    print(json.dumps(data, ensure_ascii=False, indent=2))


def main(args=None):
    """CLI 메인 진입점."""
    parser = _build_parser()
    ns = parser.parse_args(args)

    if ns.action == 'weekly-report':
        from .periodic_report import PeriodicReportGenerator
        gen = PeriodicReportGenerator()
        report = gen.send_weekly_report(ns.week_start)
        if report:
            print(gen.format_weekly_telegram(report))
        return

    if ns.action == 'monthly-report':
        from .periodic_report import PeriodicReportGenerator
        gen = PeriodicReportGenerator()
        report = gen.send_monthly_report(ns.month)
        if report:
            print(gen.format_monthly_telegram(report))
        return

    if ns.action == 'auto-pricing':
        from .auto_pricing import AutoPricingEngine
        engine = AutoPricingEngine()
        result = engine.check_and_adjust()
        _print_json(result)
        return

    if ns.action == 'reorder-check':
        from .reorder_alert import ReorderAlertEngine
        engine = ReorderAlertEngine()
        result = engine.run()
        _print_json(result)
        return

    if ns.action == 'new-product-check':
        from .new_product_detector import NewProductDetector
        detector = NewProductDetector()
        result = detector.run()
        _print_json(result)
        return

    if ns.action == 'business-report':
        from .business_report import BusinessAnalytics
        analytics = BusinessAnalytics()
        if ns.report_type == 'country':
            result = analytics.by_country()
        elif ns.report_type == 'brand':
            result = analytics.by_brand()
        elif ns.report_type == 'trend':
            result = analytics.trend_analysis(days=ns.days)
        else:
            result = analytics.channel_efficiency()
        _print_json(result)
        return


if __name__ == '__main__':
    main()
