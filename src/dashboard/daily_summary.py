"""일일 운영 요약 생성 + 발송 모듈."""

import os
import logging
from datetime import date, datetime, timezone

logger = logging.getLogger(__name__)


class DailySummaryGenerator:
    """일일 운영 요약 생성 + 발송."""

    def __init__(self):
        from .order_status import OrderStatusTracker
        from .revenue_report import RevenueReporter

        self.order_tracker = OrderStatusTracker()
        self.reporter = RevenueReporter(self.order_tracker)

    # ── 공개 API ────────────────────────────────────────────

    def generate_summary(self, date_str: str = None) -> dict:
        """일일 운영 요약 데이터 생성.

        Returns:
        {
            'date': '2026-03-09',
            'revenue': {...},
            'order_stats': {...},
            'pending_orders': [...],
            'alerts': [...],
        }
        """
        if date_str is None:
            date_str = str(date.today())

        revenue = self.reporter.daily_revenue(date_str)
        order_stats = self.order_tracker.get_stats()
        pending_orders = self.order_tracker.get_pending_orders()
        alerts = self._check_alerts(order_stats, pending_orders)

        return {
            'date': date_str,
            'revenue': revenue,
            'order_stats': order_stats,
            'pending_orders': pending_orders,
            'alerts': alerts,
        }

    def format_telegram(self, summary: dict) -> str:
        """텔레그램 메시지 형식으로 포맷팅."""
        rev = summary.get('revenue', {})
        _ = summary.get('order_stats', {})
        pending = summary.get('pending_orders', [])
        alerts = summary.get('alerts', [])

        date_str = summary.get('date', '')
        total_revenue = rev.get('total_revenue_krw', 0)
        total_orders = rev.get('total_orders', 0)
        margin_pct = rev.get('gross_margin_pct', 0.0)

        # 벤더별 주문 수
        by_vendor = rev.get('by_vendor', {})
        vendor_parts = []
        vendor_kr = {'porter': '포터', 'memo_paris': '메모파리'}
        for v, vdata in by_vendor.items():
            kr_name = vendor_kr.get(v, v)
            vendor_parts.append(f"{kr_name} {vdata.get('orders', 0)}")
        vendor_str = ', '.join(vendor_parts) if vendor_parts else '-'

        # 미완료 주문 현황
        by_status: dict[str, int] = {}
        for r in pending:
            s = str(r.get('status', ''))
            by_status[s] = by_status.get(s, 0) + 1

        status_kr = {
            'new': '신규접수',
            'routed': '라우팅완료',
            'ordered': '발주완료',
            'shipped_vendor': '벤더발송',
            'at_forwarder': '배대지도착',
            'shipped_domestic': '국내배송중',
        }

        pending_total = len(pending)
        pending_lines = []
        for status_key, kr_name in status_kr.items():
            cnt = by_status.get(status_key, 0)
            if cnt > 0:
                pending_lines.append(f"  ├ {kr_name}: {cnt}건")
        if pending_lines:
            pending_lines[-1] = pending_lines[-1].replace('├', '└')

        pending_block = '\n'.join(pending_lines) if pending_lines else '  └ 없음'

        # 알림
        alert_block = ''
        if alerts:
            alert_lines = '\n'.join(f"  - {a}" for a in alerts)
            alert_block = f"\n\n⚠️ 알림:\n{alert_lines}"

        msg = (
            f"📊 [일일 리포트] {date_str}\n"
            f"\n"
            f"💰 매출: ₩{total_revenue:,.0f}\n"
            f"📦 주문: {total_orders}건 ({vendor_str})\n"
            f"📈 마진: {margin_pct:.1f}%\n"
            f"\n"
            f"🔄 미완료 주문: {pending_total}건\n"
            f"{pending_block}"
            f"{alert_block}"
        )
        return msg

    def format_email_html(self, summary: dict) -> str:
        """이메일 HTML 형식으로 포맷팅."""
        rev = summary.get('revenue', {})
        _ = summary.get('order_stats', {})
        alerts = summary.get('alerts', [])
        date_str = summary.get('date', '')
        pending = summary.get('pending_orders', [])

        total_revenue = rev.get('total_revenue_krw', 0)
        total_orders = rev.get('total_orders', 0)
        margin_pct = rev.get('gross_margin_pct', 0.0)
        pending_total = len(pending)

        by_vendor = rev.get('by_vendor', {})
        vendor_rows_html = ''
        for v, vdata in by_vendor.items():
            vendor_rows_html += (
                f"<tr><td>{v}</td>"
                f"<td>{vdata.get('orders', 0)}</td>"
                f"<td>₩{vdata.get('revenue_krw', 0):,}</td>"
                f"<td>{vdata.get('margin_pct', 0):.1f}%</td></tr>"
            )

        alert_html = ''
        if alerts:
            items = ''.join(f"<li>{a}</li>" for a in alerts)
            alert_html = f"<h3>⚠️ 알림</h3><ul>{items}</ul>"

        html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>일일 리포트 {date_str}</title></head>
