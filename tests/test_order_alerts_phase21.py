"""tests/test_order_alerts_phase21.py — Phase 21 주문 알림 강화 단위 테스트."""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


# ──────────────────────────────────────────────────────────
# 헬퍼 팩토리
# ──────────────────────────────────────────────────────────

def _make_order(
    order_id='ORD-001',
    platform='coupang',
    status='ACCEPT',
):
    """테스트용 정규화 주문 샘플."""
    return {
        'platform': platform,
        'order_id': order_id,
        'order_number': f'CP-{order_id}',
        'product_names': ['무선 이어폰 프리미엄'],
        'quantities': [1],
        'total_price': 55000,
        'currency': 'KRW',
        'buyer_name': '홍길동',
        'buyer_phone': '01012341234',
        'status': status,
        'created_at': '2024-01-15T10:30:00',
    }


# ──────────────────────────────────────────────────────────
# TestTemplates
# ──────────────────────────────────────────────────────────

class TestTemplates:
    """메시지 템플릿 테스트."""

    def test_render_order_received(self):
        """주문 접수 메시지 렌더링."""
        from src.order_alerts.templates import render_order_received
        order = _make_order()
        result = render_order_received(order)
        assert '신규 주문 접수' in result
        assert 'ORD-001' in result
        assert '홍길동' in result
        assert '55,000원' in result

    def test_render_payment_confirmed(self):
        """결제 확인 메시지 렌더링."""
        from src.order_alerts.templates import render_payment_confirmed
        order = _make_order()
        result = render_payment_confirmed(order)
        assert '결제 확인 완료' in result
        assert 'ORD-001' in result

    def test_render_shipping(self):
        """배송 시작 메시지 렌더링."""
        from src.order_alerts.templates import render_shipping
        order = _make_order()
        result = render_shipping(order)
        assert '배송 시작' in result
        assert '발송' in result

    def test_render_shipping_with_tracking(self):
        """운송장번호 포함 배송 메시지."""
        from src.order_alerts.templates import render_shipping
        order = _make_order()
        order['tracking_number'] = 'TRACK-12345'
        result = render_shipping(order)
        assert 'TRACK-12345' in result

    def test_render_delivered(self):
        """배송 완료 메시지 렌더링."""
        from src.order_alerts.templates import render_delivered
        order = _make_order()
        result = render_delivered(order)
        assert '배송 완료' in result
        assert '홍길동' in result

    def test_render_cancelled(self):
        """주문 취소 메시지 렌더링."""
        from src.order_alerts.templates import render_cancelled
        order = _make_order()
        result = render_cancelled(order)
        assert '주문 취소' in result
        assert 'ORD-001' in result

    def test_render_cancelled_with_reason(self):
        """취소 사유 포함 메시지."""
        from src.order_alerts.templates import render_cancelled
        order = _make_order()
        order['cancel_reason'] = '고객 변심'
        result = render_cancelled(order)
        assert '고객 변심' in result

    def test_render_refunded(self):
        """환불 처리 메시지 렌더링."""
        from src.order_alerts.templates import render_refunded
        order = _make_order()
        result = render_refunded(order)
        assert '환불 처리' in result
        assert '55,000원' in result

    def test_render_for_status_dispatches_correctly(self):
        """render_for_status 라우팅."""
        from src.order_alerts.templates import render_for_status
        order = _make_order()
        for status, keyword in [
            ('order_received', '신규 주문'),
            ('payment_confirmed', '결제 확인'),
            ('shipping', '배송 시작'),
            ('delivered', '배송 완료'),
            ('cancelled', '주문 취소'),
            ('refunded', '환불 처리'),
        ]:
            result = render_for_status(order, status)
            assert keyword in result, f"status={status} 키워드 '{keyword}' 없음"

    def test_render_for_status_unknown_falls_back(self):
        """알 수 없는 상태는 order_received로 폴백."""
        from src.order_alerts.templates import render_for_status
        order = _make_order()
        result = render_for_status(order, 'UNKNOWN_STATUS')
        assert '신규 주문' in result

    def test_render_naver_platform(self):
        """네이버 플랫폼 주문 렌더링."""
        from src.order_alerts.templates import render_order_received
        order = _make_order(platform='naver')
        result = render_order_received(order)
        assert '네이버' in result

    def test_render_missing_products(self):
        """상품 정보 없는 경우 폴백."""
        from src.order_alerts.templates import render_order_received
        order = _make_order()
        order['product_names'] = []
        order['quantities'] = []
        result = render_order_received(order)
        assert '상품 정보 없음' in result


