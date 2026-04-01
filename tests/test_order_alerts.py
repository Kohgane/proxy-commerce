"""tests/test_order_alerts.py — 주문 알림 시스템 단위 테스트."""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


# ──────────────────────────────────────────────────────────
# 헬퍼 팩토리
# ──────────────────────────────────────────────────────────

def _make_coupang_order(order_id='ORD-001', status='ACCEPT'):
    """쿠팡 정규화 주문 샘플."""
    return {
        'platform': 'coupang',
        'order_id': order_id,
        'order_number': f'CP-{order_id}',
        'product_names': ['무선 이어폰 프리미엄', '충전 케이블'],
        'quantities': [1, 2],
        'total_price': 55000,
        'currency': 'KRW',
        'buyer_name': '홍길동',
        'buyer_phone': '01012341234',
        'status': status,
        'created_at': '2024-01-15T10:30:00',
        'raw': {},
    }


def _make_naver_order(order_id='NOD-001', status='PAYED'):
    """네이버 정규화 주문 샘플."""
    return {
        'platform': 'naver',
        'order_id': order_id,
        'order_number': f'NV-{order_id}',
        'product_names': ['스마트워치 SE'],
        'quantities': [1],
        'total_price': 89000,
        'currency': 'KRW',
        'buyer_name': '이순신',
        'buyer_phone': '01098765432',
        'status': status,
        'created_at': '2024-01-15T11:00:00',
        'raw': {},
    }


# ──────────────────────────────────────────────────────────
# CoupangOrderPoller
# ──────────────────────────────────────────────────────────

