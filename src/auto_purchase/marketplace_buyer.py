"""src/auto_purchase/marketplace_buyer.py — 마켓플레이스 자동 구매 구현 (Phase 96)."""
from __future__ import annotations

import abc
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from .purchase_models import PurchaseOrder, PurchaseResult, PurchaseStatus, SourceOption

logger = logging.getLogger(__name__)


class MarketplaceBuyer(abc.ABC):
    """마켓플레이스 구매 추상 기반 클래스."""

    @abc.abstractmethod
    def search_product(self, query: str, **kwargs) -> List[SourceOption]:
        """상품을 검색한다."""

    @abc.abstractmethod
    def check_availability(self, product_id: str) -> Dict:
        """상품 재고/가격을 확인한다."""

    @abc.abstractmethod
    def place_order(self, order: PurchaseOrder) -> PurchaseResult:
        """주문을 생성한다."""

    @abc.abstractmethod
    def check_order_status(self, order_id: str) -> Dict:
        """주문 상태를 조회한다."""

    @abc.abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """주문을 취소한다."""

    @property
    @abc.abstractmethod
    def marketplace_name(self) -> str:
        """마켓플레이스 이름."""


# ---------------------------------------------------------------------------
# Amazon Buyer (SP-API mock)
# ---------------------------------------------------------------------------

