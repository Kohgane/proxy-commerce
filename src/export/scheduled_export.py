"""src/export/scheduled_export.py — 정기 내보내기 스케줄러.

매일 자정 KST: 일일 매출 요약 CSV → Google Sheets 'daily_exports' 워크시트
매주 월요일: 주간 종합 리포트 텔레그램 발송

환경변수:
  EXPORT_ENABLED         — 내보내기 활성화 여부 (기본 "1")
  EXPORT_WORKSHEET       — 저장할 워크시트명 (기본 "daily_exports")
  EXPORT_DAILY_ENABLED   — 일일 내보내기 활성화 (기본 "1")
  EXPORT_WEEKLY_ENABLED  — 주간 내보내기 활성화 (기본 "1")
  GOOGLE_SHEET_ID        — Google Sheets ID
"""

import csv
import datetime
import io
import logging
import os
from typing import Optional

try:
    from ..utils.sheets import open_sheet
except ImportError:
    open_sheet = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

_EXPORT_ENABLED = os.getenv("EXPORT_ENABLED", "1") == "1"
_EXPORT_WORKSHEET = os.getenv("EXPORT_WORKSHEET", "daily_exports")
_DAILY_ENABLED = os.getenv("EXPORT_DAILY_ENABLED", "1") == "1"
_WEEKLY_ENABLED = os.getenv("EXPORT_WEEKLY_ENABLED", "1") == "1"
_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")


class ScheduledExport:
    """정기 내보내기 스케줄러.

    사용 예:
        scheduler = ScheduledExport()
        scheduler.run_daily()     # 일일 내보내기 실행
        scheduler.run_weekly()    # 주간 리포트 실행
    """

    def __init__(self, sheet_id: Optional[str] = None):
        self._sheet_id = sheet_id or _SHEET_ID

    def run_daily(self) -> bool:
        """일일 매출 요약 CSV를 생성하고 Google Sheets에 저장한다.

        Returns:
            성공 여부
        """
        if not _EXPORT_ENABLED or not _DAILY_ENABLED:
            logger.info("일일 내보내기 비활성화")
            return False

        try:
            from .csv_exporter import CsvExporter
            from .report_generator import ReportGenerator

            today = datetime.date.today()
            yesterday = today - datetime.timedelta(days=1)

            exporter = CsvExporter(sheet_id=self._sheet_id)
            csv_bytes = exporter.export_revenue(date_from=yesterday, date_to=yesterday)

            self._save_to_sheets(csv_bytes, worksheet=_EXPORT_WORKSHEET, date=yesterday)

            gen = ReportGenerator(sheet_id=self._sheet_id)
            report = gen.daily_report(date=yesterday)
            gen.send_to_telegram(report)

            logger.info("일일 내보내기 완료: %s", yesterday)
            return True
        except Exception as exc:
            logger.error("일일 내보내기 실패: %s", exc)
            return False

    def run_weekly(self) -> bool:
        """주간 종합 리포트를 생성하고 텔레그램으로 발송한다.

        Returns:
            성공 여부
        """
        if not _EXPORT_ENABLED or not _WEEKLY_ENABLED:
            logger.info("주간 내보내기 비활성화")
            return False

        try:
            from .report_generator import ReportGenerator

            gen = ReportGenerator(sheet_id=self._sheet_id)
            report = gen.weekly_report()
            gen.send_to_telegram(report)

            logger.info("주간 리포트 발송 완료")
            return True
        except Exception as exc:
            logger.error("주간 내보내기 실패: %s", exc)
            return False

    def _save_to_sheets(
        self,
        csv_bytes: bytes,
        worksheet: str,
        date: datetime.date,
    ) -> None:
        """CSV 데이터를 Google Sheets 워크시트에 저장한다."""
        try:
            ws = open_sheet(self._sheet_id, worksheet)
            content = csv_bytes.decode("utf-8-sig")
            reader = csv.DictReader(io.StringIO(content))
            rows = list(reader)

            if not rows:
                logger.info("내보낼 데이터 없음: %s", date)
                return

            # 헤더 + 날짜 메타 행 추가
            ws.append_row([f"=== {date} 일일 내보내기 ==="])
            if rows:
                ws.append_row(list(rows[0].keys()))
                for row in rows:
                    ws.append_row(list(row.values()))

            logger.info("Google Sheets 저장 완료: worksheet=%s rows=%d", worksheet, len(rows))
        except Exception as exc:
            logger.warning("Google Sheets 저장 실패: %s", exc)


def run_daily_export() -> None:
    """CLI/GitHub Actions 엔트리포인트 — 일일 내보내기 실행."""
    scheduler = ScheduledExport()
    success = scheduler.run_daily()
    if not success:
        raise SystemExit(1)


def run_weekly_export() -> None:
    """CLI/GitHub Actions 엔트리포인트 — 주간 내보내기 실행."""
    scheduler = ScheduledExport()
    success = scheduler.run_weekly()
    if not success:
        raise SystemExit(1)


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "daily"
    if cmd == "weekly":
        run_weekly_export()
    else:
        run_daily_export()
