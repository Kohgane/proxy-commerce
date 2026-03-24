"""src/reporting/scheduled_reports.py — 스케줄 리포트 실행기.

일간/주간/월간 리포트를 자동으로 생성하여 Telegram 및 Google Sheets에 전송한다.

환경변수:
  REPORT_SCHEDULE_DAILY    — 일간 리포트 활성화 (기본 "1")
  REPORT_SCHEDULE_WEEKLY   — 주간 리포트 활성화 (기본 "1")
  REPORT_SCHEDULE_MONTHLY  — 월간 리포트 활성화 (기본 "1")
  REPORT_SHEET_NAME        — 리포트 아카이브 워크시트명 (기본 "reports")
  TELEGRAM_BOT_TOKEN       — Telegram 봇 토큰
  TELEGRAM_CHAT_ID         — Telegram 채팅 ID
  GOOGLE_SHEET_ID          — Google Sheets ID
"""

import datetime
import json
import logging
import os
from typing import Any, Dict

import requests

logger = logging.getLogger(__name__)

_DAILY_ENABLED = os.getenv("REPORT_SCHEDULE_DAILY", "1") == "1"
_WEEKLY_ENABLED = os.getenv("REPORT_SCHEDULE_WEEKLY", "1") == "1"
_MONTHLY_ENABLED = os.getenv("REPORT_SCHEDULE_MONTHLY", "1") == "1"
_REPORT_SHEET_NAME = os.getenv("REPORT_SHEET_NAME", "reports")
_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")

try:
    from ..utils.sheets import open_sheet
except ImportError:
    open_sheet = None  # type: ignore


class ScheduledReportRunner:
    """스케줄 리포트 실행기."""

    def __init__(self, sheet_id: str = ""):
        self._sheet_id = sheet_id or _SHEET_ID

    # ------------------------------------------------------------------
    # 내부 헬퍼
    # ------------------------------------------------------------------

    def _get_builder(self):
        """ReportBuilder 인스턴스를 반환한다."""
        from .report_builder import ReportBuilder
        return ReportBuilder(sheet_id=self._sheet_id)

    def _send_telegram(self, text: str) -> bool:
        """Telegram으로 텍스트를 전송한다."""
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        if not token or not chat_id:
            logger.warning("Telegram 설정 누락 — 리포트 전송 생략")
            return False
        try:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            resp = requests.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}, timeout=10)
            resp.raise_for_status()
            return True
        except Exception as exc:
            logger.warning("Telegram 리포트 전송 실패: %s", exc)
            return False

    def _archive_to_sheets(self, report_data: Dict[str, Any]) -> None:
        """리포트 데이터를 Google Sheets에 아카이브한다."""
        sheet_name = os.getenv("REPORT_SHEET_NAME", _REPORT_SHEET_NAME)
        if open_sheet is None:
            return
        try:
            ws = open_sheet(self._sheet_id, sheet_name)
            existing = ws.get_all_values()
            if not existing:
                ws.append_row(["report_type", "generated_at", "data_json"])
            ws.append_row([
                report_data.get("report_type", ""),
                report_data.get("generated_at", datetime.datetime.utcnow().isoformat()),
                json.dumps(report_data, ensure_ascii=False),
            ])
        except Exception as exc:
            logger.warning("리포트 아카이브 실패: %s", exc)

    def _format_report_text(self, report: Dict[str, Any]) -> str:
        """리포트 딕셔너리를 Telegram 텍스트로 변환한다."""
        rtype = report.get("report_type", "unknown")
        generated_at = str(report.get("generated_at", ""))[:19]
        lines = [f"*📊 {rtype.upper()} 리포트* ({generated_at})\n"]

        if rtype == "sales":
            lines.append(f"총 주문: *{report.get('total_orders', 0)}건*")
            lines.append(f"총 매출: *{int(report.get('total_revenue_krw', 0)):,}원*")
            lines.append(f"평균 주문: *{int(report.get('avg_order_krw', 0)):,}원*")
        elif rtype == "inventory":
            lines.append(f"전체 SKU: *{report.get('total_skus', 0)}*")
            lines.append(f"재고 있음: *{report.get('in_stock', 0)}*")
            lines.append(f"재고 없음: *{report.get('out_of_stock', 0)}*")
            lines.append(f"저재고: *{report.get('low_stock', 0)}*")
        elif rtype == "customers":
            lines.append(f"전체 고객: *{report.get('total_customers', 0)}명*")
            lines.append(f"신규 고객: *{report.get('new_customers', 0)}명*")
        elif rtype == "marketing":
            lines.append(f"전체 캠페인: *{report.get('total_campaigns', 0)}*")
            lines.append(f"활성 캠페인: *{report.get('active_campaigns', 0)}*")
            lines.append(f"총 예산: *{int(report.get('total_budget_krw', 0)):,}원*")
            lines.append(f"총 지출: *{int(report.get('total_spent_krw', 0)):,}원*")

        return '\n'.join(lines)

    # ------------------------------------------------------------------
    # 공개 메서드
    # ------------------------------------------------------------------

    def run_daily_report(self) -> None:
        """일간 매출 리포트를 생성하여 Telegram으로 전송한다."""
        if not os.getenv("REPORT_SCHEDULE_DAILY", "1") == "1":
            return
        try:
            today = datetime.date.today().isoformat()
            builder = self._get_builder()
            report = builder.generate_report("sales", start_date=today, end_date=today)
            text = self._format_report_text(report)
            self._send_telegram(f"*[일간 리포트]*\n{text}")
            logger.info("일간 리포트 완료")
        except Exception as exc:
            logger.error("일간 리포트 실패: %s", exc)

    def run_weekly_report(self) -> None:
        """주간 리포트(매출 + 재고)를 생성하여 Telegram 및 이메일로 전송한다."""
        if not os.getenv("REPORT_SCHEDULE_WEEKLY", "1") == "1":
            return
        try:
            today = datetime.date.today()
            start = (today - datetime.timedelta(days=7)).isoformat()
            end = today.isoformat()
            builder = self._get_builder()

            sales = builder.generate_report("sales", start_date=start, end_date=end)
            inventory = builder.generate_report("inventory", start_date=start, end_date=end)

            text = "*[주간 리포트]*\n"
            text += self._format_report_text(sales) + "\n\n"
            text += self._format_report_text(inventory)
            self._send_telegram(text)
            logger.info("주간 리포트 완료")
        except Exception as exc:
            logger.error("주간 리포트 실패: %s", exc)

    def run_monthly_report(self) -> None:
        """월간 리포트(전체 타입)를 생성하여 Google Sheets에 아카이브한다."""
        if not os.getenv("REPORT_SCHEDULE_MONTHLY", "1") == "1":
            return
        try:
            today = datetime.date.today()
            first_day = today.replace(day=1).isoformat()
            end = today.isoformat()
            builder = self._get_builder()

            for rtype in ("sales", "inventory", "customers", "marketing"):
                report = builder.generate_report(rtype, start_date=first_day, end_date=end)
                self._archive_to_sheets(report)

            logger.info("월간 리포트 아카이브 완료")
        except Exception as exc:
            logger.error("월간 리포트 실패: %s", exc)