class AmazonBuyer(MarketplaceBuyer):
    """Amazon SP-API mock 구현.

    미국/일본 Amazon 자동 주문을 지원한다.
    실제 SP-API 연동 시 이 클래스를 교체한다.
    """

    _DEFAULT_FORWARDER_ADDRESS = {
        'name': 'MyForwarder',
        'address_line_1': '123 Forwarder St',
        'city': 'Los Angeles',
        'state_or_region': 'CA',
        'postal_code': '90001',
        'country_code': 'US',
    }

    def __init__(
        self,
        region: str = 'US',
        access_key: str = '',
        secret_key: str = '',
        marketplace_id: str = '',
    ) -> None:
        self.region = region.upper()
        self._access_key = access_key
        self._secret_key = secret_key
        self._marketplace_id = marketplace_id
        # 인메모리 주문 저장소 (mock)
        self._orders: Dict[str, Dict] = {}
        # mock 상품 카탈로그 (ASIN → 상품 정보)
        self._catalog: Dict[str, Dict] = {
            'B08N5WRWNW': {
                'asin': 'B08N5WRWNW', 'title': 'Echo Dot (4th Gen)',
                'price': 49.99, 'stock': 100, 'rating': 4.7,
                'delivery_days': 5,
            },
            'B09B8YWXDF': {
                'asin': 'B09B8YWXDF', 'title': 'AirPods Pro (2nd Gen)',
                'price': 199.99, 'stock': 50, 'rating': 4.8,
                'delivery_days': 3,
            },
            'B0BDJH3XVN': {
                'asin': 'B0BDJH3XVN', 'title': 'Kindle Paperwhite',
                'price': 139.99, 'stock': 30, 'rating': 4.6,
                'delivery_days': 7,
            },
        }

    @property
    def marketplace_name(self) -> str:
        return f'amazon_{self.region.lower()}'

    def search_product(self, query: str, **kwargs) -> List[SourceOption]:
        """ASIN 기반 또는 키워드 기반 상품 검색."""
        results = []
        query_lower = query.lower()
        for asin, info in self._catalog.items():
            if query_lower in info['title'].lower() or query_lower == asin.lower():
                results.append(SourceOption(
                    marketplace=self.marketplace_name,
                    product_id=asin,
                    title=info['title'],
                    price=info['price'],
                    currency='USD' if self.region == 'US' else 'JPY',
                    availability=info['stock'] > 0,
                    stock_quantity=info['stock'],
                    estimated_delivery_days=info['delivery_days'],
                    seller_rating=info['rating'],
                    shipping_cost=0.0,
                    url=f'https://www.amazon.{"com" if self.region == "US" else "co.jp"}/dp/{asin}',
                ))
        return results

    def check_availability(self, product_id: str) -> Dict:
        """재고/가격 확인."""
        info = self._catalog.get(product_id)
        if not info:
            return {'available': False, 'product_id': product_id, 'error': 'Product not found'}
        return {
            'available': info['stock'] > 0,
            'product_id': product_id,
            'price': info['price'],
            'currency': 'USD' if self.region == 'US' else 'JPY',
            'stock': info['stock'],
            'estimated_delivery_days': info['delivery_days'],
        }

    def place_order(self, order: PurchaseOrder) -> PurchaseResult:
        """주문 생성 — 배송대행지 주소 자동 설정."""
        info = self._catalog.get(order.source_product_id)
        if not info or info['stock'] < order.quantity:
            return PurchaseResult(
                success=False,
                order_id=order.order_id,
                error_message=f'재고 부족: {order.source_product_id}',
                marketplace=self.marketplace_name,
            )

        # 배송지: 고객 주소 또는 배송대행지 기본 주소
        shipping_address = order.shipping_address or self._DEFAULT_FORWARDER_ADDRESS

        confirmation_code = f'AMZ-{self.region}-{uuid.uuid4().hex[:8].upper()}'
        estimated_delivery = datetime.now(timezone.utc) + timedelta(days=info['delivery_days'])

        # 재고 차감 (mock)
        self._catalog[order.source_product_id]['stock'] -= order.quantity

        amz_order_id = f'114-{uuid.uuid4().int % 10**7:07d}-{uuid.uuid4().int % 10**7:07d}'
        self._orders[amz_order_id] = {
            'order_id': amz_order_id,
            'purchase_order_id': order.order_id,
            'status': 'Pending',
            'product_id': order.source_product_id,
            'quantity': order.quantity,
            'price': info['price'],
            'shipping_address': shipping_address,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'estimated_delivery': estimated_delivery.isoformat(),
        }

        logger.info(
            'Amazon order placed: %s (ASIN: %s, qty: %d, addr: %s)',
            amz_order_id, order.source_product_id, order.quantity,
            shipping_address.get('city', 'unknown'),
        )

        return PurchaseResult(
            success=True,
            order_id=amz_order_id,
            confirmation_code=confirmation_code,
            estimated_delivery=estimated_delivery,
            actual_cost=info['price'] * order.quantity,
            currency='USD' if self.region == 'US' else 'JPY',
            marketplace=self.marketplace_name,
        )

    def check_order_status(self, order_id: str) -> Dict:
        """주문 상태 조회."""
        order = self._orders.get(order_id)
        if not order:
            return {'order_id': order_id, 'status': 'NotFound', 'error': 'Order not found'}
        # mock 상태 진행 (시간 경과 시뮬레이션)
        return {
            'order_id': order_id,
            'status': order.get('status', 'Pending'),
            'tracking_number': order.get('tracking_number', ''),
            'estimated_delivery': order.get('estimated_delivery', ''),
        }

    def cancel_order(self, order_id: str) -> bool:
        """주문 취소."""
        order = self._orders.get(order_id)
        if not order:
            return False
        if order.get('status') in ('Shipped', 'Delivered'):
            return False
        order['status'] = 'Cancelled'
        logger.info('Amazon order cancelled: %s', order_id)
        return True


# ---------------------------------------------------------------------------
# Taobao Buyer (API mock)
# ---------------------------------------------------------------------------

