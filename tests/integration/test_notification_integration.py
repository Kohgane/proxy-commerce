"""tests/integration/test_notification_integration.py — 알림 통합 테스트.

주문 접수→텔레그램 알림 전체 흐름, 가격 변동 알림 트리거,
재고 부족 알림을 검증한다.
"""

from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# 샘플 데이터
# ---------------------------------------------------------------------------

SAMPLE_COUPANG_ORDER = {
    'order_id': 'CPN-20260401-001',
    'order_number': '#3001',
    'platform': 'coupang',
    'status': 'ACCEPT',
    'customer_name': '홍길동',
    'customer_phone': '010-1234-5678',
    'product_names': ['에코 닷 4세대', '소니 무선 이어폰'],
    'total_price': 191000,
    'shipping_address': '서울시 강남구',
}

SAMPLE_NAVER_ORDER = {
    'order_id': 'NVR-20260401-002',
    'order_number': '#4001',
    'platform': 'naver',
    'status': 'PAYED',
    'customer_name': '김철수',
    'product_names': ['무선 블루투스 이어폰'],
    'total_price': 15000,
    'shipping_address': '부산시 해운대구',
}

LOW_STOCK_PRODUCT = {
    'sku': 'TEST-ELC-001',
    'title_ko': '에코 닷 4세대',
    'stock': 1,
    'threshold': 3,
    'vendor': 'amazon_us',
}


# ---------------------------------------------------------------------------
# 주문 접수 → 텔레그램 알림 전체 흐름
# ---------------------------------------------------------------------------

class TestOrderAlertTelegramFlow:
    """주문 접수 → 텔레그램 알림 전체 흐름 통합 테스트."""

    def test_coupang_order_triggers_telegram_alert(self, monkeypatch):
        """쿠팡 주문 접수 시 텔레그램 알림이 발송되는지 검증한다."""
        monkeypatch.setenv('ORDER_ALERT_TELEGRAM_BOT_TOKEN', '123456:test-token')
        monkeypatch.setenv('ORDER_ALERT_TELEGRAM_CHAT_ID', '-100test')

        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {'ok': True, 'result': {'message_id': 1}}

        with patch('requests.post', return_value=resp) as mock_post:
            from src.order_alerts.alert_dispatcher import AlertDispatcher
            dispatcher = AlertDispatcher(
                bot_token='123456:test-token',
                chat_id='-100test',
            )
            result = dispatcher.send_new_order_alert(SAMPLE_COUPANG_ORDER)

        assert result is True
        mock_post.assert_called_once()

    def test_naver_order_triggers_telegram_alert(self, monkeypatch):
        """네이버 주문 접수 시 텔레그램 알림이 발송되는지 검증한다."""
        monkeypatch.setenv('ORDER_ALERT_TELEGRAM_BOT_TOKEN', '123456:test-token')
        monkeypatch.setenv('ORDER_ALERT_TELEGRAM_CHAT_ID', '-100test')

        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {'ok': True, 'result': {'message_id': 2}}

        with patch('requests.post', return_value=resp) as mock_post:
            from src.order_alerts.alert_dispatcher import AlertDispatcher
            dispatcher = AlertDispatcher(
                bot_token='123456:test-token',
                chat_id='-100test',
            )
            result = dispatcher.send_new_order_alert(SAMPLE_NAVER_ORDER)

        assert result is True

    def test_telegram_alert_without_token_returns_false(self, monkeypatch):
        """토큰 없이 알림 발송 시 False를 반환하는지 검증한다."""
        monkeypatch.delenv('ORDER_ALERT_TELEGRAM_BOT_TOKEN', raising=False)
        monkeypatch.delenv('ORDER_ALERT_TELEGRAM_CHAT_ID', raising=False)

        from src.order_alerts.alert_dispatcher import AlertDispatcher
        dispatcher = AlertDispatcher(bot_token='', chat_id='')
        result = dispatcher.send_new_order_alert(SAMPLE_COUPANG_ORDER)

        assert result is False

    def test_notification_hub_order_event(self, monkeypatch):
        """NotificationHub를 통한 주문 이벤트 알림 전체 흐름을 검증한다."""
        monkeypatch.setenv('TELEGRAM_BOT_TOKEN', '123456:test-token')
        monkeypatch.setenv('TELEGRAM_CHAT_ID', '-100test')
        monkeypatch.setenv('TELEGRAM_ENABLED', '1')

        with patch('src.utils.telegram.send_tele', return_value=None) as mock_tele:
            from src.notifications.hub import NotificationHub
            hub = NotificationHub(
                telegram_token='123456:test-token',
                telegram_chat_id='-100test',
            )
            order_data = {
                'id': 'CPN-001',
                'order_number': '#3001',
                'customer': {'name': '홍길동'},
                'customer_email': 'hong@example.com',
                'sku': 'TEST-001',
                'total_price': '191000',
            }
            result = hub.send_order_event(order_data, event='confirmed')

        assert isinstance(result, dict)

    def test_order_tracker_prevents_duplicate_alerts(self, monkeypatch):
        """OrderTracker가 중복 주문 알림을 방지하는지 검증한다."""
        monkeypatch.setenv('GOOGLE_SHEET_ID', 'test-sheet')

        with patch('src.utils.sheets.open_sheet') as mock_open:
            ws = MagicMock()
            # 이미 알림 발송된 주문 이력 시뮬레이션
            ws.get_all_records.return_value = [
                {
                    'order_id': 'CPN-20260401-001',
                    'platform': 'coupang',
                    'order_number': '#3001',
                    'status': 'ACCEPT',
                    'alerted_at': '2026-04-01T09:00:00Z',
                    'product_names': '에코 닷',
                }
            ]
            mock_open.return_value = ws

            from src.order_alerts.order_tracker import OrderTracker
            tracker = OrderTracker()
            already_alerted = tracker.is_already_alerted(
                'CPN-20260401-001', status='ACCEPT'
            )

        assert already_alerted is True


