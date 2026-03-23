"""tests/test_bot_commands.py — 텔레그램 봇 커맨드 테스트."""
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


# ─── 샘플 데이터 ────────────────────────────────────────────

SAMPLE_STATS = {
    'total': 5,
    'by_status': {
        'new': 1,
        'routed': 2,
        'ordered': 1,
        'delivered': 1,
    },
}

SAMPLE_PENDING = [
    {'order_id': '1', 'sku': 'PTR-TNK-001', 'status': 'routed'},
    {'order_id': '2', 'sku': 'MMP-EDP-001', 'status': 'ordered'},
]

SAMPLE_REVENUE = {
    'total_orders': 3,
    'total_revenue_krw': 900000,
    'total_margin_krw': 180000,
    'avg_margin_pct': 20.0,
    'by_vendor': {'PORTER': {'revenue_krw': 600000, 'orders': 2}},
}

SAMPLE_RATES = {
    'USDKRW': '1350',
    'JPYKRW': '9.0',
    'EURKRW': '1470',
    'fetched_at': '2026-03-23T10:00:00+00:00',
    'provider': 'frankfurter',
}


# ══════════════════════════════════════════════════════════
# cmd_status 테스트
# ══════════════════════════════════════════════════════════

class TestCmdStatus:
    def test_returns_string(self):
        """cmd_status()는 문자열을 반환해야 한다."""
        with patch('src.dashboard.order_status.OrderStatusTracker') as MockTracker:
            inst = MockTracker.return_value
            inst.get_stats.return_value = SAMPLE_STATS
            inst.get_pending_orders.return_value = SAMPLE_PENDING
            from src.bot.commands import cmd_status
            result = cmd_status()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_contains_total(self):
        """주문 현황에 전체 주문 수가 포함되어야 한다."""
        with patch('src.dashboard.order_status.OrderStatusTracker') as MockTracker:
            inst = MockTracker.return_value
            inst.get_stats.return_value = SAMPLE_STATS
            inst.get_pending_orders.return_value = SAMPLE_PENDING
            from src.bot.commands import cmd_status
            result = cmd_status()
        assert '5' in result

    def test_error_handling(self):
        """예외 발생 시 에러 메시지를 반환해야 한다."""
        with patch('src.dashboard.order_status.OrderStatusTracker', side_effect=Exception("sheets error")):
            from src.bot.commands import cmd_status
            result = cmd_status()
        assert '오류' in result or 'error' in result.lower()


# ══════════════════════════════════════════════════════════
# cmd_revenue 테스트
# ══════════════════════════════════════════════════════════

class TestCmdRevenue:
    def _mock_reporter(self):
        mock = MagicMock()
        mock.daily_revenue.return_value = SAMPLE_REVENUE
        mock.weekly_revenue.return_value = SAMPLE_REVENUE
        mock.monthly_revenue.return_value = SAMPLE_REVENUE
        return mock

    def test_today(self):
        with patch('src.dashboard.revenue_report.RevenueReporter', return_value=self._mock_reporter()):
            from src.bot.commands import cmd_revenue
            result = cmd_revenue('today')
        assert isinstance(result, str)
        assert '900' in result or '매출' in result

    def test_week(self):
        with patch('src.dashboard.revenue_report.RevenueReporter', return_value=self._mock_reporter()):
            from src.bot.commands import cmd_revenue
            result = cmd_revenue('week')
        assert isinstance(result, str)

    def test_month(self):
        with patch('src.dashboard.revenue_report.RevenueReporter', return_value=self._mock_reporter()):
            from src.bot.commands import cmd_revenue
            result = cmd_revenue('month')
        assert isinstance(result, str)

    def test_invalid_period(self):
        with patch('src.dashboard.revenue_report.RevenueReporter', return_value=self._mock_reporter()):
            from src.bot.commands import cmd_revenue
            result = cmd_revenue('invalid')
        assert '유효하지 않은' in result or '오류' in result

    def test_default_period(self):
        with patch('src.dashboard.revenue_report.RevenueReporter', return_value=self._mock_reporter()):
            from src.bot.commands import cmd_revenue
            result = cmd_revenue()
        assert isinstance(result, str)


# ══════════════════════════════════════════════════════════
# cmd_stock 테스트
# ══════════════════════════════════════════════════════════