class TaobaoBuyer(MarketplaceBuyer):
    """타오바오 API mock 구현.

    에이전트 경유 구매 방식.
    """

    def __init__(self, agent_api_key: str = '', agent_endpoint: str = '') -> None:
        self._agent_api_key = agent_api_key
        self._agent_endpoint = agent_endpoint
        self._orders: Dict[str, Dict] = {}
        self._catalog: Dict[str, Dict] = {
            'TB001234': {
                'id': 'TB001234', 'title': '나이키 에어맥스 270',
                'price': 380.0, 'currency': 'CNY', 'stock': 200,
                'rating': 4.5, 'delivery_days': 14,
            },
            'TB005678': {
                'id': 'TB005678', 'title': '애플 USB-C 케이블',
                'price': 15.0, 'currency': 'CNY', 'stock': 500,
                'rating': 4.2, 'delivery_days': 10,
            },
        }

    @property
    def marketplace_name(self) -> str:
        return 'taobao'

    def search_product(self, query: str, **kwargs) -> List[SourceOption]:
        results = []
        query_lower = query.lower()
        for pid, info in self._catalog.items():
            if query_lower in info['title'].lower() or query_lower == pid.lower():
                results.append(SourceOption(
                    marketplace=self.marketplace_name,
                    product_id=pid,
                    title=info['title'],
                    price=info['price'],
                    currency=info['currency'],
                    availability=info['stock'] > 0,
                    stock_quantity=info['stock'],
                    estimated_delivery_days=info['delivery_days'],
                    seller_rating=info['rating'],
                    shipping_cost=10.0,
                    url=f'https://item.taobao.com/item.htm?id={pid}',
                ))
        return results

    def check_availability(self, product_id: str) -> Dict:
        info = self._catalog.get(product_id)
        if not info:
            return {'available': False, 'product_id': product_id, 'error': 'Product not found'}
        return {
            'available': info['stock'] > 0,
            'product_id': product_id,
            'price': info['price'],
            'currency': info['currency'],
            'stock': info['stock'],
            'estimated_delivery_days': info['delivery_days'],
        }

    def place_order(self, order: PurchaseOrder) -> PurchaseResult:
        """에이전트 경유 타오바오 주문 생성."""
        info = self._catalog.get(order.source_product_id)
        if not info or info['stock'] < order.quantity:
            return PurchaseResult(
                success=False,
                order_id=order.order_id,
                error_message=f'재고 부족: {order.source_product_id}',
                marketplace=self.marketplace_name,
            )

        self._catalog[order.source_product_id]['stock'] -= order.quantity

        agent_order_id = f'TB-{uuid.uuid4().hex[:10].upper()}'
        estimated_delivery = datetime.now(timezone.utc) + timedelta(days=info['delivery_days'])

        self._orders[agent_order_id] = {
            'order_id': agent_order_id,
            'status': 'submitted_to_agent',
            'product_id': order.source_product_id,
            'quantity': order.quantity,
            'created_at': datetime.now(timezone.utc).isoformat(),
        }

        logger.info('Taobao order via agent: %s (item: %s)', agent_order_id, order.source_product_id)

        return PurchaseResult(
            success=True,
            order_id=agent_order_id,
            confirmation_code=f'TB-CONF-{uuid.uuid4().hex[:6].upper()}',
            estimated_delivery=estimated_delivery,
            actual_cost=(info['price'] + 10.0) * order.quantity,
            currency='CNY',
            marketplace=self.marketplace_name,
        )

    def check_order_status(self, order_id: str) -> Dict:
        order = self._orders.get(order_id)
        if not order:
            return {'order_id': order_id, 'status': 'NotFound'}
        return {'order_id': order_id, 'status': order.get('status', 'submitted_to_agent')}

    def cancel_order(self, order_id: str) -> bool:
        order = self._orders.get(order_id)
        if not order:
            return False
        if order.get('status') in ('shipped', 'delivered'):
            return False
        order['status'] = 'cancelled'
        return True


# ---------------------------------------------------------------------------
# Alibaba (1688) Buyer — B2B 대량 구매
# ---------------------------------------------------------------------------