class TestCoupangOrderPoller:
    """쿠팡 주문 폴러 테스트."""

    def _make_api_response(self, orders: list):
        """쿠팡 API 응답 mock 생성."""
        m = MagicMock()
        m.raise_for_status = MagicMock()
        m.json.return_value = {
            'data': {'orderSheets': orders}
        }
        return m

    def test_init_from_env(self, monkeypatch):
        """환경변수에서 자격증명 로드."""
        monkeypatch.setenv('COUPANG_VENDOR_ID', 'V123')
        monkeypatch.setenv('COUPANG_ACCESS_KEY', 'AK456')
        monkeypatch.setenv('COUPANG_SECRET_KEY', 'SK789')
        from src.order_alerts.coupang_order_poller import CoupangOrderPoller
        poller = CoupangOrderPoller()
        assert poller._vendor_id == 'V123'
        assert poller._access_key == 'AK456'
        assert poller._secret_key == 'SK789'

    def test_init_explicit_params(self):
        """명시적 파라미터로 초기화."""
        from src.order_alerts.coupang_order_poller import CoupangOrderPoller
        poller = CoupangOrderPoller(
            vendor_id='V1',
            access_key='AK1',
            secret_key='SK1',
            poll_interval=120,
        )
        assert poller._vendor_id == 'V1'
        assert poller._poll_interval == 120

    def test_fetch_new_orders_no_credentials_raises(self):
        """자격증명 없으면 ValueError."""
        from src.order_alerts.coupang_order_poller import CoupangOrderPoller
        poller = CoupangOrderPoller(vendor_id='', access_key='', secret_key='')
        with pytest.raises(ValueError, match='자격증명'):
            poller.fetch_new_orders()

    @patch('src.order_alerts.coupang_order_poller.requests.get')
    def test_fetch_new_orders_success(self, mock_get):
        """정상 주문 조회."""
        raw_order = {
            'orderId': 'ORD-001',
            'orderCode': 'CP-ORD-001',
            'orderItems': [
                {'productName': '무선 이어폰', 'quantity': 1, 'orderPrice': 50000},
            ],
            'buyer': {'name': '홍길동', 'safeNumber': '010-****-1234'},
            'status': 'ACCEPT',
            'orderedAt': '2024-01-15T10:30:00',
        }
        mock_get.return_value = self._make_api_response([raw_order])
        from src.order_alerts.coupang_order_poller import CoupangOrderPoller
        poller = CoupangOrderPoller(vendor_id='V1', access_key='AK1', secret_key='SK1')
        orders = poller.fetch_new_orders()
        assert len(orders) == 1
        assert orders[0]['platform'] == 'coupang'
        assert orders[0]['order_id'] == 'ORD-001'
        assert orders[0]['product_names'] == ['무선 이어폰']

    @patch('src.order_alerts.coupang_order_poller.requests.get')
    def test_fetch_new_orders_empty(self, mock_get):
        """주문 없을 때 빈 리스트 반환."""
        mock_get.return_value = self._make_api_response([])
        from src.order_alerts.coupang_order_poller import CoupangOrderPoller
        poller = CoupangOrderPoller(vendor_id='V1', access_key='AK1', secret_key='SK1')
        orders = poller.fetch_new_orders()
        assert orders == []

    @patch('src.order_alerts.coupang_order_poller.requests.get')
    def test_fetch_new_orders_multiple(self, mock_get):
        """다수 주문 조회."""
        raw_orders = [
            {
                'orderId': f'ORD-{i:03d}',
                'orderCode': f'CP-{i:03d}',
                'orderItems': [{'productName': f'상품{i}', 'quantity': 1, 'orderPrice': 10000}],
                'buyer': {'name': f'구매자{i}'},
                'status': 'ACCEPT',
                'orderedAt': '2024-01-15T10:30:00',
            }
            for i in range(5)
        ]
        mock_get.return_value = self._make_api_response(raw_orders)
        from src.order_alerts.coupang_order_poller import CoupangOrderPoller
        poller = CoupangOrderPoller(vendor_id='V1', access_key='AK1', secret_key='SK1')
        orders = poller.fetch_new_orders()
        assert len(orders) == 5

    def test_normalize_orders_total_price(self):
        """주문 총액 계산 (수량 × 단가)."""
        from src.order_alerts.coupang_order_poller import CoupangOrderPoller
        raw = [{
            'orderId': 'ORD-001',
            'orderCode': 'CP-001',
            'orderItems': [
                {'productName': '상품A', 'quantity': 2, 'orderPrice': 15000},
                {'productName': '상품B', 'quantity': 1, 'orderPrice': 20000},
            ],
            'buyer': {},
            'status': 'ACCEPT',
            'orderedAt': '',
        }]
        result = CoupangOrderPoller._normalize_orders(raw)
        assert result[0]['total_price'] == 50000  # 2*15000 + 1*20000

    def test_normalize_orders_platform(self):
        """정규화 결과에 platform='coupang' 포함."""
        from src.order_alerts.coupang_order_poller import CoupangOrderPoller
        raw = [{'orderId': '1', 'orderCode': '1', 'orderItems': [], 'buyer': {}, 'status': 'ACCEPT', 'orderedAt': ''}]
        result = CoupangOrderPoller._normalize_orders(raw)
        assert result[0]['platform'] == 'coupang'
        assert result[0]['currency'] == 'KRW'

    def test_poll_interval_default(self, monkeypatch):
        """기본 폴링 간격 300초."""
        monkeypatch.delenv('ORDER_POLL_INTERVAL_SECONDS', raising=False)
        from src.order_alerts.coupang_order_poller import CoupangOrderPoller
        poller = CoupangOrderPoller(vendor_id='V1', access_key='AK1', secret_key='SK1')
        assert poller.poll_interval == 300

    def test_poll_interval_from_env(self, monkeypatch):
        """환경변수로 폴링 간격 설정."""
        monkeypatch.setenv('ORDER_POLL_INTERVAL_SECONDS', '60')
        from src.order_alerts.coupang_order_poller import CoupangOrderPoller
        poller = CoupangOrderPoller(vendor_id='V1', access_key='AK1', secret_key='SK1')
        assert poller.poll_interval == 60

    def test_build_auth_headers_contains_authorization(self):
        """인증 헤더에 Authorization 포함."""
        from src.order_alerts.coupang_order_poller import CoupangOrderPoller
        poller = CoupangOrderPoller(vendor_id='V1', access_key='AK1', secret_key='SK1')
        headers = poller._build_auth_headers('GET', '/test', 'q=1')
        assert 'Authorization' in headers
        assert 'CEA algorithm=HmacSHA256' in headers['Authorization']
        assert 'AK1' in headers['Authorization']

    @patch('src.order_alerts.coupang_order_poller.requests.get')
    def test_poll_loop_calls_callback(self, mock_get):
        """poll_loop: 주문 있을 때 콜백 호출."""
        import threading
        raw = [{
            'orderId': 'ORD-001', 'orderCode': 'CP-001',
            'orderItems': [{'productName': '상품', 'quantity': 1, 'orderPrice': 10000}],
            'buyer': {}, 'status': 'ACCEPT', 'orderedAt': '',
        }]
        mock_get.return_value = self._make_api_response(raw)

        from src.order_alerts.coupang_order_poller import CoupangOrderPoller
        poller = CoupangOrderPoller(vendor_id='V1', access_key='AK1', secret_key='SK1', poll_interval=0)
        stop = threading.Event()
        received = []

        def callback(orders):
            received.extend(orders)
            stop.set()

        with patch('src.order_alerts.coupang_order_poller.time.sleep'):
            t = threading.Thread(target=poller.poll_loop, kwargs={'callback': callback, 'stop_event': stop})
            t.daemon = True
            t.start()
            t.join(timeout=2)

        assert len(received) > 0


