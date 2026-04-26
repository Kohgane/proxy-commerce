"""일일 운영 요약 + 통합 모닝 브리핑 생성/발송 모듈."""

import os
import logging
from datetime import date, datetime, timezone, timedelta

try:
    from zoneinfo import ZoneInfo
    _KST = ZoneInfo('Asia/Seoul')
except ImportError:
    # Python 3.8 이하 폴백
    _KST = timezone(timedelta(hours=9))

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
        """일일 운영 요약 데이터 생성."""
        if date_str is None:
            date_str = str(date.today())

        try:
            revenue = self.reporter.daily_revenue(date_str)
        except Exception as exc:
            logger.warning("daily_revenue(%s) failed, using defaults: %s", date_str, exc)
            revenue = {
                'date': date_str,
                'total_orders': 0,
                'total_revenue_krw': 0,
                'total_cost_krw': 0,
                'gross_profit_krw': 0,
                'gross_margin_pct': 0.0,
                'by_vendor': {},
                'by_channel': {},
                'top_products': [],
            }

        try:
            order_stats = self.order_tracker.get_stats()
        except Exception as exc:
            logger.warning("get_stats() failed, using defaults: %s", exc)
            order_stats = {'total': 0, 'by_status': {}, 'by_vendor': {}, 'avg_processing_days': 0.0}

        try:
            pending_orders = self.order_tracker.get_pending_orders()
        except Exception as exc:
            logger.warning("get_pending_orders() failed, using defaults: %s", exc)
            pending_orders = []

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
        pending = summary.get('pending_orders', [])
        alerts = summary.get('alerts', [])

        date_str = summary.get('date', '')
        total_revenue = rev.get('total_revenue_krw', 0)
        total_orders = rev.get('total_orders', 0)
        margin_pct = rev.get('gross_margin_pct', 0.0)

        by_vendor = rev.get('by_vendor', {})
        vendor_parts = []
        vendor_kr = {'porter': '포터', 'memo_paris': '메모파리'}
        for v, vdata in by_vendor.items():
            kr_name = vendor_kr.get(v, v)
            vendor_parts.append(f"{kr_name} {vdata.get('orders', 0)}")
        vendor_str = ', '.join(vendor_parts) if vendor_parts else '-'

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
        """일일 요약 생성 + 텔레그램/이메일 발송."""
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
        """경고/알림 체크."""
        alerts: list[str] = []

        stale_days = int(os.getenv('ALERT_STALE_ORDER_DAYS', '7'))
        forwarder_days = int(os.getenv('ALERT_FORWARDER_DAYS', '5'))
        fx_threshold = float(os.getenv('ALERT_FX_CHANGE_PCT', '3.0'))

        now = datetime.now(timezone.utc)

        for r in pending_orders:
            status = str(r.get('status', ''))
            order_id = r.get('order_id', '')
            vendor = str(r.get('vendor', '')).lower()

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

        fx_alerts = self._check_fx_alerts(fx_threshold)
        alerts.extend(fx_alerts)

        return alerts

    def _check_fx_alerts(self, threshold_pct: float) -> list[str]:
        """환율 급변 경고."""
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


# ─────────────────────────────────────────────────────────
# 통합 모닝 브리핑 — 일일/환율/가격 조정을 하나의 텔레그램으로
# ─────────────────────────────────────────────────────────

def _fx_arrow(change_pct: float) -> tuple:
    """환율 변동률 → (화살표, 부호, 급변강조)."""
    if change_pct > 0.1:
        arrow = "⬆"
        sign = "+"
    elif change_pct < -0.1:
        arrow = "⬇"
        sign = ""
    else:
        arrow = "━"
        sign = ""

    if abs(change_pct) >= 3:
        strong = "↑↑" if change_pct > 0 else "↓↓"
    else:
        strong = ""
    return arrow, sign, strong