# ──────────────────────────────────────────────────────────
# TestTelegramNotifier
# ──────────────────────────────────────────────────────────

class TestTelegramNotifier:
    """TelegramNotifier 테스트."""

    def _make_notifier(self):
        from src.order_alerts.telegram_notifier import TelegramNotifier
        return TelegramNotifier(bot_token='TEST_TOKEN', chat_id='CHAT_123')

    def _mock_ok_response(self):
        m = MagicMock()
        m.raise_for_status = MagicMock()
        m.json.return_value = {'ok': True}
        return m

    def test_is_configured_true(self):
        """토큰과 채팅ID 있으면 configured."""
        notifier = self._make_notifier()
        assert notifier.is_configured is True

    def test_is_configured_false_when_missing(self):
        """토큰 없으면 not configured."""
        from src.order_alerts.telegram_notifier import TelegramNotifier
        notifier = TelegramNotifier(bot_token='', chat_id='')
        assert notifier.is_configured is False

    @patch('src.order_alerts.telegram_notifier.requests.post')
    def test_send_message_success(self, mock_post):
        """메시지 발송 성공."""
        mock_post.return_value = self._mock_ok_response()
        notifier = self._make_notifier()
        result = notifier.send_message('테스트 메시지')
        assert result is True
        mock_post.assert_called_once()
        payload = mock_post.call_args.kwargs.get('json', {})
        assert payload['text'] == '테스트 메시지'
        assert payload['chat_id'] == 'CHAT_123'

    @patch('src.order_alerts.telegram_notifier.requests.post')
    def test_send_message_with_reply_markup(self, mock_post):
        """Inline Keyboard 포함 메시지 발송."""
        mock_post.return_value = self._mock_ok_response()
        notifier = self._make_notifier()
        keyboard = {'inline_keyboard': [[{'text': '확인', 'callback_data': 'ok'}]]}
        result = notifier.send_message('메시지', reply_markup=keyboard)
        assert result is True
        payload = mock_post.call_args.kwargs.get('json', {})
        assert 'reply_markup' in payload

    @patch('src.order_alerts.telegram_notifier.requests.post')
    def test_send_message_failure(self, mock_post):
        """네트워크 오류 시 False 반환."""
        import requests as req
        mock_post.side_effect = req.exceptions.RequestException("timeout")
        notifier = self._make_notifier()
        result = notifier.send_message('실패 테스트')
        assert result is False

    def test_send_message_no_credentials(self):
        """자격증명 없으면 False 반환 (API 호출 없음)."""
        from src.order_alerts.telegram_notifier import TelegramNotifier
        notifier = TelegramNotifier(bot_token='', chat_id='')
        result = notifier.send_message('테스트')
        assert result is False

    def test_build_order_inline_keyboard_structure(self):
        """Inline Keyboard 구조 검증."""
        notifier = self._make_notifier()
        keyboard = notifier.build_order_inline_keyboard('ORDER-001')
        assert 'inline_keyboard' in keyboard
        buttons = keyboard['inline_keyboard'][0]
        assert len(buttons) == 3
        texts = [b['text'] for b in buttons]
        assert '✅ 주문 승인' in texts
        assert '🚚 배송 시작' in texts
        assert '❌ 주문 취소' in texts

    def test_build_order_inline_keyboard_callback_data(self):
        """Inline Keyboard callback_data 검증."""
        notifier = self._make_notifier()
        keyboard = notifier.build_order_inline_keyboard('ORDER-999')
        buttons = keyboard['inline_keyboard'][0]
        callbacks = {b['text']: b['callback_data'] for b in buttons}
        assert callbacks['✅ 주문 승인'] == 'approve:ORDER-999'
        assert callbacks['🚚 배송 시작'] == 'ship:ORDER-999'
        assert callbacks['❌ 주문 취소'] == 'cancel:ORDER-999'

    @patch('src.order_alerts.telegram_notifier.requests.post')
    def test_send_order_alert_calls_send_message(self, mock_post):
        """send_order_alert가 메시지와 키보드 함께 발송."""
        mock_post.return_value = self._mock_ok_response()
        notifier = self._make_notifier()
        order = _make_order()
        result = notifier.send_order_alert(order, 'order_received')
        assert result is True
        payload = mock_post.call_args.kwargs.get('json', {})
        assert 'reply_markup' in payload
        assert '신규 주문' in payload['text']

    @patch('src.order_alerts.telegram_notifier.requests.post')
    def test_send_order_alert_each_status(self, mock_post):
        """각 상태별 send_order_alert 동작."""
        mock_post.return_value = self._mock_ok_response()
        notifier = self._make_notifier()
        order = _make_order()
        statuses = ['order_received', 'payment_confirmed', 'shipping', 'delivered', 'cancelled', 'refunded']
        for status in statuses:
            mock_post.reset_mock()
            result = notifier.send_order_alert(order, status)
            assert result is True, f"status={status} 발송 실패"

    def test_build_keyboard_from_env(self, monkeypatch):
        """환경변수에서 자격증명 로드."""
        monkeypatch.setenv('ORDER_ALERT_TELEGRAM_BOT_TOKEN', 'ENV_TOKEN')
        monkeypatch.setenv('ORDER_ALERT_TELEGRAM_CHAT_ID', 'ENV_CHAT')
        from src.order_alerts.telegram_notifier import TelegramNotifier
        notifier = TelegramNotifier()
        assert notifier.is_configured is True


