"""쿠팡 Wing API 주문 폴링 모듈.

쿠팡 Wing API를 주기적으로 폴링하여 신규 주문을 감지합니다.
"""

import hashlib
import hmac
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import requests

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT = 15
_DEFAULT_POLL_INTERVAL = 300  # 5분


class CoupangOrderPoller:
    """쿠팡 Wing API 주문 폴링 클래스.

    Wing API HMAC 인증을 사용하여 신규 주문을 주기적으로 조회합니다.

    환경변수:
        COUPANG_VENDOR_ID: 쿠팡 Wing 벤더 ID
        COUPANG_ACCESS_KEY: 쿠팡 Wing 액세스 키
        COUPANG_SECRET_KEY: 쿠팡 Wing 시크릿 키
        ORDER_POLL_INTERVAL_SECONDS: 폴링 간격(초, 기본 300)
    """

    _BASE_URL = 'https://api-gateway.coupang.com'
    _ORDERS_PATH = '/v2/providers/openapi/apis/api/v4/vendors/{vendor_id}/ordersheets'

    def __init__(
        self,
        vendor_id: str = None,
        access_key: str = None,
        secret_key: str = None,
        poll_interval: int = None,
    ):
        """초기화.

        Args:
            vendor_id: 쿠팡 Wing 벤더 ID (None이면 환경변수 사용)
            access_key: 쿠팡 Wing 액세스 키 (None이면 환경변수 사용)
            secret_key: 쿠팡 Wing 시크릿 키 (None이면 환경변수 사용)
            poll_interval: 폴링 간격(초). None이면 환경변수 또는 300초.
        """
        self._vendor_id = vendor_id or os.getenv('COUPANG_VENDOR_ID', '')
        self._access_key = access_key or os.getenv('COUPANG_ACCESS_KEY', '')
        self._secret_key = secret_key or os.getenv('COUPANG_SECRET_KEY', '')
        self._poll_interval = poll_interval if poll_interval is not None else int(
            os.getenv('ORDER_POLL_INTERVAL_SECONDS', str(_DEFAULT_POLL_INTERVAL))
        )

    # ── public API ───────────────────────────────────────────

    def fetch_new_orders(self, since_minutes: int = None) -> List[dict]:
        """신규 주문 조회.

        Args:
            since_minutes: 최근 N분 이내 주문 조회. None이면 poll_interval 기준.

        Returns:
            주문 목록 (list of dict)
        """
        if not self._vendor_id or not self._access_key or not self._secret_key:
            raise ValueError("쿠팡 Wing API 자격증명이 설정되지 않았습니다 (COUPANG_VENDOR_ID, COUPANG_ACCESS_KEY, COUPANG_SECRET_KEY)")

        minutes = since_minutes if since_minutes is not None else (self._poll_interval // 60 + 1)
        now = datetime.now(tz=timezone.utc)
        created_at_from = (now - timedelta(minutes=minutes)).strftime('%Y-%m-%dT%H:%M:%S')
        created_at_to = now.strftime('%Y-%m-%dT%H:%M:%S')

        path = self._ORDERS_PATH.format(vendor_id=self._vendor_id)
        query = (
            f'createdAtFrom={created_at_from}&createdAtTo={created_at_to}'
            f'&status=ACCEPT&vendorId={self._vendor_id}'
        )
        headers = self._build_auth_headers('GET', path, query)
        url = f"{self._BASE_URL}{path}?{query}"

        resp = requests.get(url, headers=headers, timeout=_REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        orders = data.get('data', {}).get('orderSheets', [])
        logger.info("쿠팡 신규 주문 %d건 조회됨", len(orders))
        return self._normalize_orders(orders)

    def poll_loop(self, callback, stop_event=None):
        """주문 폴링 루프 (blocking).

        Args:
            callback: 신규 주문 목록을 받는 콜백 함수 callback(orders: list)
            stop_event: threading.Event — set() 되면 루프 종료. None이면 무한 루프.
        """
        logger.info("쿠팡 주문 폴링 시작 (간격: %d초)", self._poll_interval)
        while True:
            try:
                orders = self.fetch_new_orders()
                if orders:
                    callback(orders)
            except Exception as exc:
                logger.error("쿠팡 폴링 오류: %s", exc)
            if stop_event and stop_event.is_set():
                break
            time.sleep(self._poll_interval)

    # ── 내부 메서드 ──────────────────────────────────────────

    def _build_auth_headers(self, method: str, path: str, query: str = '') -> dict:
        """Wing API HMAC 인증 헤더 생성.

        Args:
            method: HTTP 메서드 (GET, POST 등)
            path: API 경로
            query: 쿼리 스트링

        Returns:
            인증 헤더 딕셔너리
        """
        datetime_str = datetime.now(tz=timezone.utc).strftime('%y%m%dT%H%M%SZ')
        message = f"{method}{datetime_str}{path}{query}"
        signature = hmac.new(
            self._secret_key.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256,
        ).hexdigest()
        auth = f"CEA algorithm=HmacSHA256, access-key={self._access_key}, signed-date={datetime_str}, signature={signature}"
        return {
            'Authorization': auth,
            'Content-Type': 'application/json',
        }

    @staticmethod
    def _normalize_orders(raw_orders: list) -> List[dict]:
        """쿠팡 주문 데이터를 공통 형식으로 변환.

        Args:
            raw_orders: Wing API 원시 주문 목록

        Returns:
            정규화된 주문 목록
        """
        result = []
        for order in raw_orders:
            items = order.get('orderItems', [])
            product_names = [item.get('productName', '') for item in items]
            quantities = [item.get('quantity', 1) for item in items]
            total_price = sum(
                item.get('orderPrice', 0) * item.get('quantity', 1)
                for item in items
            )
            buyer = order.get('buyer', {})
            result.append({
                'platform': 'coupang',
                'order_id': str(order.get('orderId', '')),
                'order_number': str(order.get('orderCode', order.get('orderId', ''))),
                'product_names': product_names,
                'quantities': quantities,
                'total_price': total_price,
                'currency': 'KRW',
                'buyer_name': buyer.get('name', ''),
                'buyer_phone': buyer.get('safeNumber', buyer.get('phone', '')),
                'status': order.get('status', 'ACCEPT'),
                'created_at': order.get('orderedAt', ''),
                'raw': order,
            })
        return result

    @property
    def poll_interval(self) -> int:
        """폴링 간격(초)."""
        return self._poll_interval

    def _get_vendor_id(self) -> Optional[str]:
        """벤더 ID 반환."""
        return self._vendor_id or None