class TestCmdStock:
    def _mock_sync(self, rows=None):
        mock = MagicMock()
        mock._get_active_rows.return_value = rows or [
            {'sku': 'PTR-TNK-001', 'title': 'Tanker', 'vendor': 'PORTER', 'stock': 1},
            {'sku': 'MMP-EDP-001', 'title': 'Memo', 'vendor': 'MEMO_PARIS', 'stock': 5},
        ]
        return mock

    def test_low_filter(self):
        with patch('src.inventory.inventory_sync.InventorySync', return_value=self._mock_sync()):
            from src.bot.commands import cmd_stock
            result = cmd_stock('low')
        assert isinstance(result, str)

    def test_all_filter(self):
        with patch('src.inventory.inventory_sync.InventorySync', return_value=self._mock_sync()):
            from src.bot.commands import cmd_stock
            result = cmd_stock('all')
        assert isinstance(result, str)

    def test_default_filter(self):
        with patch('src.inventory.inventory_sync.InventorySync', return_value=self._mock_sync()):
            from src.bot.commands import cmd_stock
            result = cmd_stock()
        assert isinstance(result, str)


# ══════════════════════════════════════════════════════════
# cmd_fx 테스트
# ══════════════════════════════════════════════════════════

class TestCmdFx:
    def test_returns_rates(self):
        with patch('src.fx.provider.FXProvider') as MockProvider, \
             patch('src.fx.history.FXHistory') as MockHistory:
            MockProvider.return_value.get_rates.return_value = SAMPLE_RATES
            MockHistory.return_value.get_latest_rates.return_value = SAMPLE_RATES
            from src.bot.commands import cmd_fx
            result = cmd_fx()
        assert 'USD' in result or 'JPY' in result or '환율' in result

    def test_fallback_no_history(self):
        """FXHistory 없어도 동작해야 한다."""
        with patch('src.fx.provider.FXProvider') as MockProvider, \
             patch('src.fx.history.FXHistory', side_effect=Exception("no history")):
            MockProvider.return_value.get_rates.return_value = SAMPLE_RATES
            from src.bot.commands import cmd_fx
            result = cmd_fx()
        assert isinstance(result, str)


# ══════════════════════════════════════════════════════════
# cmd_help 테스트
# ══════════════════════════════════════════════════════════

class TestCmdHelp:
    def test_contains_commands(self):
        from src.bot.commands import cmd_help
        result = cmd_help()
        assert '/status' in result
        assert '/revenue' in result
        assert '/stock' in result
        assert '/fx' in result

    def test_returns_string(self):
        from src.bot.commands import cmd_help
        assert isinstance(cmd_help(), str)


# ══════════════════════════════════════════════════════════
# _dispatch 테스트 (telegram_bot.py)
# ══════════════════════════════════════════════════════════

class TestDispatch:
    def test_status_command(self):
        with patch('src.dashboard.order_status.OrderStatusTracker') as MockTracker:
            inst = MockTracker.return_value
            inst.get_stats.return_value = SAMPLE_STATS
            inst.get_pending_orders.return_value = []
            from src.bot.telegram_bot import _dispatch
            result = _dispatch('/status')
        assert isinstance(result, str)

    def test_help_command(self):
        from src.bot.telegram_bot import _dispatch
        result = _dispatch('/help')
        assert '/status' in result

    def test_unknown_command(self):
        from src.bot.telegram_bot import _dispatch
        result = _dispatch('/unknown')
        assert '알 수 없는' in result or 'help' in result.lower()

    def test_revenue_with_arg(self):
        with patch('src.dashboard.revenue_report.RevenueReporter') as MockReporter:
            inst = MockReporter.return_value
            inst.weekly_revenue.return_value = SAMPLE_REVENUE
            from src.bot.telegram_bot import _dispatch
            result = _dispatch('/revenue week')
        assert isinstance(result, str)

    def test_bot_name_suffix(self):
        """'/status@MyBot' 형식 커맨드도 처리돼야 한다."""
        with patch('src.dashboard.order_status.OrderStatusTracker') as MockTracker:
            inst = MockTracker.return_value
            inst.get_stats.return_value = SAMPLE_STATS
            inst.get_pending_orders.return_value = []
            from src.bot.telegram_bot import _dispatch
            result = _dispatch('/status@ProxyBot')
        assert isinstance(result, str)

    def test_empty_text(self):
        from src.bot.telegram_bot import _dispatch
        result = _dispatch('')
        assert isinstance(result, str)