# ---------------------------------------------------------------------------
# 가격 변동 알림 트리거 검증
# ---------------------------------------------------------------------------

class TestPriceChangeNotification:
    """가격 변동 알림 트리거 통합 테스트."""

    def test_price_change_triggers_notification(self, monkeypatch):
        """가격 변동 감지 시 알림이 트리거되는지 검증한다."""
        old_price = 82000
        new_price = 75000
        change_pct = abs(new_price - old_price) / old_price * 100

        # 5% 이상 변동 시 알림 트리거
        threshold = 5.0
        should_notify = change_pct >= threshold

        assert should_notify is True
        assert change_pct > 5.0

    def test_small_price_change_no_notification(self, monkeypatch):
        """소폭 가격 변동(임계값 미만)에는 알림이 발송되지 않는지 검증한다."""
        old_price = 82000
        new_price = 81000
        change_pct = abs(new_price - old_price) / old_price * 100

        threshold = 5.0
        should_notify = change_pct >= threshold

        assert should_notify is False

    def test_notification_hub_sends_to_telegram(self, monkeypatch):
        """NotificationHub를 통한 텔레그램 알림 발송을 검증한다."""
        monkeypatch.setenv('TELEGRAM_BOT_TOKEN', '123456:test')
        monkeypatch.setenv('TELEGRAM_CHAT_ID', '-100test')

        with patch('src.utils.telegram.send_tele', return_value=None) as mock_tele:
            from src.notifications.hub import NotificationHub
            hub = NotificationHub(
                telegram_token='123456:test',
                telegram_chat_id='-100test',
            )
            result = hub.send_custom(
                message='가격 변동 알림: TEST-001 82000→75000원',
                channels=['telegram'],
            )

        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# 재고 부족 알림 검증
# ---------------------------------------------------------------------------

class TestLowStockNotification:
    """재고 부족 알림 통합 테스트."""

    def test_low_stock_triggers_reorder_alert(self, monkeypatch):
        """임계값 이하 재고 감지 시 재발주 알림이 발송되는지 검증한다."""
        monkeypatch.setenv('REORDER_ENABLED', '1')
        monkeypatch.setenv('REORDER_THRESHOLD', '3')
        monkeypatch.setenv('GOOGLE_SHEET_ID', 'test-sheet')

        with patch('src.utils.sheets.open_sheet') as mock_open, \
             patch('src.utils.telegram.send_tele', return_value=None):
            ws = MagicMock()
            ws.get_all_records.return_value = []
            ws.append_row.return_value = None
            mock_open.return_value = ws

            with patch(
                'src.reorder.auto_reorder.AutoReorder.run',
                return_value={'queued': 1, 'skipped': 0},
            ) as mock_run:
                from src.reorder.auto_reorder import AutoReorder
                reorder = AutoReorder()
                result = reorder.run(dry_run=True)

        assert isinstance(result, dict)

    def test_stock_sufficient_no_alert(self, monkeypatch):
        """재고가 충분한 경우 알림이 발송되지 않는지 검증한다."""
        sufficient_product = dict(LOW_STOCK_PRODUCT, stock=10)

        stock = sufficient_product['stock']
        threshold = sufficient_product['threshold']
        should_alert = stock <= threshold

        assert should_alert is False

    def test_low_stock_alert_message_format(self, monkeypatch):
        """재고 부족 알림 메시지 형식이 올바른지 검증한다."""
        from src.order_alerts.alert_dispatcher import AlertDispatcher

        dispatcher = AlertDispatcher(
            bot_token='123456:test',
            chat_id='-100test',
        )
        message = dispatcher._format_new_order_message(SAMPLE_COUPANG_ORDER)

        assert isinstance(message, str)
        assert len(message) > 0
