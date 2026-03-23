"""텔레그램 봇 커맨드 구현 — dashboard, fx, inventory 모듈 연동."""

import logging
import os
from datetime import date

from .formatters import format_message

logger = logging.getLogger(__name__)


def cmd_status() -> str:
    """/status — 미완료 주문 현황 요약."""
    try:
        from ..dashboard.order_status import OrderStatusTracker
        tracker = OrderStatusTracker()
        stats = tracker.get_stats()
        pending = tracker.get_pending_orders()
        return format_message('status', stats, pending=pending)
    except Exception as exc:
        logger.error("cmd_status 오류: %s", exc)
        return format_message('error', f'주문 현황 조회 실패: {exc}')


def cmd_revenue(period: str = 'today') -> str:
    """/revenue [today|week|month] — 매출 요약."""
    period = period.strip().lower()
    try:
        from ..dashboard.revenue_report import RevenueReporter
        reporter = RevenueReporter()

        if period == 'today':
            data = reporter.daily_revenue()
            label = f"오늘 ({date.today().isoformat()})"
        elif period == 'week':
            data = reporter.weekly_revenue()
            label = "이번 주"
        elif period == 'month':
            data = reporter.monthly_revenue()
            label = f"이번 달 ({date.today().strftime('%Y-%m')})"
        else:
            return format_message('error', f'유효하지 않은 기간: {period}\n사용법: /revenue [today|week|month]')

        return format_message('revenue', data, label=label)
    except Exception as exc:
        logger.error("cmd_revenue 오류: %s", exc)
        return format_message('error', f'매출 조회 실패: {exc}')


def cmd_stock(filter_type: str = 'low') -> str:
    """/stock [low|all] — 재고 현황."""
    filter_type = filter_type.strip().lower()
    try:
        from ..inventory.inventory_sync import InventorySync
        sync = InventorySync()
        rows = sync._get_active_rows()

        low_threshold = int(os.getenv('LOW_STOCK_THRESHOLD', '3'))

        if filter_type == 'low':
            items = [r for r in rows if int(r.get('stock', 0)) <= low_threshold]
            label = f"저재고 상품 (임계값: {low_threshold})"
        else:
            items = rows
            label = "전체 재고"

        return format_message('stock', items, label=label)
    except Exception as exc:
        logger.error("cmd_stock 오류: %s", exc)
        return format_message('error', f'재고 조회 실패: {exc}')


def cmd_fx() -> str:
    """/fx — 현재 환율 + 변동률."""
    try:
        from ..fx.provider import FXProvider
        from ..fx.history import FXHistory
        provider = FXProvider()
        rates = provider.get_rates()

        # 이전 환율 비교 (이력 있는 경우)
        prev_rates = None
        try:
            history = FXHistory()
            prev_rates = history.get_latest_rates()
        except Exception:
            pass  # 이력 없으면 변동률 생략

        return format_message('fx', rates, prev_rates=prev_rates)
    except Exception as exc:
        logger.error("cmd_fx 오류: %s", exc)
        return format_message('error', f'환율 조회 실패: {exc}')


def cmd_help() -> str:
    """/help — 도움말."""
    return (
        "*🤖 Proxy Commerce 봇 도움말*\n\n"
        "사용 가능한 커맨드:\n\n"
        "📦 `/status` — 미완료 주문 현황 요약\n"
        "💰 `/revenue [today|week|month]` — 매출 요약\n"
        "  예) `/revenue week`\n\n"
        "📊 `/stock [low|all]` — 재고 현황\n"
        "  예) `/stock low` (저재고만 표시)\n\n"
        "💱 `/fx` — 현재 환율 + 변동률\n"
        "❓ `/help` — 이 도움말\n"
    )