# ──────────────────────────────────────────────────────────
# TestAlertManager
# ──────────────────────────────────────────────────────────

class TestAlertManager:
    """AlertManager 테스트."""

    def _make_manager(self):
        """모킹된 AlertManager 생성."""
        from src.order_alerts.alert_manager import AlertManager
        from src.order_alerts.alert_dispatcher import AlertDispatcher
        from src.order_alerts.telegram_notifier import TelegramNotifier

        mock_dispatcher = MagicMock(spec=AlertDispatcher)
        mock_dispatcher.send_new_order_alert.return_value = True
        mock_dispatcher.send_status_change_alert.return_value = True

        mock_notifier = MagicMock(spec=TelegramNotifier)
        mock_notifier.send_order_alert.return_value = True

        manager = AlertManager(dispatcher=mock_dispatcher, notifier=mock_notifier)
        return manager, mock_dispatcher, mock_notifier

    def test_dispatch_accept_status(self):
        """ACCEPT 상태 → order_received 알림."""
        manager, _, mock_notifier = self._make_manager()
        order = _make_order(status='ACCEPT')
        result = manager.dispatch(order)
        assert result is True
        mock_notifier.send_order_alert.assert_called_once_with(order, 'order_received')

    def test_dispatch_payed_status(self):
        """PAYED 상태 → payment_confirmed 알림."""
        manager, _, mock_notifier = self._make_manager()
        order = _make_order(status='PAYED')
        result = manager.dispatch(order)
        assert result is True
        mock_notifier.send_order_alert.assert_called_once_with(order, 'payment_confirmed')

    def test_dispatch_delivering_status(self):
        """DELIVERING 상태 → shipping 알림."""
        manager, _, mock_notifier = self._make_manager()
        order = _make_order(status='DELIVERING')
        result = manager.dispatch(order)
        assert result is True
        mock_notifier.send_order_alert.assert_called_once_with(order, 'shipping')

    def test_dispatch_delivered_status(self):
        """DELIVERED 상태 → delivered 알림."""
        manager, _, mock_notifier = self._make_manager()
        order = _make_order(status='DELIVERED')
        result = manager.dispatch(order)
        assert result is True
        mock_notifier.send_order_alert.assert_called_once_with(order, 'delivered')

    def test_dispatch_canceled_status(self):
        """CANCELED 상태 → cancelled 알림."""
        manager, _, mock_notifier = self._make_manager()
        order = _make_order(status='CANCELED')
        result = manager.dispatch(order)
        assert result is True
        mock_notifier.send_order_alert.assert_called_once_with(order, 'cancelled')

    def test_dispatch_returned_status(self):
        """RETURNED 상태 → refunded 알림."""
        manager, _, mock_notifier = self._make_manager()
        order = _make_order(status='RETURNED')
        result = manager.dispatch(order)
        assert result is True
        mock_notifier.send_order_alert.assert_called_once_with(order, 'refunded')

    def test_dispatch_internal_status(self):
        """내부 상태 코드 직접 사용."""
        manager, _, mock_notifier = self._make_manager()
        order = _make_order(status='order_received')
        result = manager.dispatch(order)
        assert result is True
        mock_notifier.send_order_alert.assert_called_once_with(order, 'order_received')

    def test_dispatch_unknown_status_uses_dispatcher(self):
        """알 수 없는 상태는 기존 dispatcher 사용."""
        manager, mock_dispatcher, mock_notifier = self._make_manager()
        order = _make_order(status='UNKNOWN')
        result = manager.dispatch(order)
        assert result is True
        mock_dispatcher.send_new_order_alert.assert_called_once_with(order)
        mock_notifier.send_order_alert.assert_not_called()

    def test_dispatch_status_change_known_status(self):
        """알려진 상태 변경 → notifier 사용."""
        manager, mock_dispatcher, mock_notifier = self._make_manager()
        order = _make_order()
        result = manager.dispatch_status_change(order, 'DELIVERING')
        assert result is True
        mock_notifier.send_order_alert.assert_called_once_with(order, 'shipping')
        mock_dispatcher.send_status_change_alert.assert_not_called()

    def test_dispatch_status_change_unknown_status(self):
        """알 수 없는 상태 변경 → dispatcher 폴백."""
        manager, mock_dispatcher, mock_notifier = self._make_manager()
        order = _make_order()
        result = manager.dispatch_status_change(order, 'INSTRUCT_SOMETHING')
        assert result is True
        mock_dispatcher.send_status_change_alert.assert_called_once()
        mock_notifier.send_order_alert.assert_not_called()

    def test_dispatch_status_change_internal_refunded(self):
        """내부 상태 refunded 변경."""
        manager, _, mock_notifier = self._make_manager()
        order = _make_order()
        result = manager.dispatch_status_change(order, 'refunded')
        assert result is True
        mock_notifier.send_order_alert.assert_called_once_with(order, 'refunded')

    def test_default_init(self):
        """기본값으로 초기화 (환경변수 없이도 오류 없음)."""
        from src.order_alerts.alert_manager import AlertManager
        manager = AlertManager()
        assert manager is not None