<body style="font-family: sans-serif; max-width: 600px; margin: 0 auto;">
  <h2>📊 일일 리포트 — {date_str}</h2>
  <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse; width:100%;">
    <tr><th>항목</th><th>값</th></tr>
    <tr><td>매출</td><td>₩{total_revenue:,}</td></tr>
    <tr><td>주문 수</td><td>{total_orders}건</td></tr>
    <tr><td>마진</td><td>{margin_pct:.1f}%</td></tr>
    <tr><td>미완료 주문</td><td>{pending_total}건</td></tr>
  </table>
  <h3>벤더별 현황</h3>
  <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse; width:100%;">
    <tr><th>벤더</th><th>주문</th><th>매출</th><th>마진</th></tr>
    {vendor_rows_html}
  </table>
  {alert_html}
</body>
</html>"""
        return html

    def send_daily_summary(self, date_str: str = None):
        """일일 요약 생성 + 텔레그램/이메일 발송.

        환경변수:
        - DAILY_SUMMARY_ENABLED (기본 1)
        - TELEGRAM_ENABLED (기본 1)
        - EMAIL_ENABLED (기본 0)
        """
        enabled = os.getenv('DAILY_SUMMARY_ENABLED', '1') == '1'
        if not enabled:
            logger.info("DAILY_SUMMARY_ENABLED=0, skipping")
            return

        summary = self.generate_summary(date_str)

        telegram_enabled = os.getenv('TELEGRAM_ENABLED', '1') == '1'
        if telegram_enabled:
            try:
                from ..utils.telegram import send_tele
                msg = self.format_telegram(summary)
                send_tele(msg)
                logger.info("Daily summary sent via Telegram")
            except Exception as exc:
                logger.warning("Telegram send failed: %s", exc)

        email_enabled = os.getenv('EMAIL_ENABLED', '0') == '1'
        if email_enabled:
            try:
                from ..utils.emailer import send_mail
                html = self.format_email_html(summary)
                send_mail(f"[일일 리포트] {summary['date']}", html)
                logger.info("Daily summary sent via Email")
            except Exception as exc:
                logger.warning("Email send failed: %s", exc)

        return summary

    # ── 내부 헬퍼 ───────────────────────────────────────────

    def _check_alerts(self, order_stats: dict, pending_orders: list) -> list:
        """경고/알림 체크.

        체크 항목:
        - 발주 후 N일 이상 경과한 주문 (기본 7일, ALERT_STALE_ORDER_DAYS)
        - 배대지 도착 후 N일 이상 경과 (기본 5일, ALERT_FORWARDER_DAYS)
        - 환율 급변 (전일 대비 3% 이상 변동, ALERT_FX_CHANGE_PCT)
        """
        alerts: list[str] = []

        stale_days = int(os.getenv('ALERT_STALE_ORDER_DAYS', '7'))
        forwarder_days = int(os.getenv('ALERT_FORWARDER_DAYS', '5'))
        fx_threshold = float(os.getenv('ALERT_FX_CHANGE_PCT', '3.0'))

        now = datetime.now(timezone.utc)

        for r in pending_orders:
            status = str(r.get('status', ''))
            order_id = r.get('order_id', '')
            vendor = str(r.get('vendor', '')).lower()

            # 발주 완료 후 stale_days 이상 경과한 주문
            if status == 'ordered':
                try:
                    updated = datetime.fromisoformat(
                        str(r.get('status_updated_at', '')).replace('Z', '+00:00')
                    )
                    delta_days = (now - updated).days
                    if delta_days >= stale_days:
                        alerts.append(
                            f"주문 #{order_id} 발주 후 {delta_days}일 경과 ({vendor})"
                        )
                except (ValueError, TypeError):
                    pass

            # 배대지 도착 후 forwarder_days 이상 경과
            if status == 'at_forwarder':
                try:
                    updated = datetime.fromisoformat(
                        str(r.get('status_updated_at', '')).replace('Z', '+00:00')
                    )
                    delta_days = (now - updated).days
                    if delta_days >= forwarder_days:
                        alerts.append(
                            f"주문 #{order_id} 배대지 도착 후 {delta_days}일 경과"
                        )
                except (ValueError, TypeError):
                    pass

        # 환율 급변 경고 (환경변수 기반 단순 비교)
        fx_alerts = self._check_fx_alerts(fx_threshold)
        alerts.extend(fx_alerts)

        return alerts

    def _check_fx_alerts(self, threshold_pct: float) -> list[str]:
        """환율 급변 경고 (전일 대비 변동 체크).

        현재 구현: 환경변수 기준값과 DEFAULT 값 비교.
        """
        # Import DEFAULT_FX_RATES from price.py to compare current env-based rates
        # against the module-level defaults as a proxy for "yesterday's rate"
        from ..price import DEFAULT_FX_RATES

        alerts = []
        checks = [
            ('FX_JPYKRW', 'JPY/KRW', float(DEFAULT_FX_RATES['JPYKRW'])),
            ('FX_EURKRW', 'EUR/KRW', float(DEFAULT_FX_RATES['EURKRW'])),
            ('FX_USDKRW', 'USD/KRW', float(DEFAULT_FX_RATES['USDKRW'])),
        ]
        for env_key, label, default_val in checks:
            try:
                current = float(os.getenv(env_key, str(default_val)))
                change_pct = abs(current - default_val) / default_val * 100
                if change_pct >= threshold_pct:
                    direction = '상승' if current > default_val else '하락'
                    alerts.append(
                        f"{label} 환율 {change_pct:.1f}% {direction} (현재: {current})"
                    )
            except (ValueError, TypeError):
                pass

        return alerts
