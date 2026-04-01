"""네이버 커머스 API 주문 폴링 모듈.

네이버 커머스 API를 주기적으로 폴링하여 신규 주문을 감지합니다.
"""

import base64
import hashlib
import hmac
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import List

import requests

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT = 15
_DEFAULT_POLL_INTERVAL = 300  # 5분

_NAVER_API_BASE = 'https://api.commerce.naver.com/external'
_TOKEN_URL = f'{_NAVER_API_BASE}/v1/oauth2/token'
_ORDERS_URL = f'{_NAVER_API_BASE}/v1/pay-order/seller/orders/last-changed-statuses'


class NaverOrderPoller:
    """네이버 커머스 API 주문 폴링 클래스.

    OAuth2 클라이언트 자격증명을 사용하여 신규 주문을 주기적으로 조회합니다.

    환경변수:
        NAVER_COMMERCE_CLIENT_ID: 네이버 커머스 API 클라이언트 ID
        NAVER_COMMERCE_CLIENT_SECRET: 네이버 커머스 API 클라이언트 시크릿
        ORDER_POLL_INTERVAL_SECONDS: 폴링 간격(초, 기본 300)
    """

    def __init__(
        self,
        client_id: str = None,
        client_secret: str = None,
        poll_interval: int = None,
    ):
        """초기화.

        Args:
            client_id: 네이버 커머스 클라이언트 ID (None이면 환경변수 사용)
            client_secret: 네이버 커머스 클라이언트 시크릿 (None이면 환경변수 사용)
            poll_interval: 폴링 간격(초). None이면 환경변수 또는 300초.
        """
        self._client_id = client_id or os.getenv('NAVER_COMMERCE_CLIENT_ID', '')
        self._client_secret = client_secret or os.getenv('NAVER_COMMERCE_CLIENT_SECRET', '')
        self._poll_interval = poll_interval if poll_interval is not None else int(
            os.getenv('ORDER_POLL_INTERVAL_SECONDS', str(_DEFAULT_POLL_INTERVAL))
        )
        self._access_token: str = ''
        self._token_expires_at: float = 0.0

    # ── public API ───────────────────────────────────────────

    def fetch_new_orders(self, since_minutes: int = None) -> List[dict]:
        """신규 주문 조회.

        Args:
            since_minutes: 최근 N분 이내 주문 조회. None이면 poll_interval 기준.

        Returns:
            주문 목록 (list of dict)
        """
        if not self._client_id or not self._client_secret:
            raise ValueError("네이버 커머스 API 자격증명이 설정되지 않았습니다 (NAVER_COMMERCE_CLIENT_ID, NAVER_COMMERCE_CLIENT_SECRET)")

        minutes = since_minutes if since_minutes is not None else (self._poll_interval // 60 + 1)
        now = datetime.now(tz=timezone.utc)
        last_changed_from = (now - timedelta(minutes=minutes)).strftime('%Y-%m-%dT%H:%M:%S.000Z')
        last_changed_to = now.strftime('%Y-%m-%dT%H:%M:%S.000Z')

        token = self._get_access_token()
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
        }
        params = {
            'lastChangedFrom': last_changed_from,
            'lastChangedTo': last_changed_to,
            'orderStatusType': 'PAY_WAITING,PAYED',
        }
        resp = requests.get(_ORDERS_URL, headers=headers, params=params, timeout=_REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        orders = data.get('data', [])
        logger.info("네이버 신규 주문 %d건 조회됨", len(orders))
        return self._normalize_orders(orders)

    def poll_loop(self, callback, stop_event=None):
        """주문 폴링 루프 (blocking).

        Args:
            callback: 신규 주문 목록을 받는 콜백 함수 callback(orders: list)
            stop_event: threading.Event — set() 되면 루프 종료. None이면 무한 루프.
        """
        logger.info("네이버 주문 폴링 시작 (간격: %d초)", self._poll_interval)
        while True:
            try:
                orders = self.fetch_new_orders()
                if orders:
                    callback(orders)
            except Exception as exc:
                logger.error("네이버 폴링 오류: %s", exc)
            if stop_event and stop_event.is_set():
                break
            time.sleep(self._poll_interval)

    # ── 인증 ────────────────────────────────────────────────

    def _get_access_token(self) -> str:
        """네이버 커머스 OAuth2 액세스 토큰 조회 (캐싱 포함).

        Returns:
            유효한 액세스 토큰
        """
        if self._access_token and time.monotonic() < self._token_expires_at:
            return self._access_token

        # 토큰 생성 (HMAC-SHA256)
        timestamp = str(int(time.time() * 1000))
        password = self._generate_client_secret_sign(timestamp)
        payload = {
            'client_id': self._client_id,
            'timestamp': timestamp,
            'client_secret_sign': password,
            'grant_type': 'client_credentials',
            'type': 'SELF',
        }
        resp = requests.post(_TOKEN_URL, data=payload, timeout=_REQUEST_TIMEOUT)
        resp.raise_for_status()
        token_data = resp.json()

        self._access_token = token_data.get('access_token', '')
        expires_in = int(token_data.get('expires_in', 3600))
        self._token_expires_at = time.monotonic() + expires_in - 60  # 60초 여유
        logger.debug("네이버 액세스 토큰 갱신됨 (만료: %ds)", expires_in)
        return self._access_token

    def _generate_client_secret_sign(self, timestamp: str) -> str:
        """클라이언트 시크릿 서명 생성 (HMAC-SHA256 + Base64).

        Args:
            timestamp: 밀리초 타임스탬프

        Returns:
            Base64 인코딩된 서명
        """
        message = f"{self._client_id}_{timestamp}"
        signature = hmac.new(
            self._client_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256,
        ).digest()
        return base64.b64encode(signature).decode('utf-8')

    # ── 데이터 변환 ──────────────────────────────────────────

    @staticmethod
    def _normalize_orders(raw_orders: list) -> List[dict]:
        """네이버 주문 데이터를 공통 형식으로 변환.

        Args:
            raw_orders: 네이버 커머스 API 원시 주문 목록

        Returns:
            정규화된 주문 목록
        """
        result = []
        for order in raw_orders:
            product_order = order.get('productOrder', {})
            product_name = product_order.get('productName', '')
            quantity = int(product_order.get('quantity', 1))
            total_price = float(product_order.get('totalPaymentAmount', 0))
            orderer = order.get('order', {}).get('ordererName', '')
            phone = order.get('order', {}).get('ordererTel', '')
            result.append({
                'platform': 'naver',
                'order_id': str(order.get('productOrderId', '')),
                'order_number': str(order.get('orderId', order.get('productOrderId', ''))),
                'product_names': [product_name] if product_name else [],
                'quantities': [quantity],
                'total_price': total_price,
                'currency': 'KRW',
                'buyer_name': orderer,
                'buyer_phone': phone,
                'status': product_order.get('productOrderStatus', ''),
                'created_at': order.get('order', {}).get('paymentDate', ''),
                'raw': order,
            })
        return result

    @property
    def poll_interval(self) -> int:
        """폴링 간격(초)."""
        return self._poll_interval