def format_morning_briefing(
    daily_summary: dict = None,
    fx_data: dict = None,
    pricing_summary: dict = None,
    fx_history: dict = None,
) -> str:
    """통합 모닝 브리핑 — 일일 요약 + 환율 + 가격 조정.

    Args:
        daily_summary: DailySummaryGenerator.generate_summary() 결과 또는 평탄 dict
        fx_data: {"USDKRW": 1450.0, "JPYKRW": 9.2, "EURKRW": 1560.0}
        pricing_summary: {"checked": 0, "to_adjust": 0}
        fx_history: {"USDKRW": {"current": 1450, "previous": 1443}, ...}

    Returns:
        텔레그램 발송용 멀티라인 문자열.
    """
    daily_summary = daily_summary or {}
    fx_data = fx_data or {}
    pricing_summary = pricing_summary or {}
    fx_history = fx_history or {}

    now = datetime.now(_KST)
    yesterday = (now - timedelta(days=1)).strftime('%m-%d')
    weekday_kr = ['월', '화', '수', '목', '금', '토', '일'][now.weekday()]

    lines = []
    lines.append(f"🌅 [모닝 브리핑] {now.strftime('%Y-%m-%d')} ({weekday_kr})")
    lines.append("━" * 24)
    lines.append("")

    # 1. 어제 운영 현황 — daily_summary는 generate_summary() 결과(중첩) 또는 평탄 둘 다 처리
    rev = daily_summary.get('revenue', daily_summary)
    total_orders = rev.get('total_orders', 0)
    total_revenue = rev.get('total_revenue_krw', rev.get('total_revenue', 0))
    margin = rev.get('gross_margin_pct', rev.get('avg_margin', 0))
    low_stock = daily_summary.get('low_stock_count', 0)

    lines.append(f"📊 어제({yesterday}) 운영 현황")
    lines.append(f"• 총 주문: {total_orders}건")
    lines.append(f"• 총 매출: ₩{total_revenue:,}")
    lines.append(f"• 평균 마진: {margin:.1f}%")
    lines.append(f"• 재고 부족: {low_stock}개 SKU")
    lines.append("")

    # 2. 환율 (화살표 포함)
    lines.append("💱 환율 현황")
    if fx_data:
        for pair_name, rate in fx_data.items():
            prev = fx_history.get(pair_name, {}).get('previous')
            display = pair_name.replace('KRW', '/KRW')
            if prev and prev > 0:
                change_pct = ((rate - prev) / prev) * 100
                arrow, sign, strong = _fx_arrow(change_pct)
                line = f"• {display}: {rate:,.1f}원 {arrow} {sign}{change_pct:.1f}%"
                if strong:
                    line += f" {strong}"
                lines.append(line)
            else:
                lines.append(f"• {display}: {rate:,.1f}원")
    else:
        lines.append("• 데이터 없음")
    lines.append("")

    # 3. 자동 가격 조정
    lines.append("💰 자동 가격 조정 (DRY RUN)")
    lines.append(f"• 검토 SKU: {pricing_summary.get('checked', 0)}개")
    lines.append(f"• 조정 필요: {pricing_summary.get('to_adjust', 0)}개")
    lines.append("")

    # 4. 급변/이상 알림
    alerts = []
    for pair_name, rate in fx_data.items():
        prev = fx_history.get(pair_name, {}).get('previous')
        if prev and prev > 0:
            change_pct = ((rate - prev) / prev) * 100
            if abs(change_pct) >= 3:
                arrow_strong = "↑↑" if change_pct > 0 else "↓↓"
                alerts.append(f"• 환율 급변: {pair_name} {change_pct:+.1f}% {arrow_strong}")

    if pricing_summary.get('to_adjust', 0) > 5:
        alerts.append(f"• 가격 조정 필요 SKU 다수: {pricing_summary['to_adjust']}개")

    if alerts:
        lines.append("⚠️ 알림")
        lines.extend(alerts)
        lines.append("")

    lines.append("━" * 24)
    return "\n".join(lines)
