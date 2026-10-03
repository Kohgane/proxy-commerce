"""네이버 커머스 API 주문 폴링 모듈 — W1(오너 2026-10-03) 재작성.

## 실측(이전 코드)
- 토큰 서명이 **HMAC-SHA256**이었다. 네이버 규격은 bcrypt(`client_id_timestamp`, client_secret) → base64 —
  이 파일로는 토큰이 한 번도 나올 수 없었다.
- 주문 경로 `/v1/pay-order/seller/orders/last-changed-statuses`는 없는 주소다(정본은 `product-orders/…`).
- 읽는 키는 `NAVER_COMMERCE_*` 한 벌 — 스토어 구분 없음.
- 이 레포에서 이 폴러를 띄우는 서비스·크론은 없었다(render.yaml·크론 0). 운영 주문 알림은 LinkLynk 서버의
  `order_notify_all_v1.py`(볼트 [[네이버스스]])다 — 그래서 이 파일의 결함이 실제 알림을 끊지는 않았다.

## 지금
- **토큰 = 스마트스토어 업로더의 `_get_access_token` 한 곳**(bcrypt 서명 단일 소스 `_naver_signature` · 릴레이 경유 ·
  실패 원문 `token_error`). 이 파일엔 서명 코드가 없다.
- **스토어별**: `store="chezgoga"|"gocosmos"`면 그 스토어 키(`NAVER_<STORE>_*`, 셰고가는 공용 키 실측 승격 포함 — V).
- 주문 = `GET /v1/pay-order/seller/product-orders/last-changed-statuses`(lastChangedType=PAYED, **24시간 창**)로
  상품주문번호를 모은 뒤 `POST /v1/pay-order/seller/product-orders/query`로 상세.
  경로 출처: 오픈소스 laravel-naver-commerce `Orders.php`. 응답 필드 이름은 문서로 확인하지 못해
  **`productOrderId`를 응답 전체에서 찾아 모은다**(위치를 짐작해 박지 않는다).
- 실패는 원문을 그대로 올린다(조용한 0건 금지).
"""

import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Iterable, List, Optional
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

_DEFAULT_POLL_INTERVAL = 300  # 5분
_KST = timezone(timedelta(hours=9))
_CHANGED_PATH = '/v1/pay-order/seller/product-orders/last-changed-statuses'
_QUERY_PATH = '/v1/pay-order/seller/product-orders/query'
_QUERY_CHUNK = 50
_MAX_PAGES = 20


class NaverOrderError(RuntimeError):
    """네이버 주문 조회 실패 — 메시지 = 응답 원문."""