class AlibabaBuyer(MarketplaceBuyer):
    """1688 API mock 구현 — B2B 대량 구매."""

    def __init__(self, app_key: str = '', app_secret: str = '') -> None:
        self._app_key = app_key
        self._app_secret = app_secret
        self._orders: Dict[str, Dict] = {}
        self._catalog: Dict[str, Dict] = {
            '1688-001': {
                'id': '1688-001', 'title': '티셔츠 도매 (흰색)',
                'price': 8.5, 'currency': 'CNY', 'stock': 5000,
                'rating': 4.6, 'delivery_days': 7, 'moq': 100,
            },
            '1688-002': {
                'id': '1688-002', 'title': '스마트폰 케이스 도매',
                'price': 3.2, 'currency': 'CNY', 'stock': 10000,
                'rating': 4.4, 'delivery_days': 5, 'moq': 50,
            },
        }

    @property
    def marketplace_name(self) -> str:
        return 'alibaba_1688'

    def search_product(self, query: str, **kwargs) -> List[SourceOption]:
        results = []
        query_lower = query.lower()
        for pid, info in self._catalog.items():
            if query_lower in info['title'].lower() or query_lower == pid.lower():
                results.append(SourceOption(
                    marketplace=self.marketplace_name,
                    product_id=pid,
                    title=info['title'],
                    price=info['price'],
                    currency=info['currency'],
                    availability=info['stock'] > 0,
                    stock_quantity=info['stock'],
                    estimated_delivery_days=info['delivery_days'],
                    seller_rating=info['rating'],
                    shipping_cost=20.0,
                    moq=info['moq'],
                    url=f'https://detail.1688.com/offer/{pid}.html',
                ))
        return results

    def check_availability(self, product_id: str) -> Dict:
        info = self._catalog.get(product_id)
        if not info:
            return {'available': False, 'product_id': product_id, 'error': 'Product not found'}
        return {
            'available': info['stock'] > 0,
            'product_id': product_id,
            'price': info['price'],
            'currency': info['currency'],
            'stock': info['stock'],
            'moq': info['moq'],
            'estimated_delivery_days': info['delivery_days'],
        }

    def check_moq(self, product_id: str, quantity: int) -> bool:
        """MOQ(최소주문수량) 충족 여부 확인."""
        info = self._catalog.get(product_id)
        if not info:
            return False
        return quantity >= info.get('moq', 1)

    def place_order(self, order: PurchaseOrder) -> PurchaseResult:
        """B2B 대량 주문 생성 — MOQ 체크 포함."""
        info = self._catalog.get(order.source_product_id)
        if not info:
            return PurchaseResult(
                success=False,
                order_id=order.order_id,
                error_message=f'상품 없음: {order.source_product_id}',
                marketplace=self.marketplace_name,
            )

        moq = info.get('moq', 1)
        if order.quantity < moq:
            return PurchaseResult(
                success=False,
                order_id=order.order_id,
                error_message=f'MOQ 미충족: 최소 {moq}개 필요 (요청: {order.quantity}개)',
                marketplace=self.marketplace_name,
            )

        if info['stock'] < order.quantity:
            return PurchaseResult(
                success=False,
                order_id=order.order_id,
                error_message=f'재고 부족: {info["stock"]}개 남음',
                marketplace=self.marketplace_name,
            )

        self._catalog[order.source_product_id]['stock'] -= order.quantity

        b2b_order_id = f'1688-ORD-{uuid.uuid4().hex[:8].upper()}'
        estimated_delivery = datetime.now(timezone.utc) + timedelta(days=info['delivery_days'])

        self._orders[b2b_order_id] = {
            'order_id': b2b_order_id,
            'status': 'payment_pending',
            'product_id': order.source_product_id,
            'quantity': order.quantity,
            'created_at': datetime.now(timezone.utc).isoformat(),
        }

        logger.info(
            '1688 B2B order: %s (item: %s, qty: %d)',
            b2b_order_id, order.source_product_id, order.quantity,
        )

        return PurchaseResult(
            success=True,
            order_id=b2b_order_id,
            confirmation_code=f'1688-{uuid.uuid4().hex[:6].upper()}',
            estimated_delivery=estimated_delivery,
            actual_cost=(info['price'] + 20.0) * order.quantity,
            currency='CNY',
            marketplace=self.marketplace_name,
        )

    def check_order_status(self, order_id: str) -> Dict:
        order = self._orders.get(order_id)
        if not order:
            return {'order_id': order_id, 'status': 'NotFound'}
        return {'order_id': order_id, 'status': order.get('status', 'payment_pending')}

    def cancel_order(self, order_id: str) -> bool:
        order = self._orders.get(order_id)
        if not order:
            return False
        if order.get('status') in ('shipped', 'delivered'):
            return False
        order['status'] = 'cancelled'
        return True
