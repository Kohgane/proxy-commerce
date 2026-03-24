"""src/cli/export_commands.py — 내보내기/리포트 CLI 커맨드.

커맨드:
  export orders [--from] [--to] [--format]     — 주문 CSV 내보내기
  export revenue [--period] [--format]          — 매출 CSV 내보내기
  export audit [--days]                         — 감사 로그 CSV 내보내기
  report daily                                   — 일일 리포트
  report weekly                                  — 주간 리포트
  report monthly                                 — 월간 리포트
  report margin                                  — 마진 분석 리포트
"""

import datetime
import logging

logger = logging.getLogger(__name__)


def cmd_export(args):
    """내보내기 커맨드를 처리한다."""
    sub = getattr(args, "exp_cmd", None)
    if sub == "orders":
        _export_orders(args)
    elif sub == "revenue":
        _export_revenue(args)
    elif sub == "audit":
        _export_audit(args)
    else:
        print("사용법: export {orders|revenue|audit} [옵션]")


def _export_orders(args):
    """주문 데이터를 CSV로 내보낸다."""
    from ..export.csv_exporter import CsvExporter

    date_from = None
    date_to = None
    if getattr(args, "date_from", None):
        date_from = datetime.date.fromisoformat(args.date_from)
    if getattr(args, "date_to", None):
        date_to = datetime.date.fromisoformat(args.date_to)

    exporter = CsvExporter()
    csv_bytes = exporter.export_orders(date_from=date_from, date_to=date_to)

    filename = f"orders_{datetime.date.today()}.csv"
    with open(filename, "wb") as f:
        f.write(csv_bytes)
    print(f"✅ 주문 CSV 저장 완료: {filename}")


def _export_revenue(args):
    """매출 데이터를 CSV로 내보낸다."""
    from ..export.csv_exporter import CsvExporter

    period = getattr(args, "period", "monthly")
    today = datetime.date.today()
    if period == "daily":
        date_from = today - datetime.timedelta(days=1)
        date_to = today
    elif period == "weekly":
        date_from = today - datetime.timedelta(weeks=1)
        date_to = today
    else:  # monthly
        date_from = today.replace(day=1)
        date_to = today

    exporter = CsvExporter()
    csv_bytes = exporter.export_revenue(date_from=date_from, date_to=date_to)

    filename = f"revenue_{period}_{today}.csv"
    with open(filename, "wb") as f:
        f.write(csv_bytes)
    print(f"✅ 매출 CSV 저장 완료: {filename}")


def _export_audit(args):
    """감사 로그를 CSV로 내보낸다."""
    from ..export.csv_exporter import CsvExporter

    days = getattr(args, "days", 30)
    exporter = CsvExporter()
    csv_bytes = exporter.export_audit(days=days)

    filename = f"audit_{datetime.date.today()}.csv"
    with open(filename, "wb") as f:
        f.write(csv_bytes)
    print(f"✅ 감사 로그 CSV 저장 완료: {filename} (최근 {days}일)")


def cmd_report(args):
    """리포트 생성 커맨드를 처리한다."""
    sub = getattr(args, "rep_cmd", None)
    from ..export.report_generator import ReportGenerator
    gen = ReportGenerator()

    if sub == "weekly":
        report = gen.weekly_report()
    elif sub == "monthly":
        report = gen.monthly_report()
    elif sub == "margin":
        report = gen.margin_analysis_report()
    else:
        report = gen.daily_report()

    print(report)
    send = input("\n텔레그램으로 발송할까요? [y/N] ").strip().lower()
    if send == "y":
        ok = gen.send_to_telegram(report)
        print("✅ 발송 완료" if ok else "❌ 발송 실패")