# ──────────────────────────────────────────────────────────
# NaverOrderPoller
# ──────────────────────────────────────────────────────────

class TestNaverOrderPoller:
    """네이버 주문 폴러 테스트."""

    def _make_token_response(self):
        m = MagicMock()
        m.raise_for_status = MagicMock()
        m.json.return_value = {'access_token': 'test-token', 'expires_in': 3600}
        return m

    def _make_orders_response(self, orders: list):
        m = MagicMock()
        m.raise_for_status = MagicMock()
        m.json.return_value = {'data': orders}
        return m

    def test_init_from_env(self, monkeypatch):
        """환경변수에서 자격증명 로드."""
        monkeypatch.setenv('NAVER_COMMERCE_CLIENT_ID', 'NC123')
        monkeypatch.setenv('NAVER_COMMERCE_CLIENT_SECRET', 'NS456')
        from src.order_alerts.naver_order_poller import NaverOrderPoller
        poller = NaverOrderPoller()
        assert poller._client_id == 'NC123'
        assert poller._client_secret == 'NS456'

    def test_init_explicit_params(self):
        """명시적 파라미터로 초기화."""
        from src.order_alerts.naver_order_poller import NaverOrderPoller
        poller = NaverOrderPoller(client_id='NC1', client_secret='NS1', poll_interval=120)
        assert poller._client_id == 'NC1'
        assert poller._poll_interval == 120

    def test_fetch_new_orders_no_credentials_raises(self):
        """자격증명 없으면 ValueError."""
        from src.order_alerts.naver_order_poller import NaverOrderPoller
        poller = NaverOrderPoller(client_id='', client_secret='')
        with pytest.raises(ValueError, match='자격증명'):
            poller.fetch_new_orders()

    @patch('src.order_alerts.naver_order_poller.requests.get')
    @patch('src.order_alerts.naver_order_poller.requests.post')
    def test_fetch_new_orders_success(self, mock_post, mock_get):
        """정상 주문 조회."""
        mock_post.return_value = self._make_token_response()
        raw_order = {
            'productOrderId': 'NOD-001',
            'orderId': 'NV-001',
            'productOrder': {
                'productName': '스마트워치',
                'quantity': 1,
                'totalPaymentAmount': 89000,
                'productOrderStatus': 'PAYED',
            },
            'order': {
                'ordererName': '이순신',
                'ordererTel': '010-9876-5432',
                'paymentDate': '2024-01-15T11:00:00',
            },
        }
        mock_get.return_value = self._make_orders_response([raw_order])
        from src.order_alerts.naver_order_poller import NaverOrderPoller
        poller = NaverOrderPoller(client_id='NC1', client_secret='NS1')
        orders = poller.fetch_new_orders()
        assert len(orders) == 1
        assert orders[0]['platform'] == 'naver'
        assert orders[0]['order_id'] == 'NOD-001'
        assert orders[0]['product_names'] == ['스마트워치']

    @patch('src.order_alerts.naver_order_poller.requests.get')
    @patch('src.order_alerts.naver_order_poller.requests.post')
    def test_fetch_new_orders_empty(self, mock_post, mock_get):
        """주문 없을 때 빈 리스트."""
        mock_post.return_value = self._make_token_response()
        mock_get.return_value = self._make_orders_response([])
        from src.order_alerts.naver_order_poller import NaverOrderPoller
        poller = NaverOrderPoller(client_id='NC1', client_secret='NS1')
        orders = poller.fetch_new_orders()
        assert orders == []

    @patch('src.order_alerts.naver_order_poller.requests.post')
    def test_token_cached_within_expiry(self, mock_post):
        """토큰 캐싱 — 유효 기간 내 재발급 안 함."""
        mock_post.return_value = self._make_token_response()
        from src.order_alerts.naver_order_poller import NaverOrderPoller
        poller = NaverOrderPoller(client_id='NC1', client_secret='NS1')
        token1 = poller._get_access_token()
        token2 = poller._get_access_token()
        assert token1 == token2
        assert mock_post.call_count == 1

    def test_generate_client_secret_sign(self):
        """클라이언트 시크릿 서명 Base64 형식."""
        import base64
        from src.order_alerts.naver_order_poller import NaverOrderPoller
        poller = NaverOrderPoller(client_id='NC1', client_secret='secret')
        sign = poller._generate_client_secret_sign('1234567890')
        assert isinstance(sign, str)
        # Base64 디코딩 가능 여부 확인
        decoded = base64.b64decode(sign)
        assert len(decoded) == 32  # SHA-256 = 32바이트

    def test_normalize_orders_platform(self):
        """정규화 결과에 platform='naver' 포함."""
        from src.order_alerts.naver_order_poller import NaverOrderPoller
        raw = [{
            'productOrderId': 'NOD-001',
            'orderId': 'NV-001',
            'productOrder': {'productName': '상품', 'quantity': 1, 'totalPaymentAmount': 10000, 'productOrderStatus': 'PAYED'},
            'order': {'ordererName': '테스터', 'ordererTel': '01011112222', 'paymentDate': ''},
        }]
        result = NaverOrderPoller._normalize_orders(raw)
        assert result[0]['platform'] == 'naver'
        assert result[0]['currency'] == 'KRW'

    def test_normalize_orders_fields(self):
        """정규화 필드 검증."""
        from src.order_alerts.naver_order_poller import NaverOrderPoller
        raw = [{
            'productOrderId': 'NOD-999',
            'orderId': 'NV-999',
            'productOrder': {
                'productName': '무선충전기',
                'quantity': 3,
                'totalPaymentAmount': 30000,
                'productOrderStatus': 'PAYED',
            },
            'order': {'ordererName': '홍길동', 'ordererTel': '01099998888', 'paymentDate': '2024-01-20'},
        }]
        result = NaverOrderPoller._normalize_orders(raw)
        assert result[0]['quantities'] == [3]
        assert result[0]['total_price'] == 30000
        assert result[0]['buyer_name'] == '홍길동'