# ──────────────────────────────────────────────────────────
# TestCallbackHandler
# ──────────────────────────────────────────────────────────

class TestCallbackHandler:
    """CallbackHandler 테스트."""

    def _make_callback(self, data: str, callback_id: str = 'CB001') -> dict:
        return {'id': callback_id, 'data': data}

    def test_handle_approve(self):
        """approve 콜백 처리."""
        from src.order_alerts.callback_handler import CallbackHandler
        handler = CallbackHandler()
        result = handler.handle(self._make_callback('approve:ORDER-001'))
        assert result['action'] == 'approve'
        assert result['order_id'] == 'ORDER-001'
        assert '승인' in result['response_text']

    def test_handle_ship(self):
        """ship 콜백 처리."""
        from src.order_alerts.callback_handler import CallbackHandler
        handler = CallbackHandler()
        result = handler.handle(self._make_callback('ship:ORDER-002'))
        assert result['action'] == 'ship'
        assert result['order_id'] == 'ORDER-002'
        assert '배송' in result['response_text']

    def test_handle_cancel(self):
        """cancel 콜백 처리."""
        from src.order_alerts.callback_handler import CallbackHandler
        handler = CallbackHandler()
        result = handler.handle(self._make_callback('cancel:ORDER-003'))
        assert result['action'] == 'cancel'
        assert result['order_id'] == 'ORDER-003'
        assert '취소' in result['response_text']

    def test_handle_unknown_action(self):
        """알 수 없는 액션 처리."""
        from src.order_alerts.callback_handler import CallbackHandler
        handler = CallbackHandler()
        result = handler.handle(self._make_callback('refund:ORDER-004'))
        assert result['action'] == 'refund'
        assert result['order_id'] == 'ORDER-004'

    def test_handle_no_colon(self):
        """콜론 없는 callback_data."""
        from src.order_alerts.callback_handler import CallbackHandler
        handler = CallbackHandler()
        result = handler.handle(self._make_callback('just_data'))
        assert result['action'] == 'unknown'
        assert result['order_id'] == 'just_data'

    def test_handle_returns_dict_keys(self):
        """반환 딕셔너리 키 검증."""
        from src.order_alerts.callback_handler import CallbackHandler
        handler = CallbackHandler()
        result = handler.handle(self._make_callback('approve:ORD-100'))
        assert set(result.keys()) == {'action', 'order_id', 'response_text'}

    def test_handle_empty_callback_query(self):
        """빈 callback_query 처리."""
        from src.order_alerts.callback_handler import CallbackHandler
        handler = CallbackHandler()
        result = handler.handle({})
        assert result['action'] == 'unknown'
        assert isinstance(result['response_text'], str)

    def test_handle_order_id_with_hyphens(self):
        """하이픈 포함 주문 ID 처리."""
        from src.order_alerts.callback_handler import CallbackHandler
        handler = CallbackHandler()
        result = handler.handle(self._make_callback('approve:CP-ORD-2024-001'))
        assert result['action'] == 'approve'
        assert result['order_id'] == 'CP-ORD-2024-001'


