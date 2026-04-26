"""환율 관리 CLI.

사용법:
  python -m src.fx.cli --action update [--force] [--dry-run]
  python -m src.fx.cli --action current
  python -m src.fx.cli --action history [--days 30]
  python -m src.fx.cli --action recalculate [--dry-run]
  python -m src.fx.cli --action check-changes [--threshold 3.0]
"""

import argparse
import json
import sys


def _print_json(data):
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def cmd_update(args):
    from .updater import FXUpdater
    updater = FXUpdater()
    result = updater.update(force=args.force, dry_run=args.dry_run)
    _print_json(result)

    # 텔레그램 환율 요약 발송
    if not args.dry_run:
        from src.utils.telegram import send_fx_summary
        send_fx_summary(result)


def cmd_current(args):
    from .updater import FXUpdater
    updater = FXUpdater()
    rates = updater.get_current_rates()
    _print_json({k: str(v) for k, v in rates.items()})


def cmd_history(args):
    from .history import FXHistory
    history = FXHistory()
    records = history.get_history(days=args.days)
    _print_json(records)


def cmd_recalculate(args):
    from .updater import FXUpdater
    updater = FXUpdater()
    rates = updater.get_current_rates()
    results = updater.recalculate_prices(rates, dry_run=args.dry_run)
    _print_json(results)


def cmd_check_changes(args):
    from .history import FXHistory
    history = FXHistory()
    changes = history.detect_significant_changes(threshold_pct=args.threshold)
    if changes:
        print(f"⚠️  {len(changes)}개 통화쌍에서 급변 감지 (임계값 {args.threshold}%):")
        _print_json(changes)
    else:
        print(f"✅ 급변 없음 (임계값 {args.threshold}%)")


def main(argv=None):
    parser = argparse.ArgumentParser(description='환율 관리 CLI')
    parser.add_argument(
        '--action',
        choices=['update', 'current', 'history', 'recalculate', 'check-changes'],
        required=True,
        help='실행할 액션',
    )
    parser.add_argument('--force', action='store_true', help='강제 갱신 (캐시 무시)')
    parser.add_argument('--dry-run', action='store_true', help='드라이런 (실제 업데이트 없음)')
    parser.add_argument('--days', type=int, default=30, help='이력 조회 일수 (기본 30)')
    parser.add_argument('--threshold', type=float, default=3.0, help='급변 감지 임계값 % (기본 3.0)')

    args = parser.parse_args(argv)

    if args.action == 'update':
        cmd_update(args)
    elif args.action == 'current':
        cmd_current(args)
    elif args.action == 'history':
        cmd_history(args)
    elif args.action == 'recalculate':
        cmd_recalculate(args)
    elif args.action == 'check-changes':
        cmd_check_changes(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()