# ──────────────────────────────────────────────────────────
# AlertDispatcher
# ──────────────────────────────────────────────────────────

class TestAlertDispatcher:
    """알림 발송기 테스트."""

    def test_init_from_env(self, monkeypatch):
        """환경변수에서 토큰/채팅ID 로드."""
        monkeypatch.setenv('ORDER_ALERT_TELEGRAM_BOT_TOKEN', 'BOT123')
        monkeypatch.setenv('ORDER_ALERT_TELEGRAM_CHAT_ID', 'CHAT456')
        from src.order_alerts.alert_dispatcher import AlertDispatcher
        d = AlertDispatcher()
        assert d._bot_token == 'BOT123'
        assert d._chat_id == 'CHAT456'

    def test_is_configured_true(self):
        """토큰과 채팅ID 모두 있으면 configured=True."""
        from src.order_alerts.alert_dispatcher import AlertDispatcher
        d = AlertDispatcher(bot_token='BOT', chat_id='CHAT')
        assert d.is_configured is True

    def test_is_configured_false_no_token(self):
        """토큰 없으면 configured=False."""
        from src.order_alerts.alert_dispatcher import AlertDispatcher
        d = AlertDispatcher(bot_token='', chat_id='CHAT')
        assert d.is_configured is False

    def test_is_configured_false_no_chat_id(self):
        """채팅ID 없으면 configured=False."""
        from src.order_alerts.alert_dispatcher import AlertDispatcher
        d = AlertDispatcher(bot_token='BOT', chat_id='')
        assert d.is_configured is False

    def test_send_new_order_alert_no_config_returns_false(self):
        """설정 없으면 False 반환."""
        from src.order_alerts.alert_dispatcher import AlertDispatcher
        d = AlertDispatcher(bot_token='', chat_id='')
        result = d.send_new_order_alert(_make_coupang_order())
        assert result is False

    @patch('src.order_alerts.alert_dispatcher.requests.post')
    def test_send_new_order_alert_success(self, mock_post):
        """주문 알림 발송 성공."""
        mock_post.return_value = MagicMock(raise_for_status=MagicMock())
        from src.order_alerts.alert_dispatcher import AlertDispatcher
        d = AlertDispatcher(bot_token='BOT', chat_id='CHAT')
        result = d.send_new_order_alert(_make_coupang_order())
        assert result is True
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        payload = call_kwargs[1]['json']
        assert payload['chat_id'] == 'CHAT'
        assert '주문 접수' in payload['text']

    @patch('src.order_alerts.alert_dispatcher.requests.post')
    def test_send_status_change_alert(self, mock_post):
        """상태 변경 알림 발송."""
        mock_post.return_value = MagicMock(raise_for_status=MagicMock())
        from src.order_alerts.alert_dispatcher import AlertDispatcher
        d = AlertDispatcher(bot_token='BOT', chat_id='CHAT')
        result = d.send_status_change_alert(_make_coupang_order(), 'DELIVERING')
        assert result is True
        payload = mock_post.call_args[1]['json']
        assert '배송중' in payload['text']

    @patch('src.order_alerts.alert_dispatcher.requests.post')
    def test_send_bulk_alerts_count(self, mock_post):
        """일괄 발송 성공 건수."""
        mock_post.return_value = MagicMock(raise_for_status=MagicMock())
        from src.order_alerts.alert_dispatcher import AlertDispatcher
        d = AlertDispatcher(bot_token='BOT', chat_id='CHAT')
        orders = [_make_coupang_order(f'ORD-{i:03d}') for i in range(3)]
        count = d.send_bulk_alerts(orders)
        assert count == 3

    @patch('src.order_alerts.alert_dispatcher.requests.post')
    def test_send_naver_order_alert(self, mock_post):
        """네이버 주문 알림 발송."""
        mock_post.return_value = MagicMock(raise_for_status=MagicMock())
        from src.order_alerts.alert_dispatcher import AlertDispatcher
        d = AlertDispatcher(bot_token='BOT', chat_id='CHAT')
        result = d.send_new_order_alert(_make_naver_order())
        assert result is True
        payload = mock_post.call_args[1]['json']
        assert '네이버' in payload['text']

    def test_format_new_order_message_coupang(self):
        """쿠팡 신규 주문 메시지 포맷."""
        from src.order_alerts.alert_dispatcher import AlertDispatcher
        d = AlertDispatcher(bot_token='BOT', chat_id='CHAT')
        msg = d._format_new_order_message(_make_coupang_order('ORD-001'))
        assert '쿠팡' in msg
        assert 'ORD-001' in msg or 'CP-ORD-001' in msg
        assert '55,000원' in msg
        assert '홍길동' in msg

    def test_format_new_order_message_naver(self):
        """네이버 신규 주문 메시지 포맷."""
        from src.order_alerts.alert_dispatcher import AlertDispatcher
        d = AlertDispatcher(bot_token='BOT', chat_id='CHAT')
        msg = d._format_new_order_message(_make_naver_order())
        assert '네이버' in msg or 'naver' in msg.lower()

    def test_format_status_change_delivering(self):
        """배송중 상태 변경 메시지."""
        from src.order_alerts.alert_dispatcher import AlertDispatcher
        d = AlertDispatcher(bot_token='BOT', chat_id='CHAT')
        msg = d._format_status_change_message(_make_coupang_order(), 'DELIVERING')
        assert '배송중' in msg

    def test_format_status_change_delivered(self):
        """배송완료 상태 변경 메시지."""
        from src.order_alerts.alert_dispatcher import AlertDispatcher
        d = AlertDispatcher(bot_token='BOT', chat_id='CHAT')
        msg = d._format_status_change_message(_make_coupang_order(), 'DELIVERED')
        assert '배송완료' in msg

    def test_mask_phone_standard(self):
        """전화번호 마스킹."""
        from src.order_alerts.alert_dispatcher import AlertDispatcher
        masked = AlertDispatcher._mask_phone('01012341234')
        assert '****' in masked
        assert '1234' in masked
        assert '010' in masked

    def test_mask_phone_empty(self):
        """빈 전화번호 처리."""
        from src.order_alerts.alert_dispatcher import AlertDispatcher
        masked = AlertDispatcher._mask_phone('')
        assert masked == '(미공개)'

    @patch('src.order_alerts.alert_dispatcher.requests.post')
    def test_send_message_api_error_returns_false(self, mock_post):
        """API 오류 시 False 반환."""
        import requests as req
        mock_post.side_effect = req.exceptions.RequestException("connection error")
        from src.order_alerts.alert_dispatcher import AlertDispatcher
        d = AlertDispatcher(bot_token='BOT', chat_id='CHAT')
        result = d.send_custom_message('테스트')
        assert result is False

    @patch('src.order_alerts.alert_dispatcher.requests.post')
    def test_send_message_parse_mode_markdown(self, mock_post):
        """메시지 parse_mode가 Markdown."""
        mock_post.return_value = MagicMock(raise_for_status=MagicMock())
        from src.order_alerts.alert_dispatcher import AlertDispatcher
        d = AlertDispatcher(bot_token='BOT', chat_id='CHAT')
        d.send_custom_message('테스트')
        payload = mock_post.call_args[1]['json']
        assert payload['parse_mode'] == 'Markdown'