# ──────────────────────────────────────────────────────────
# TestCmdOrderAlerts
# ──────────────────────────────────────────────────────────

class TestCmdOrderAlerts:
    """cmd_order_alerts 봇 커맨드 테스트."""

    def _make_orders(self):
        return [_make_order('ORD-001'), _make_order('ORD-002', status='PAYED')]

    @patch('src.order_alerts.order_tracker.OrderTracker.get_alerted_orders')
    def test_cmd_order_alerts_status(self, mock_get):
        """status 서브커맨드 — 최근 알림 목록 반환."""
        mock_get.return_value = self._make_orders()
        from src.bot.commands import cmd_order_alerts
        result = cmd_order_alerts('status')
        assert '주문 알림' in result
        mock_get.assert_called_once_with(limit=10)

    @patch('src.order_alerts.order_tracker.OrderTracker.get_alerted_orders')
    def test_cmd_order_alerts_default_arg(self, mock_get):
        """인수 없을 때 기본 동작."""
        mock_get.return_value = []
        from src.bot.commands import cmd_order_alerts
        result = cmd_order_alerts()
        assert isinstance(result, str)
        assert len(result) > 0

    @patch('src.order_alerts.order_tracker.OrderTracker.get_alerted_orders')
    def test_cmd_order_alerts_error_handling(self, mock_get):
        """예외 발생 시 오류 메시지 반환."""
        mock_get.side_effect = Exception("DB 연결 실패")
        from src.bot.commands import cmd_order_alerts
        result = cmd_order_alerts('status')
        assert '실패' in result or '오류' in result