def _walk(node, key: str):
    """응답 어디에 있든 `key`의 값을 모은다(구조 짐작 없이)."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k == key and v not in (None, ''):
                yield v
            else:
                yield from _walk(v, key)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v, key)


def _details(node):
    """`productOrder` 칸을 가진 dict(주문 한 줄)를 모은다."""
    if isinstance(node, dict):
        if isinstance(node.get('productOrder'), dict):
            yield node
            return
        for v in node.values():
            yield from _details(v)
    elif isinstance(node, list):
        for v in node:
            yield from _details(v)


def _ts(dt: datetime) -> str:
    return dt.astimezone(_KST).strftime('%Y-%m-%dT%H:%M:%S.000+09:00')


class NaverOrderPoller:
    """네이버 커머스 API 주문 폴링.

    환경변수: 스토어 키(`NAVER_<STORE>_CLIENT_ID/SECRET`, store 미지정이면 `NAVER_COMMERCE_*`) ·
    ORDER_POLL_INTERVAL_SECONDS(기본 300).
    """

    def __init__(self, client_id: str = None, client_secret: str = None, poll_interval: int = None,
                 store: Optional[str] = None):
        from src.uploaders.naver_uploader import NaverSmartStoreUploader
        self.store = (store or '').strip().lower() or None
        self._up = NaverSmartStoreUploader(account=self.store)
        if not self.store:
            # 스토어 미지정 = 예전 이름 한 벌(NAVER_COMMERCE_*). 업로더 기본은 NAVER_CLIENT_ID(= 로그인 OAuth와 같은
            #   이름)를 먼저 읽으므로 여기선 커머스 키를 명시한다.
            self._up.client_id = os.getenv('NAVER_COMMERCE_CLIENT_ID', '').strip()
            self._up.client_secret = os.getenv('NAVER_COMMERCE_CLIENT_SECRET', '').strip()
        if client_id:
            self._up.client_id = client_id
        if client_secret:
            self._up.client_secret = client_secret
        self._poll_interval = poll_interval if poll_interval is not None else int(
            os.getenv('ORDER_POLL_INTERVAL_SECONDS', str(_DEFAULT_POLL_INTERVAL)))

    # 예전 속성 이름 호환(테스트·CLI)
    @property
    def _client_id(self) -> str:
        return self._up.client_id

    # ── 인증 ────────────────────────────────────────────────

    def _get_access_token(self) -> str:
        """토큰 — 업로더 한 곳(bcrypt 서명·릴레이·캐시). 실패면 원문과 함께 예외."""
        token = self._up._get_access_token()
        if not token:
            raise NaverOrderError(f"네이버 토큰 발급 실패 — {self._up.token_error or '사유 원문 없음'}")
        return token

    # ── 조회 ────────────────────────────────────────────────

    def _api(self, method: str, path: str, data: dict = None) -> dict:
        self._get_access_token()
        res = self._up._api_request(method, path, data=data)
        if not isinstance(res, dict):
            raise NaverOrderError(f"네이버 응답 형식 이상: {str(res)[:200]}")
        if 'error' in res:
            raise NaverOrderError(str(res['error'])[:300])
        return res

    def changed_product_order_ids(self, since: datetime, until: datetime) -> List[str]:
        """`since~until`(24시간 이하 창으로 쪼갬) 결제완료로 바뀐 상품주문번호."""
        ids: List[str] = []
        cur = since
        while cur < until:
            end = min(cur + timedelta(hours=24), until)
            more = None
            for _ in range(_MAX_PAGES):
                q = {'lastChangedFrom': _ts(cur), 'lastChangedTo': _ts(end), 'lastChangedType': 'PAYED'}
                if more:
                    q['moreSequence'] = more
                res = self._api('GET', f'{_CHANGED_PATH}?{urlencode(q)}')
                for v in _walk(res, 'productOrderId'):
                    if str(v) not in ids:
                        ids.append(str(v))
                nxt = next(iter(_walk(res, 'moreSequence')), None)
                if not nxt or nxt == more:
                    break
                more = nxt
            cur = end
        return ids

    def product_orders(self, ids: Iterable[str]) -> List[dict]:
        """상품주문 상세(다건)."""
        ids = list(ids)
        out: List[dict] = []
        for i in range(0, len(ids), _QUERY_CHUNK):
            res = self._api('POST', _QUERY_PATH, data={'productOrderIds': ids[i:i + _QUERY_CHUNK]})
            out.extend(_details(res))
        return out

    def fetch_window(self, since: datetime, until: datetime) -> List[dict]:
        ids = self.changed_product_order_ids(since, until)
        if not ids:
            return []
        return self._normalize_orders(self.product_orders(ids), store=self.store)

    def fetch_new_orders(self, since_minutes: int = None) -> List[dict]:
        """최근 N분(기본 폴링 간격+1분) 결제완료 주문."""
        if not self._up.client_id or not self._up.client_secret:
            raise ValueError("네이버 커머스 API 자격증명이 설정되지 않았습니다 ("
                             + self._up._cred_env_hint() + ")")
        minutes = since_minutes if since_minutes is not None else (self._poll_interval // 60 + 1)
        now = datetime.now(tz=timezone.utc)
        orders = self.fetch_window(now - timedelta(minutes=minutes), now)
        logger.info("네이버 신규 주문 %d건 조회됨(%s)", len(orders), self.store or '공용 키')
        return orders

    def poll_loop(self, callback, stop_event=None):
        logger.info("네이버 주문 폴링 시작 (%s · 간격: %d초)", self.store or '공용 키', self._poll_interval)
        while True:
            try:
                orders = self.fetch_new_orders()
                if orders:
                    callback(orders)
            except Exception as exc:
                logger.error("네이버 폴링 오류(%s): %s", self.store or '공용 키', exc)
            if stop_event and stop_event.is_set():
                break
            time.sleep(self._poll_interval)

    # ── 데이터 변환 ──────────────────────────────────────────

    @staticmethod
    def _normalize_orders(raw_orders: list, store: Optional[str] = None) -> List[dict]:
        """주문 한 줄(`{order, productOrder}`) → 공통 형식. 없는 칸은 빈 값(지어내지 않음)."""
        result = []
        for row in raw_orders:
            po = row.get('productOrder') or {}
            od = row.get('order') or {}
            try:
                qty = int(po.get('quantity') or 1)
            except (TypeError, ValueError):
                qty = 1
            try:
                total = float(po.get('totalPaymentAmount') or 0)
            except (TypeError, ValueError):
                total = 0.0
            name = po.get('productName', '')
            poid = str(po.get('productOrderId') or row.get('productOrderId') or '')
            result.append({
                'platform': 'naver',
                'store': store or '',
                'order_id': poid,
                'order_number': str(od.get('orderId') or row.get('orderId') or poid),
                'product_names': [name] if name else [],
                'quantities': [qty],
                'total_price': total,
                'currency': 'KRW',
                'buyer_name': od.get('ordererName', ''),
                'buyer_phone': od.get('ordererTel', ''),
                'status': po.get('productOrderStatus', ''),
                'created_at': od.get('paymentDate', ''),
                'raw': row,
            })
        return result

    @property
    def poll_interval(self) -> int:
        """폴링 간격(초)."""
        return self._poll_interval


def store_pollers() -> List[NaverOrderPoller]:
    """키가 있는 스토어마다 폴러 하나(셰고가·고코스모스). 키 없는 스토어는 건너뛴다."""
    from src.seller_console.smartstore_routing import STORES
    out = []
    for st in STORES:
        p = NaverOrderPoller(store=st)
        if p._up.client_id and p._up.client_secret:
            out.append(p)
    return out