# ──────────────────────────────────────────────────────────
# OrderTracker
# ──────────────────────────────────────────────────────────

class TestOrderTracker:
    """주문 추적기 테스트."""

    def test_init_no_sheet_id(self):
        """Sheet ID 없으면 Sheets 저장 건너뜀."""
        from src.order_alerts.order_tracker import OrderTracker
        tracker = OrderTracker(sheet_id='')
        assert tracker.get_sheet_id() is None

    def test_mark_alerted_and_is_already_alerted(self):
        """알림 표시 후 중복 감지."""
        from src.order_alerts.order_tracker import OrderTracker
        tracker = OrderTracker(sheet_id='')
        tracker._cache_loaded = True  # Sheets 로드 건너뜀
        order = _make_coupang_order('ORD-001', 'ACCEPT')
        assert tracker.is_already_alerted('ORD-001', 'ACCEPT') is False
        tracker.mark_alerted(order)
        assert tracker.is_already_alerted('ORD-001', 'ACCEPT') is True

    def test_is_already_alerted_different_status(self):
        """다른 상태는 중복으로 보지 않음."""
        from src.order_alerts.order_tracker import OrderTracker
        tracker = OrderTracker(sheet_id='')
        tracker._cache_loaded = True
        order = _make_coupang_order('ORD-001', 'ACCEPT')
        tracker.mark_alerted(order)
        # 다른 상태는 아직 알림 안 됨
        assert tracker.is_already_alerted('ORD-001', 'DELIVERING') is False

    def test_is_already_alerted_no_status_checks_any(self):
        """상태 없이 조회 시 주문 자체 존재 여부."""
        from src.order_alerts.order_tracker import OrderTracker
        tracker = OrderTracker(sheet_id='')
        tracker._cache_loaded = True
        order = _make_coupang_order('ORD-001', 'ACCEPT')
        tracker.mark_alerted(order)
        assert tracker.is_already_alerted('ORD-001') is True
        assert tracker.is_already_alerted('ORD-999') is False

    def test_filter_new_orders(self):
        """신규 주문만 필터링."""
        from src.order_alerts.order_tracker import OrderTracker
        tracker = OrderTracker(sheet_id='')
        tracker._cache_loaded = True
        order1 = _make_coupang_order('ORD-001', 'ACCEPT')
        order2 = _make_coupang_order('ORD-002', 'ACCEPT')
        tracker.mark_alerted(order1)
        result = tracker.filter_new_orders([order1, order2])
        assert len(result) == 1
        assert result[0]['order_id'] == 'ORD-002'

    def test_filter_new_orders_all_new(self):
        """모두 신규인 경우."""
        from src.order_alerts.order_tracker import OrderTracker
        tracker = OrderTracker(sheet_id='')
        tracker._cache_loaded = True
        orders = [_make_coupang_order(f'ORD-{i:03d}') for i in range(5)]
        result = tracker.filter_new_orders(orders)
        assert len(result) == 5

    def test_filter_new_orders_all_seen(self):
        """모두 중복인 경우."""
        from src.order_alerts.order_tracker import OrderTracker
        tracker = OrderTracker(sheet_id='')
        tracker._cache_loaded = True
        orders = [_make_coupang_order(f'ORD-{i:03d}') for i in range(3)]
        for o in orders:
            tracker.mark_alerted(o)
        result = tracker.filter_new_orders(orders)
        assert result == []

    def test_should_send_status_alert_new(self):
        """새 상태는 알림 발송해야 함."""
        from src.order_alerts.order_tracker import OrderTracker
        tracker = OrderTracker(sheet_id='')
        tracker._cache_loaded = True
        assert tracker.should_send_status_alert('ORD-001', 'DELIVERING') is True

    def test_should_send_status_alert_duplicate(self):
        """이미 알림 보낸 상태는 False."""
        from src.order_alerts.order_tracker import OrderTracker
        tracker = OrderTracker(sheet_id='')
        tracker._cache_loaded = True
        order = _make_coupang_order('ORD-001', 'DELIVERING')
        tracker.mark_alerted(order, 'DELIVERING')
        assert tracker.should_send_status_alert('ORD-001', 'DELIVERING') is False

    def test_reset_memory_cache(self):
        """메모리 캐시 초기화."""
        from src.order_alerts.order_tracker import OrderTracker
        tracker = OrderTracker(sheet_id='')
        tracker._cache_loaded = True
        order = _make_coupang_order('ORD-001')
        tracker.mark_alerted(order)
        assert tracker.get_cache_size() > 0
        tracker.reset_memory_cache()
        assert tracker.get_cache_size() == 0

    def test_get_cache_size(self):
        """캐시 크기 반환."""
        from src.order_alerts.order_tracker import OrderTracker
        tracker = OrderTracker(sheet_id='')
        tracker._cache_loaded = True
        assert tracker.get_cache_size() == 0
        for i in range(3):
            tracker.mark_alerted(_make_coupang_order(f'ORD-{i:03d}'))
        assert tracker.get_cache_size() == 3

    @patch('src.order_alerts.order_tracker.OrderTracker._get_worksheet')
    def test_mark_alerted_saves_to_sheets(self, mock_ws_getter):
        """알림 표시 시 Sheets에도 저장."""
        mock_ws = MagicMock()
        mock_ws_getter.return_value = mock_ws
        from src.order_alerts.order_tracker import OrderTracker
        tracker = OrderTracker(sheet_id='SHEET123')
        tracker._cache_loaded = True
        order = _make_coupang_order('ORD-001')
        tracker.mark_alerted(order)
        mock_ws.append_row.assert_called_once()

    @patch('src.order_alerts.order_tracker.OrderTracker._get_worksheet')
    def test_get_alerted_orders_from_sheets(self, mock_ws_getter):
        """Sheets에서 이력 조회."""
        mock_ws = MagicMock()
        mock_ws.get_all_records.return_value = [
            {'order_id': 'ORD-001', 'platform': 'coupang', 'status': 'ACCEPT'},
            {'order_id': 'ORD-002', 'platform': 'naver', 'status': 'PAYED'},
        ]
        mock_ws_getter.return_value = mock_ws
        from src.order_alerts.order_tracker import OrderTracker
        tracker = OrderTracker(sheet_id='SHEET123')
        records = tracker.get_alerted_orders()
        assert len(records) == 2

    @patch('src.order_alerts.order_tracker.OrderTracker._get_worksheet')
    def test_load_cache_from_sheets(self, mock_ws_getter):
        """시작 시 Sheets에서 캐시 로드."""
        mock_ws = MagicMock()
        mock_ws.get_all_records.return_value = [
            {'order_id': 'ORD-001', 'status': 'ACCEPT'},
            {'order_id': 'ORD-002', 'status': 'PAYED'},
        ]
        mock_ws.get_all_values.return_value = [['order_id', 'platform', 'order_number', 'status', 'alerted_at', 'product_names']]
        mock_ws_getter.return_value = mock_ws
        from src.order_alerts.order_tracker import OrderTracker
        tracker = OrderTracker(sheet_id='SHEET123')
        tracker._load_cache_from_sheets()
        assert tracker.get_cache_size() == 2

    def test_get_order_history_no_sheets(self):
        """Sheets 없을 때 빈 리스트."""
        from src.order_alerts.order_tracker import OrderTracker
        tracker = OrderTracker(sheet_id='')
        result = tracker.get_order_history('ORD-001')
        assert result == []

    def test_worksheet_name_default(self, monkeypatch):
        """기본 워크시트 이름 확인."""
        monkeypatch.delenv('ORDER_ALERTS_WORKSHEET', raising=False)
        from src.order_alerts.order_tracker import OrderTracker
        tracker = OrderTracker(sheet_id='')
        assert tracker._worksheet == 'order_alerts'

    def test_worksheet_name_from_env(self, monkeypatch):
        """환경변수로 워크시트 이름 설정."""
        monkeypatch.setenv('ORDER_ALERTS_WORKSHEET', 'my_alerts')
        from src.order_alerts.order_tracker import OrderTracker
        tracker = OrderTracker(sheet_id='')
        assert tracker._worksheet == 'my_alerts'


