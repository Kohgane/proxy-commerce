"""src/cli/main.py — 통합 CLI 엔트리포인트.

사용법:
  python -m src.cli <command> [options]

서브커맨드:
  sync       — 카탈로그 동기화 (기존 catalog_sync 래핑)
  orders     — 주문 조회/관리
  inventory  — 재고 조회/동기화
  fx         — 환율 조회/업데이트
  export     — 데이터 내보내기
  report     — 리포트 생성
  health     — 시스템 상태 확인
  audit      — 감사 로그 조회
  cache      — 캐시 통계/초기화
"""

import argparse


def _build_parser() -> argparse.ArgumentParser:
    """CLI 파서를 구성한다."""
    parser = argparse.ArgumentParser(
        prog="python -m src.cli",
        description="Proxy Commerce 운영 CLI",
    )
    sub = parser.add_subparsers(dest="command", metavar="<command>")
    sub.required = True

    # sync
    sub.add_parser("sync", help="카탈로그 동기화 실행")

    # orders
    orders_p = sub.add_parser("orders", help="주문 조회/관리")
    orders_sub = orders_p.add_subparsers(dest="orders_cmd", metavar="<subcommand>")
    orders_list = orders_sub.add_parser("list", help="주문 목록")
    orders_list.add_argument("--status", choices=["pending", "shipped", "completed", "paid"], default=None)
    orders_list.add_argument("--limit", type=int, default=20)
    orders_detail = orders_sub.add_parser("detail", help="주문 상세")
    orders_detail.add_argument("order_id")
    orders_stats = orders_sub.add_parser("stats", help="주문 통계")
    orders_stats.add_argument("--period", choices=["today", "week", "month"], default="today")

    # inventory
    inv_p = sub.add_parser("inventory", help="재고 조회/동기화")
    inv_sub = inv_p.add_subparsers(dest="inv_cmd", metavar="<subcommand>")
    inv_check = inv_sub.add_parser("check", help="재고 확인")
    inv_check.add_argument("--vendor", choices=["porter", "memo_paris"], default=None)
    inv_low = inv_sub.add_parser("low-stock", help="재고 부족 상품")
    inv_low.add_argument("--threshold", type=int, default=3)
    inv_sync = inv_sub.add_parser("sync", help="재고 동기화")
    inv_sync.add_argument("--vendor", choices=["porter", "memo_paris"], default=None)

    # fx
    fx_p = sub.add_parser("fx", help="환율 조회/업데이트")
    fx_sub = fx_p.add_subparsers(dest="fx_cmd", metavar="<subcommand>")
    fx_sub.add_parser("show", help="현재 환율 출력")
    fx_sub.add_parser("update", help="환율 업데이트")

    # export
    exp_p = sub.add_parser("export", help="데이터 내보내기")
    exp_sub = exp_p.add_subparsers(dest="exp_cmd", metavar="<subcommand>")
    exp_orders = exp_sub.add_parser("orders", help="주문 CSV 내보내기")
    exp_orders.add_argument("--from", dest="date_from", metavar="YYYY-MM-DD", default=None)
    exp_orders.add_argument("--to", dest="date_to", metavar="YYYY-MM-DD", default=None)
    exp_orders.add_argument("--format", choices=["csv"], default="csv")
    exp_revenue = exp_sub.add_parser("revenue", help="매출 CSV 내보내기")
    exp_revenue.add_argument("--period", choices=["monthly", "weekly", "daily"], default="monthly")
    exp_revenue.add_argument("--format", choices=["csv"], default="csv")
    exp_audit = exp_sub.add_parser("audit", help="감사 로그 CSV 내보내기")
    exp_audit.add_argument("--days", type=int, default=30)

    # report
    rep_p = sub.add_parser("report", help="리포트 생성")
    rep_sub = rep_p.add_subparsers(dest="rep_cmd", metavar="<subcommand>")
    rep_sub.add_parser("daily", help="일일 리포트")
    rep_sub.add_parser("weekly", help="주간 리포트")
    rep_sub.add_parser("monthly", help="월간 리포트")
    rep_sub.add_parser("margin", help="마진 분석 리포트")

    # health
    health_p = sub.add_parser("health", help="시스템 상태 확인")
    health_sub = health_p.add_subparsers(dest="health_cmd", metavar="<subcommand>")
    health_sub.add_parser("check", help="전체 시스템 헬스 체크")

    # cache
    cache_p = sub.add_parser("cache", help="캐시 통계/초기화")
    cache_sub = cache_p.add_subparsers(dest="cache_cmd", metavar="<subcommand>")
    cache_sub.add_parser("stats", help="캐시 통계 출력")
    cache_sub.add_parser("clear", help="캐시 전체 초기화")

    # audit
    audit_p = sub.add_parser("audit", help="감사 로그 조회")
    audit_sub = audit_p.add_subparsers(dest="audit_cmd", metavar="<subcommand>")
    audit_recent = audit_sub.add_parser("recent", help="최근 감사 로그")
    audit_recent.add_argument("--limit", type=int, default=20)

    return parser


def main(argv=None):
    """CLI 메인 함수."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "sync":
        from .order_commands import cmd_sync
        cmd_sync(args)
    elif args.command == "orders":
        from .order_commands import cmd_orders
        cmd_orders(args)
    elif args.command == "inventory":
        from .inventory_commands import cmd_inventory
        cmd_inventory(args)
    elif args.command == "fx":
        from .order_commands import cmd_fx
        cmd_fx(args)
    elif args.command == "export":
        from .export_commands import cmd_export
        cmd_export(args)
    elif args.command == "report":
        from .export_commands import cmd_report
        cmd_report(args)
    elif args.command == "health":
        from .system_commands import cmd_health
        cmd_health(args)
    elif args.command == "cache":
        from .system_commands import cmd_cache
        cmd_cache(args)
    elif args.command == "audit":
        from .system_commands import cmd_audit
        cmd_audit(args)


if __name__ == "__main__":
    main()
