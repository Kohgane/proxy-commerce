"""Phase 7: 주간/월간 정기 리포트 생성 + 발송 모듈.

기존 DailySummaryGenerator 패턴을 확장하여 주간/월간 리포트를
텔레그램, 이메일, Google Sheets로 발송한다.
"""

import logging
import os
from datetime import date, timedelta

logger = logging.getLogger(__name__)


class PeriodicReportGenerator:
    """주간/월간 정기 리포트 생성 + 발송.

    환경변수:
      WEEKLY_REPORT_ENABLED        — 주간 리포트 활성화 (기본 1)
      MONTHLY_REPORT_ENABLED       — 월간 리포트 활성화 (기본 1)
      WEEKLY_REPORTS_WORKSHEET     — Sheets 워크시트명 (기본 weekly_reports)
      MONTHLY_REPORTS_WORKSHEET    — Sheets 워크시트명 (기본 monthly_reports)
    """

    def __init__(self, order_tracker=None):
        """초기화.

        Args:
            order_tracker: OrderStatusTracker 인스턴스. None이면 새로 생성.
        """
        if order_tracker is None:
            from ..dashboard.order_status import OrderStatusTracker
            self._tracker = OrderStatusTracker()
        else:
            self._tracker = order_tracker

        from ..dashboard.revenue_report import RevenueReporter
        self._reporter = RevenueReporter(self._tracker)

    # ── 공개 API ─────────────────────────────────────────────

    def weekly_report(self, week_start: str = None) -> dict:
        """주간 리포트 데이터 생성.

        Args:
            week_start: 'YYYY-MM-DD' (월요일). None이면 이번 주 월요일.

        Returns:
            주간 리포트 딕셔너리 (매출/마진/성장률/베스트셀러/마진위험SKU/환율)
        """
        if week_start:
            start = date.fromisoformat(week_start)
        else:
            today = date.today()
            start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=7)

        current_rows = self._reporter._rows_for_range(start, end)
        prev_start = start - timedelta(days=7)
        prev_rows = self._reporter._rows_for_range(prev_start, start)

        current_agg = self._reporter._aggregate(current_rows)
        prev_agg = self._reporter._aggregate(prev_rows)

        growth_pct = 0.0
        if prev_agg['revenue_krw'] > 0:
            growth_pct = round(
                (current_agg['revenue_krw'] - prev_agg['revenue_krw'])
                / prev_agg['revenue_krw'] * 100, 1
            )

        # 마진 위험 SKU
        risk_skus = []
        for r in current_rows:
            try:
                mp = float(r.get('margin_pct', 0) or 0)
            except (TypeError, ValueError):
                mp = 0.0
            if 0 < mp < self._reporter.LOW_MARGIN_THRESHOLD:
                risk_skus.append({'sku': r.get('sku', ''), 'margin_pct': mp})

        return {
            'type': 'weekly',
            'week_start': str(start),
            'week_end': str(end - timedelta(days=1)),
            'total_orders': current_agg['orders'],
            'total_revenue_krw': current_agg['revenue_krw'],
            'total_cost_krw': current_agg['cost_krw'],
            'gross_profit_krw': current_agg['gross_profit_krw'],
            'gross_margin_pct': current_agg['margin_pct'],
            'prev_week_revenue_krw': prev_agg['revenue_krw'],
            'growth_pct': growth_pct,
            'by_vendor': self._reporter._by_vendor(current_rows),
            'by_channel': self._reporter._by_channel(current_rows),
            'top_products': self._reporter._top_products(current_rows, n=10),
            'risk_skus': risk_skus[:5],
            'fx_summary': self._get_fx_summary(),
        }

    def monthly_report(self, year_month: str = None) -> dict:
        """월간 리포트 데이터 생성.

        Args:
            year_month: 'YYYY-MM'. None이면 이번 달.

        Returns:
            월간 리포트 딕셔너리 (전월/전년동월 성장률, 신규/단종 상품, 채널 비중 등)
        """
        if year_month:
            year, month = map(int, year_month.split('-'))
        else:
            today = date.today()
            year, month = today.year, today.month

        start = date(year, month, 1)
        end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)

        current_rows = self._reporter._rows_for_range(start, end)

        # 전월
        prev_month = month - 1 if month > 1 else 12
        prev_year = year if month > 1 else year - 1
        prev_start = date(prev_year, prev_month, 1)
        prev_rows = self._reporter._rows_for_range(prev_start, start)

        # 전년동월
        yoy_start = date(year - 1, month, 1)
        yoy_end = date(year - 1, month + 1, 1) if month < 12 else date(year, 1, 1)
        yoy_rows = self._reporter._rows_for_range(yoy_start, yoy_end)

        current_agg = self._reporter._aggregate(current_rows)
        prev_agg = self._reporter._aggregate(prev_rows)
        yoy_agg = self._reporter._aggregate(yoy_rows)

        mom_growth = 0.0
        if prev_agg['revenue_krw'] > 0:
            mom_growth = round(
                (current_agg['revenue_krw'] - prev_agg['revenue_krw'])
                / prev_agg['revenue_krw'] * 100, 1
            )

        yoy_growth = 0.0
        if yoy_agg['revenue_krw'] > 0:
            yoy_growth = round(
                (current_agg['revenue_krw'] - yoy_agg['revenue_krw'])
                / yoy_agg['revenue_krw'] * 100, 1
            )

        current_skus = {str(r.get('sku', '')) for r in current_rows if r.get('sku')}
        prev_skus = {str(r.get('sku', '')) for r in prev_rows if r.get('sku')}
        new_products = sorted(current_skus - prev_skus)
        discontinued = sorted(prev_skus - current_skus)

        by_channel = self._reporter._by_channel(current_rows)
        total_rev = current_agg['revenue_krw'] or 1
        channel_share = {
            ch: round(data['revenue_krw'] / total_rev * 100, 1)
            for ch, data in by_channel.items()
        }

        return {
            'type': 'monthly',
            'year_month': f"{year:04d}-{month:02d}",
            'total_orders': current_agg['orders'],
            'total_revenue_krw': current_agg['revenue_krw'],
            'total_cost_krw': current_agg['cost_krw'],
            'gross_profit_krw': current_agg['gross_profit_krw'],
            'gross_margin_pct': current_agg['margin_pct'],
            'prev_month_revenue_krw': prev_agg['revenue_krw'],
            'mom_growth_pct': mom_growth,
            'yoy_revenue_krw': yoy_agg['revenue_krw'],
            'yoy_growth_pct': yoy_growth,
            'by_vendor': self._reporter._by_vendor(current_rows),
            'by_channel': by_channel,
            'channel_share_pct': channel_share,
            'top_products': self._reporter._top_products(current_rows, n=10),
            'new_products': new_products[:20],
            'discontinued_products': discontinued[:20],
        }

    def format_weekly_telegram(self, report: dict) -> str:
        """주간 리포트 텔레그램 메시지 포맷팅."""
        growth_arrow = "📈" if report.get('growth_pct', 0) >= 0 else "📉"
        top = report.get('top_products', [])
        top_line = ', '.join(f"{p['sku']}({p['sold']}건)" for p in top[:3]) if top else '-'
        risk = report.get('risk_skus', [])
        risk_line = ', '.join(f"{s['sku']}({s['margin_pct']:.1f}%)" for s in risk) if risk else '-'

        lines = [
            f"📊 [주간 리포트] {report.get('week_start')} ~ {report.get('week_end')}",
            "",
            f"💰 매출: ₩{report.get('total_revenue_krw', 0):,.0f}",
            f"📦 주문: {report.get('total_orders', 0)}건",
            f"📈 마진: {report.get('gross_margin_pct', 0):.1f}%",
            f"{growth_arrow} 전주 대비: {report.get('growth_pct', 0):+.1f}%",
            "",
            f"🏆 베스트셀러: {top_line}",
            f"⚠️ 마진 위험: {risk_line}",
        ]

        fx = report.get('fx_summary', {})
        if fx:
            fx_parts = [f"{k}: {v}" for k, v in fx.items()]
            lines.append(f"💱 환율: {', '.join(fx_parts)}")

        return "\n".join(lines)

    def format_monthly_telegram(self, report: dict) -> str:
        """월간 리포트 텔레그램 메시지 포맷팅."""
        mom_arrow = "📈" if report.get('mom_growth_pct', 0) >= 0 else "📉"
        yoy_arrow = "📈" if report.get('yoy_growth_pct', 0) >= 0 else "📉"
        top = report.get('top_products', [])
        top_line = ', '.join(f"{p['sku']}({p['sold']}건)" for p in top[:3]) if top else '-'

        lines = [
            f"📅 [월간 리포트] {report.get('year_month')}",
            "",
            f"💰 매출: ₩{report.get('total_revenue_krw', 0):,.0f}",
            f"📦 주문: {report.get('total_orders', 0)}건",
            f"📈 마진: {report.get('gross_margin_pct', 0):.1f}%",
            f"{mom_arrow} 전월 대비: {report.get('mom_growth_pct', 0):+.1f}%",
            f"{yoy_arrow} 전년동월 대비: {report.get('yoy_growth_pct', 0):+.1f}%",
            "",
            f"🆕 신규 상품: {len(report.get('new_products', []))}개",
            f"❌ 단종 상품: {len(report.get('discontinued_products', []))}개",
            f"🏆 베스트셀러: {top_line}",
        ]
        return "\n".join(lines)

    def format_email_html(self, report: dict) -> str:
        """리포트 이메일 HTML 포맷팅."""
        report_type = report.get('type', 'periodic')
        if report_type == 'weekly':
            title = f"주간 리포트 {report.get('week_start')} ~ {report.get('week_end')}"
        else:
            title = f"월간 리포트 {report.get('year_month')}"

        total_revenue = report.get('total_revenue_krw', 0)
        total_orders = report.get('total_orders', 0)
        margin_pct = report.get('gross_margin_pct', 0.0)

        by_vendor = report.get('by_vendor', {})
        vendor_rows_html = ''.join(
            f"<tr><td>{v}</td><td>{d.get('orders', 0)}</td>"
            f"<td>₩{d.get('revenue_krw', 0):,}</td>"
            f"<td>{d.get('margin_pct', 0):.1f}%</td></tr>"
            for v, d in by_vendor.items()
        )

        top_rows_html = ''.join(
            f"<tr><td>{p['sku']}</td><td>{p.get('title', '')}</td>"
            f"<td>{p.get('sold', 0)}</td><td>₩{p.get('revenue_krw', 0):,}</td></tr>"
            for p in report.get('top_products', [])[:10]
        )

        html = (
            f'<!DOCTYPE html><html><head><meta charset="utf-8">'
            f'<title>{title}</title></head>'
            f'<body style="font-family: sans-serif; max-width: 700px; margin: 0 auto;">'
            f'<h2>📊 {title}</h2>'
            f'<table border="1" cellpadding="6" cellspacing="0"'
            f' style="border-collapse:collapse; width:100%;">'
            f'<tr><th>항목</th><th>값</th></tr>'
            f'<tr><td>매출</td><td>₩{total_revenue:,}</td></tr>'
            f'<tr><td>주문 수</td><td>{total_orders}건</td></tr>'
            f'<tr><td>마진</td><td>{margin_pct:.1f}%</td></tr>'
            f'</table>'
            f'<h3>벤더별 현황</h3>'
            f'<table border="1" cellpadding="6" cellspacing="0"'
            f' style="border-collapse:collapse; width:100%;">'
            f'<tr><th>벤더</th><th>주문</th><th>매출</th><th>마진</th></tr>'
            f'{vendor_rows_html}</table>'
            f'<h3>베스트셀러 TOP 10</h3>'
            f'<table border="1" cellpadding="6" cellspacing="0"'
            f' style="border-collapse:collapse; width:100%;">'
            f'<tr><th>SKU</th><th>상품명</th><th>판매량</th><th>매출</th></tr>'
            f'{top_rows_html}</table>'
            f'</body></html>'
        )
        return html

    def send_weekly_report(self, week_start: str = None):
        """주간 리포트 생성 + Sheets 기록 + 텔레그램/이메일 발송.

        Returns:
            report dict or None if disabled.
        """
        enabled = os.getenv('WEEKLY_REPORT_ENABLED', '1') == '1'
        if not enabled:
            logger.info("WEEKLY_REPORT_ENABLED=0, skipping")
            return None

        report = self.weekly_report(week_start)
        self._write_report_to_sheets(report)

        if os.getenv('TELEGRAM_ENABLED', '1') == '1':
            try:
                from ..utils.telegram import send_tele
                send_tele(self.format_weekly_telegram(report))
                logger.info("Weekly report sent via Telegram")
            except Exception as exc:
                logger.warning("Telegram send failed: %s", exc)

        if os.getenv('EMAIL_ENABLED', '0') == '1':
            try:
                from ..utils.emailer import send_mail
                send_mail(f"[주간 리포트] {report.get('week_start')}", self.format_email_html(report))
                logger.info("Weekly report sent via Email")
            except Exception as exc:
                logger.warning("Email send failed: %s", exc)

        return report

    def send_monthly_report(self, year_month: str = None):
        """월간 리포트 생성 + Sheets 기록 + 텔레그램/이메일 발송.

        Returns:
            report dict or None if disabled.
        """
        enabled = os.getenv('MONTHLY_REPORT_ENABLED', '1') == '1'
        if not enabled:
            logger.info("MONTHLY_REPORT_ENABLED=0, skipping")
            return None

        report = self.monthly_report(year_month)
        self._write_report_to_sheets(report)

        if os.getenv('TELEGRAM_ENABLED', '1') == '1':
            try:
                from ..utils.telegram import send_tele
                send_tele(self.format_monthly_telegram(report))
                logger.info("Monthly report sent via Telegram")
            except Exception as exc:
                logger.warning("Telegram send failed: %s", exc)

        if os.getenv('EMAIL_ENABLED', '0') == '1':
            try:
                from ..utils.emailer import send_mail
                send_mail(f"[월간 리포트] {report.get('year_month')}", self.format_email_html(report))
                logger.info("Monthly report sent via Email")
            except Exception as exc:
                logger.warning("Email send failed: %s", exc)

        return report

    # ── 내부 헬퍼 ─────────────────────────────────────────────

    def _get_fx_summary(self) -> dict:
        """현재 환율 요약 반환 (환경변수 기준)."""
        return {
            'USD/KRW': os.getenv('FX_USDKRW', '1350'),
            'JPY/KRW': os.getenv('FX_JPYKRW', '9.0'),
            'EUR/KRW': os.getenv('FX_EURKRW', '1470'),
        }

    def _write_report_to_sheets(self, report: dict):
        """리포트를 Google Sheets weekly_reports / monthly_reports 워크시트에 기록."""
        sheet_id = os.getenv('GOOGLE_SHEET_ID', '')
        if not sheet_id:
            return

        report_type = report.get('type', 'periodic')
        if report_type == 'weekly':
            worksheet = os.getenv('WEEKLY_REPORTS_WORKSHEET', 'weekly_reports')
        else:
            worksheet = os.getenv('MONTHLY_REPORTS_WORKSHEET', 'monthly_reports')

        try:
            from ..utils.sheets import open_sheet
            from datetime import datetime, timezone
            ws = open_sheet(sheet_id, worksheet)
            headers = [
                'recorded_at', 'period', 'total_orders',
                'total_revenue_krw', 'gross_margin_pct', 'growth_pct',
            ]
            existing = ws.get_all_values()
            if not existing or existing[0] != headers:
                ws.clear()
                ws.append_row(headers)
            now_str = datetime.now(timezone.utc).isoformat()
            period = report.get('week_start') or report.get('year_month', '')
            growth = report.get('growth_pct') or report.get('mom_growth_pct', 0)
            ws.append_row([
                now_str, period,
                report.get('total_orders', 0),
                report.get('total_revenue_krw', 0),
                report.get('gross_margin_pct', 0),
                growth,
            ])
            logger.info("Report written to Sheets worksheet '%s'", worksheet)
        except Exception as exc:
            logger.warning("Failed to write report to Sheets: %s", exc)