# ──────────────────────────────────────────────────────────
# 통합: 폴링 → 필터링 → 발송
# ──────────────────────────────────────────────────────────

class TestOrderAlertIntegration:
    """주문 알림 통합 시나리오 테스트."""

    @patch('src.order_alerts.alert_dispatcher.requests.post')
    def test_end_to_end_new_order_flow(self, mock_post):
        """신규 주문 → 필터링 → 발송 → 중복 방지."""
        mock_post.return_value = MagicMock(raise_for_status=MagicMock())
        from src.order_alerts.alert_dispatcher import AlertDispatcher
        from src.order_alerts.order_tracker import OrderTracker
        dispatcher = AlertDispatcher(bot_token='BOT', chat_id='CHAT')
        tracker = OrderTracker(sheet_id='')
        tracker._cache_loaded = True

        orders = [_make_coupang_order('ORD-001'), _make_coupang_order('ORD-002')]
        new_orders = tracker.filter_new_orders(orders)
        assert len(new_orders) == 2

        for order in new_orders:
            sent = dispatcher.send_new_order_alert(order)
            if sent:
                tracker.mark_alerted(order)

        # 동일 주문 재시도 시 필터링
        new_orders2 = tracker.filter_new_orders(orders)
        assert len(new_orders2) == 0
        assert mock_post.call_count == 2

    @patch('src.order_alerts.alert_dispatcher.requests.post')
    def test_status_change_flow(self, mock_post):
        """주문 상태 변경 알림 흐름."""
        mock_post.return_value = MagicMock(raise_for_status=MagicMock())
        from src.order_alerts.alert_dispatcher import AlertDispatcher
        from src.order_alerts.order_tracker import OrderTracker
        dispatcher = AlertDispatcher(bot_token='BOT', chat_id='CHAT')
        tracker = OrderTracker(sheet_id='')
        tracker._cache_loaded = True

        order = _make_coupang_order('ORD-001', 'ACCEPT')
        # 초기 알림
        tracker.mark_alerted(order, 'ACCEPT')

        # 배송 시작
        should_alert = tracker.should_send_status_alert('ORD-001', 'DELIVERING')
        assert should_alert is True
        dispatcher.send_status_change_alert(order, 'DELIVERING')
        tracker.mark_alerted(order, 'DELIVERING')

        # 배송 완료
        should_alert2 = tracker.should_send_status_alert('ORD-001', 'DELIVERED')
        assert should_alert2 is True

        # 동일 상태 중복 방지
        should_alert3 = tracker.should_send_status_alert('ORD-001', 'DELIVERING')
        assert should_alert3 is False

    def test_coupang_and_naver_orders_independent(self):
        """쿠팡/네이버 주문이 서로 독립적으로 추적."""
        from src.order_alerts.order_tracker import OrderTracker
        tracker = OrderTracker(sheet_id='')
        tracker._cache_loaded = True

        # 동일한 order_id지만 다른 상태
        coupang_order = _make_coupang_order('COMMON-001', 'ACCEPT')

        tracker.mark_alerted(coupang_order, 'ACCEPT')
        # 네이버의 COMMON-001 + PAYED는 아직 미발송
        assert tracker.should_send_status_alert('COMMON-001', 'PAYED') is True
